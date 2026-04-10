import logging
from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from app.models.market import MarketCache
from app.models.item import ItemType
from app.services.esi_client import esi_client
from app.utils.eve_constants import THE_FORGE_REGION_ID

logger = logging.getLogger(__name__)


async def fetch_region_sell_orders(region_id: int) -> dict[int, dict]:
    """Fetch all sell orders for a region and aggregate to lowest price per type.

    Returns dict mapping type_id -> {lowest_sell, order_count, volume_remain}
    """
    logger.info(f"Fetching sell orders for region {region_id}")
    all_orders = await esi_client.get_paginated(
        f"/markets/{region_id}/orders/",
        params={"order_type": "sell"},
    )

    # Aggregate: find lowest sell price and total volume per type
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


async def update_market_cache(
    db: AsyncSession, region_id: int, type_filter: set[int] | None = None
):
    """Fetch market data for a region and update the cache.

    If type_filter is provided, only cache entries for those type IDs.
    """
    aggregated = await fetch_region_sell_orders(region_id)
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

    # Batch upsert using SQLite INSERT OR REPLACE
    for batch_start in range(0, len(rows_to_upsert), 500):
        batch = rows_to_upsert[batch_start : batch_start + 500]
        stmt = sqlite_upsert(MarketCache).values(batch)
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
    """Get all marketable type IDs for the given categories."""
    result = await db.execute(
        select(ItemType.type_id).where(
            ItemType.category_id.in_(category_ids),
            ItemType.market_group_id.isnot(None),
            ItemType.published.is_(True),
        )
    )
    return set(result.scalars().all())


async def update_jita_cache(db: AsyncSession, type_ids: set[int] | None = None):
    """Update market cache specifically for The Forge (Jita) region."""
    await update_market_cache(db, THE_FORGE_REGION_ID, type_filter=type_ids)
