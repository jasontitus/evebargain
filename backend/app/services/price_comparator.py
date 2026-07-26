"""The heart of the app: comparing local prices against Jita to find deals.

THE QUERY, IN PLAIN ENGLISH
    find_arbitrage builds one SQL statement that says:

        take every cached price in THIS region        (the `local` subquery)
        alongside every cached price in JITA          (the `jita` subquery)
        matched up by item                            (the join on type_id)
        keeping only items the player cares about     (category filter)
        and only where the local price is lower       (the price comparison)

    Doing it as a single query rather than looping in Python matters: a region
    can hold tens of thousands of cached prices, and the database can match
    them far faster than fetching them all into memory first.

    A *subquery* is just a query used as if it were a table. Two are needed
    here because both sides come from the same `market_cache` table -- one
    filtered to this region, one to Jita -- and they must be told apart.

    Note the join is an INNER join, which drops rows with no match on either
    side. That is deliberate for prices, but it also applies to the ItemType
    join: with an empty catalogue every row is dropped and the result is zero
    deals at any threshold. That failure is silent by nature, hence the
    explicit check and loud log after the query runs.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import MarketCache
from app.models.item import ItemType
from app.models.user import UserConfig
from app.models.alert import Alert
from app.schemas.market import ArbitrageResult
from app.services.location import get_region_name
from app.utils.eve_constants import (
    CATEGORY_BLUEPRINTS,
    THE_FORGE_REGION_ID,
    TRACKABLE_CATEGORIES,
)

logger = logging.getLogger(__name__)

# How long a given item in a given region stays "already alerted". Long enough
# to survive many scan cycles, short enough that a deal still sitting there
# tomorrow is worth mentioning again.
ALERT_COOLDOWN = timedelta(hours=6)


async def find_arbitrage(
    db: AsyncSession,
    region_id: int,
    user_config: UserConfig,
) -> list[ArbitrageResult]:
    """Compare local region prices against Jita and find deals.

    Returns a list of ArbitrageResult for items that meet the user's
    discount threshold and filtering criteria.

    Reads only from the local cache -- it never calls ESI. Whoever calls this
    is responsible for having refreshed the cache first, which is why the
    endpoints and the scanner fetch before comparing.
    """
    # Stored as JSON text because SQLite has no array type, so it has to be
    # parsed back into a Python list before use.
    tracked_categories = json.loads(user_config.tracked_category_ids)
    if not tracked_categories:
        # Tracking nothing legitimately matches nothing. Returning early also
        # avoids building a query with an empty IN () clause.
        return []

    region_name = await get_region_name(region_id)

    # Query: join local market cache with Jita cache on type_id,
    # filtered to the user's tracked categories
    local_cache = select(
        MarketCache.type_id,
        MarketCache.lowest_sell.label("local_price"),
        MarketCache.order_count.label("local_orders"),
        MarketCache.volume_remain.label("local_volume"),
    ).where(
        MarketCache.region_id == region_id,
        MarketCache.lowest_sell.isnot(None),
    ).subquery("local")

    jita_cache = select(
        MarketCache.type_id,
        MarketCache.lowest_sell.label("jita_price"),
    ).where(
        MarketCache.region_id == THE_FORGE_REGION_ID,
        MarketCache.lowest_sell.isnot(None),
    ).subquery("jita")

    query = (
        select(
            local_cache.c.type_id,
            local_cache.c.local_price,
            local_cache.c.local_volume,
            jita_cache.c.jita_price,
            ItemType.name.label("type_name"),
            ItemType.category_id.label("category_id"),
            ItemType.volume.label("volume_m3"),
        )
        .join(jita_cache, local_cache.c.type_id == jita_cache.c.type_id)
        .join(ItemType, local_cache.c.type_id == ItemType.type_id)
        .where(
            ItemType.category_id.in_(tracked_categories),
            ItemType.published.is_(True),
            # Local price must be lower than Jita
            local_cache.c.local_price < jita_cache.c.jita_price,
        )
    )

    result = await db.execute(query)
    rows = result.all()

    if not rows:
        # The query inner-joins ItemType, so an unpopulated catalogue produces
        # zero deals at every threshold -- indistinguishable from a genuinely
        # quiet market unless we say so.
        item_count = (
            await db.execute(select(func.count()).select_from(ItemType))
        ).scalar()
        if not item_count:
            logger.error(
                "No item types in the database: every region will report zero "
                "deals regardless of threshold. Static data load has not run."
            )

    deals = []
    for row in rows:
        jita_price = row.jita_price
        local_price = row.local_price

        if jita_price <= 0:
            continue

        # As a fraction of the Jita price: 200 ISK here against 1000 in Jita
        # is (1000-200)/1000 = 0.8, i.e. 80% off.
        discount_pct = (jita_price - local_price) / jita_price
        profit_per_unit = jita_price - local_price

        # These three are the *browse* filters -- what fills the table. The
        # separate, stricter alert filters live in deals_worth_alerting below.
        # `continue` skips to the next item in the loop.
        if discount_pct < user_config.discount_threshold:
            continue
        if profit_per_unit < user_config.min_profit_isk:
            continue
        if row.local_volume < user_config.min_volume:
            continue

        # Guard the divide: volume is nullable until the backfill runs, and a
        # zero-volume type would blow up rather than rank infinitely well.
        volume_m3 = row.volume_m3
        isk_per_m3 = (
            round(profit_per_unit / volume_m3, 2)
            if volume_m3 and volume_m3 > 0
            else None
        )

        deals.append(ArbitrageResult(
            type_id=row.type_id,
            type_name=row.type_name,
            category_id=row.category_id,
            category_name=TRACKABLE_CATEGORIES.get(row.category_id),
            local_price=round(local_price, 2),
            jita_price=round(jita_price, 2),
            discount_pct=round(discount_pct, 4),
            profit_per_unit=round(profit_per_unit, 2),
            volume_available=row.local_volume,
            volume_m3=volume_m3,
            isk_per_m3=isk_per_m3,
            region_id=region_id,
            region_name=region_name,
        ))

    # `key=lambda d: ...` tells sort what to compare -- here, each deal's
    # discount rather than the object itself. reverse=True puts the biggest
    # first. (A lambda is just a small unnamed function.)
    deals.sort(key=lambda d: d.discount_pct, reverse=True)

    logger.info(
        f"Found {len(deals)} arbitrage deals in {region_name} "
        f"(threshold: {user_config.discount_threshold:.0%})"
    )
    return deals


def deals_worth_alerting(
    deals: list[ArbitrageResult], user_config: UserConfig
) -> list[ArbitrageResult]:
    """Narrow browse results down to the ones worth interrupting someone for.

    The table's filters answer "what could I look at?"; these answer "what
    should make a noise?". Sharing one threshold for both forced the dashboard
    to be as quiet as the alerts, or the alerts as noisy as the dashboard.
    """
    # A list comprehension: "give me every d in deals where all the conditions
    # hold". The equivalent for-loop with an append would be several times as
    # long and no clearer.
    return [
        d
        for d in deals
        if d.discount_pct >= user_config.alert_discount_threshold
        and d.profit_per_unit >= user_config.alert_min_profit_isk
        and d.volume_available >= user_config.alert_min_volume
        # Blueprints are excluded unless explicitly enabled -- see the note on
        # UserConfig.alert_on_blueprints. Their headline discounts are an
        # artefact of originals and copies sharing a type_id, and left in they
        # dominate every alert.
        and (user_config.alert_on_blueprints or d.category_id != CATEGORY_BLUEPRINTS)
    ]


async def create_alerts_from_deals(
    db: AsyncSession,
    user_id: int,
    deals: list[ArbitrageResult],
) -> list[Alert]:
    """Save arbitrage deals as alerts, skipping ones already raised recently.

    Returns only the newly created alerts, so callers notify once per find
    rather than on every scan.

    Market data barely moves between scans, so without this the same deal was
    re-inserted and re-pushed every cycle -- with the scan on a 300s timer and
    a 20-alert ceiling, a busy region meant 20 notifications every 5 minutes,
    forever, for items already seen.
    """
    if not deals:
        return []

    # Anything raised more recently than this counts as "already seen".
    cutoff = datetime.utcnow() - ALERT_COOLDOWN
    recent = await db.execute(
        select(Alert.type_id, Alert.region_id).where(
            Alert.user_id == user_id,
            Alert.created_at >= cutoff,
        )
    )
    # A set of (type_id, region_id) pairs. Sets test membership in constant
    # time, so the `in` check in the loop below stays fast no matter how many
    # alerts already exist.
    already_raised = set(recent.all())

    alerts = []
    for deal in deals:
        if (deal.type_id, deal.region_id) in already_raised:
            continue

        alert = Alert(
            user_id=user_id,
            type_id=deal.type_id,
            type_name=deal.type_name,
            region_id=deal.region_id,
            region_name=deal.region_name,
            local_price=deal.local_price,
            jita_price=deal.jita_price,
            discount_pct=deal.discount_pct,
            potential_profit=deal.profit_per_unit,
        )
        db.add(alert)
        alerts.append(alert)
        # Guards against duplicates inside this batch too.
        already_raised.add((deal.type_id, deal.region_id))

    await db.commit()
    return alerts
