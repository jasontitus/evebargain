import json
import logging
from datetime import datetime

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import MarketCache
from app.models.item import ItemType
from app.models.user import UserConfig
from app.models.alert import Alert
from app.schemas.market import ArbitrageResult
from app.services.location import get_region_name
from app.utils.eve_constants import THE_FORGE_REGION_ID, TRACKABLE_CATEGORIES

logger = logging.getLogger(__name__)


async def find_arbitrage(
    db: AsyncSession,
    region_id: int,
    user_config: UserConfig,
) -> list[ArbitrageResult]:
    """Compare local region prices against Jita and find deals.

    Returns a list of ArbitrageResult for items that meet the user's
    discount threshold and filtering criteria.
    """
    tracked_categories = json.loads(user_config.tracked_category_ids)
    if not tracked_categories:
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

        discount_pct = (jita_price - local_price) / jita_price
        profit_per_unit = jita_price - local_price

        # Apply user filters
        if discount_pct < user_config.discount_threshold:
            continue
        if profit_per_unit < user_config.min_profit_isk:
            continue
        if row.local_volume < user_config.min_volume:
            continue

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
            region_id=region_id,
            region_name=region_name,
        ))

    # Sort by discount percentage descending
    deals.sort(key=lambda d: d.discount_pct, reverse=True)

    logger.info(
        f"Found {len(deals)} arbitrage deals in {region_name} "
        f"(threshold: {user_config.discount_threshold:.0%})"
    )
    return deals


async def create_alerts_from_deals(
    db: AsyncSession,
    user_id: int,
    deals: list[ArbitrageResult],
) -> list[Alert]:
    """Save new arbitrage deals as alerts in the database."""
    alerts = []
    for deal in deals:
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

    await db.commit()
    return alerts
