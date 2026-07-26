"""Pulling market orders from ESI and reducing them into the local cache.

THE SHAPE OF THE WORK
    ESI hands back raw sell orders -- one entry per listing, hundreds of
    thousands for a busy region. This app does not need them individually; it
    needs the single cheapest price per item. So each fetch is:

        fetch all pages  ->  aggregate to lowest price per item  ->  upsert

    "Upsert" means insert-or-update: the market_cache table has a uniqueness
    rule on (region, item), so a row that already exists is overwritten rather
    than duplicated. Doing that in one statement per batch is far faster than
    reading each row to decide between INSERT and UPDATE.

    The most valuable code here is the cheapest: is_cache_fresh. ESI serves
    these pages from a ~300 second cache, so refetching sooner returns
    byte-identical data. Skipping that is what took this app from roughly 6,800
    requests an hour down to a few hundred.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from app.config import settings
from app.models.market import MarketCache
from app.models.item import ItemType
from app.services.esi_client import esi_client
from app.utils.eve_constants import THE_FORGE_REGION_ID

logger = logging.getLogger(__name__)


async def fetch_region_sell_orders(
    region_id: int,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> dict[int, dict]:
    """Fetch all sell orders for a region and aggregate to lowest price per type.

    Returns dict mapping type_id -> {lowest_sell, order_count, volume_remain}
    """
    logger.info(f"Fetching sell orders for region {region_id}")
    all_orders = await esi_client.get_paginated(
        f"/markets/{region_id}/orders/",
        params={"order_type": "sell"},
        on_progress=on_progress,
    )

    # Aggregate: find lowest sell price and total volume per type
    # type_id -> running totals. Built in one pass over the orders rather than
    # sorting or grouping, which would cost more for no benefit.
    aggregated: dict[int, dict] = {}
    for order in all_orders:
        type_id = order["type_id"]
        price = order["price"]
        volume = order["volume_remain"]

        if type_id not in aggregated:
            aggregated[type_id] = {
                "lowest_sell": price,
                "order_count": 1,
                "volume_remain": volume,
            }
        else:
            entry = aggregated[type_id]
            if price < entry["lowest_sell"]:
                entry["lowest_sell"] = price
            entry["order_count"] += 1
            entry["volume_remain"] += volume

    logger.info(
        f"Region {region_id}: {len(all_orders)} orders, "
        f"{len(aggregated)} unique types"
    )
    return aggregated


async def is_cache_fresh(db: AsyncSession, region_id: int, ttl: int | None = None) -> bool:
    """True if this region was fetched recently enough to skip a refetch."""
    ttl = settings.market_cache_ttl if ttl is None else ttl
    result = await db.execute(
        select(func.max(MarketCache.fetched_at)).where(
            MarketCache.region_id == region_id
        )
    )
    last = result.scalar()
    if last is None:
        return False
    return (datetime.utcnow() - last).total_seconds() < ttl


async def update_market_cache(
    db: AsyncSession,
    region_id: int,
    type_filter: set[int] | None = None,
    force: bool = False,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
):
    """Fetch market data for a region and update the cache.

    If type_filter is provided, only cache entries for those type IDs.

    Skips the fetch entirely when the cached rows are still inside ESI's own
    cache window -- refetching then costs ~275 requests to receive identical
    data. Pass force=True for an explicit user-triggered refresh.
    """
    if not force and await is_cache_fresh(db, region_id):
        logger.info(
            f"Region {region_id}: cache still fresh "
            f"(<{settings.market_cache_ttl}s), skipping ESI fetch"
        )
        return

    aggregated = await fetch_region_sell_orders(region_id, on_progress=on_progress)
    now = datetime.utcnow()

    rows_to_upsert = []
    for type_id, data in aggregated.items():
        if type_filter and type_id not in type_filter:
            continue
        rows_to_upsert.append({
            "region_id": region_id,
            "type_id": type_id,
            "lowest_sell": data["lowest_sell"],
            "order_count": data["order_count"],
            "volume_remain": data["volume_remain"],
            "fetched_at": now,
        })

    if not rows_to_upsert:
        return

    # Written 500 rows at a time. One giant statement risks exceeding SQLite's
    # limit on bound variables, and one statement per row would mean thousands
    # of round trips.
    for batch_start in range(0, len(rows_to_upsert), 500):
        batch = rows_to_upsert[batch_start : batch_start + 500]
        stmt = sqlite_upsert(MarketCache).values(batch)
        # "If a row with this (region, item) already exists, update it instead
        # of failing." index_elements names the uniqueness rule to check
        # against -- the one declared on the MarketCache model.
        stmt = stmt.on_conflict_do_update(
            index_elements=["region_id", "type_id"],
            set_={
                "lowest_sell": stmt.excluded.lowest_sell,
                "order_count": stmt.excluded.order_count,
                "volume_remain": stmt.excluded.volume_remain,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
        await db.execute(stmt)

    await db.commit()
    logger.info(f"Updated {len(rows_to_upsert)} market cache entries for region {region_id}")


async def get_tracked_type_ids(db: AsyncSession, category_ids: list[int]) -> set[int]:
    """Every marketable item id in the given categories.

    Returns a `set` rather than a list because callers use it purely for `in`
    tests while filtering hundreds of thousands of orders -- that check is
    constant-time on a set and linear on a list.
    """
    result = await db.execute(
        select(ItemType.type_id).where(
            ItemType.category_id.in_(category_ids),
            ItemType.market_group_id.isnot(None),
            ItemType.published.is_(True),
        )
    )
    return set(result.scalars().all())


async def update_jita_cache(
    db: AsyncSession,
    type_ids: set[int] | None = None,
    force: bool = False,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
):
    """Update market cache specifically for The Forge (Jita) region."""
    await update_market_cache(
        db,
        THE_FORGE_REGION_ID,
        type_filter=type_ids,
        force=force,
        on_progress=on_progress,
    )
