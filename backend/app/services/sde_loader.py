"""Load EVE static data (item types, categories, groups) from ESI."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from app.models.item import ItemType, ItemCategory
from app.services.esi_client import esi_client
from app.utils.eve_constants import TRACKABLE_CATEGORIES

logger = logging.getLogger(__name__)

# How many /universe/types/ lookups to have outstanding per batch. Actual
# concurrency is capped by the ESI client's semaphore; this bounds the task
# list and keeps each transaction a reasonable size.
TYPE_FETCH_CHUNK = 400


def packaged_volume(type_data: dict) -> float | None:
    """Cubic metres per unit as it sits on the market, i.e. packaged.

    Ships report an assembled `volume` an order of magnitude larger than their
    `packaged_volume`, and what you buy from a station is packaged -- so
    preferring the assembled figure would misprice every hauling decision.
    """
    volume = type_data.get("packaged_volume")
    if volume is None:
        volume = type_data.get("volume")
    return volume


async def load_categories(db: AsyncSession):
    """Load item categories into the database."""
    for cat_id, cat_name in TRACKABLE_CATEGORIES.items():
        stmt = sqlite_upsert(ItemCategory).values(
            category_id=cat_id, name=cat_name
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["category_id"],
            set_={"name": stmt.excluded.name},
        )
        await db.execute(stmt)
    await db.commit()
    logger.info(f"Loaded {len(TRACKABLE_CATEGORIES)} item categories")


async def load_types_for_category(db: AsyncSession, category_id: int):
    """Load all item types for a specific category from ESI.

    Fetches the category -> groups -> types hierarchy.
    """
    # Get groups in this category
    try:
        cat_resp = await esi_client.get(f"/universe/categories/{category_id}/")
        cat_data = cat_resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch category {category_id}: {e}")
        return

    group_ids = cat_data.get("groups", [])
    logger.info(f"Category {category_id} ({cat_data.get('name')}): {len(group_ids)} groups")

    # Groups first, concurrently. The ESI client's semaphore is what actually
    # bounds this; issuing them one at a time just left it idle.
    async def fetch_group(group_id: int) -> tuple[int, list[int]]:
        try:
            resp = await esi_client.get(f"/universe/groups/{group_id}/")
            return group_id, resp.json().get("types", [])
        except Exception as e:
            logger.error(f"Failed to fetch group {group_id}: {e}")
            return group_id, []

    groups = await asyncio.gather(*[fetch_group(g) for g in group_ids])

    # (type_id, group_id) for every type in the category.
    pending = [(tid, gid) for gid, type_ids in groups for tid in type_ids]
    logger.info(f"Category {category_id}: {len(pending)} types to fetch")

    async def fetch_type(type_id: int, group_id: int) -> tuple[int, int, dict | None]:
        try:
            resp = await esi_client.get(f"/universe/types/{type_id}/")
            return type_id, group_id, resp.json()
        except Exception as e:
            logger.warning(f"Failed to fetch type {type_id}: {e}")
            return type_id, group_id, None

    types_loaded = 0
    # Chunked so a category with thousands of types doesn't build one enormous
    # task list or one enormous transaction.
    for start in range(0, len(pending), TYPE_FETCH_CHUNK):
        chunk = pending[start : start + TYPE_FETCH_CHUNK]
        fetched = await asyncio.gather(*[fetch_type(t, g) for t, g in chunk])

        for type_id, group_id, type_data in fetched:
            if not type_data or not type_data.get("published", False):
                continue

            stmt = sqlite_upsert(ItemType).values(
                type_id=type_id,
                name=type_data.get("name", f"Unknown #{type_id}"),
                group_id=group_id,
                category_id=category_id,
                market_group_id=type_data.get("market_group_id"),
                published=type_data.get("published", True),
                volume=packaged_volume(type_data),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["type_id"],
                set_={
                    "name": stmt.excluded.name,
                    "group_id": stmt.excluded.group_id,
                    "category_id": stmt.excluded.category_id,
                    "market_group_id": stmt.excluded.market_group_id,
                    "published": stmt.excluded.published,
                    "volume": stmt.excluded.volume,
                },
            )
            await db.execute(stmt)
            types_loaded += 1

        await db.commit()
        logger.info(
            f"Category {category_id}: {min(start + TYPE_FETCH_CHUNK, len(pending))}"
            f"/{len(pending)} types processed"
        )

    logger.info(f"Loaded {types_loaded} types for category {category_id}")


async def load_all_static_data(db: AsyncSession, force: bool = False):
    """Load all static data needed for the application.

    This is run on first boot or via a management command.
    Skips loading if data already exists.
    """
    logger.info("Loading EVE static data from ESI (this may take a while)...")

    await load_categories(db)

    # Skip per category rather than globally. A global row-count guard treats a
    # run that died halfway as complete, which leaves the catalogue permanently
    # short and every affected category silently dealless. Upserts are
    # idempotent, so re-running an incomplete category is safe.
    for category_id, category_name in TRACKABLE_CATEGORIES.items():
        existing = (
            await db.execute(
                select(func.count(ItemType.type_id)).where(
                    ItemType.category_id == category_id
                )
            )
        ).scalar()

        if existing and not force:
            logger.info(
                f"Category {category_id} ({category_name}) already has "
                f"{existing} types, skipping"
            )
            continue

        logger.info(f"Loading types for category {category_id} ({category_name})")
        await load_types_for_category(db, category_id)

    final_count = await db.execute(select(func.count(ItemType.type_id)))
    logger.info(f"Static data load complete: {final_count.scalar()} total types")


async def backfill_volumes(db: AsyncSession) -> int:
    """Fill in volume for catalogue rows loaded before the column existed.

    Only touches rows where it is still NULL, so this is resumable and costs
    nothing once complete -- it re-reads /universe/types/ for those rows only,
    rather than reloading the whole catalogue.
    """
    missing = (
        await db.execute(
            select(ItemType.type_id).where(ItemType.volume.is_(None))
        )
    ).scalars().all()

    if not missing:
        return 0

    logger.info(f"Backfilling volume for {len(missing)} item types")

    async def fetch(type_id: int) -> tuple[int, float | None]:
        try:
            resp = await esi_client.get(f"/universe/types/{type_id}/")
            return type_id, packaged_volume(resp.json())
        except Exception:
            return type_id, None

    filled = 0
    for start in range(0, len(missing), TYPE_FETCH_CHUNK):
        chunk = missing[start : start + TYPE_FETCH_CHUNK]
        for type_id, volume in await asyncio.gather(*[fetch(t) for t in chunk]):
            if volume is None:
                continue
            await db.execute(
                update(ItemType).where(ItemType.type_id == type_id).values(volume=volume)
            )
            filled += 1
        await db.commit()
        logger.info(
            f"Volume backfill: {min(start + TYPE_FETCH_CHUNK, len(missing))}"
            f"/{len(missing)} processed"
        )

    logger.info(f"Volume backfill complete: {filled} types now have a volume")
    return filled
