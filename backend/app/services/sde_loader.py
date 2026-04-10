"""Load EVE static data (item types, categories, groups) from ESI."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from app.models.item import ItemType, ItemCategory
from app.services.esi_client import esi_client
from app.utils.eve_constants import TRACKABLE_CATEGORIES

logger = logging.getLogger(__name__)


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

    types_loaded = 0
    for group_id in group_ids:
        try:
            group_resp = await esi_client.get(f"/universe/groups/{group_id}/")
            group_data = group_resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch group {group_id}: {e}")
            continue

        type_ids = group_data.get("types", [])

        for type_id in type_ids:
            try:
                type_resp = await esi_client.get(f"/universe/types/{type_id}/")
                type_data = type_resp.json()
            except Exception as e:
                logger.warning(f"Failed to fetch type {type_id}: {e}")
                continue

            if not type_data.get("published", False):
                continue

            stmt = sqlite_upsert(ItemType).values(
                type_id=type_id,
                name=type_data.get("name", f"Unknown #{type_id}"),
                group_id=group_id,
                category_id=category_id,
                market_group_id=type_data.get("market_group_id"),
                published=type_data.get("published", True),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["type_id"],
                set_={
                    "name": stmt.excluded.name,
                    "group_id": stmt.excluded.group_id,
                    "category_id": stmt.excluded.category_id,
                    "market_group_id": stmt.excluded.market_group_id,
                    "published": stmt.excluded.published,
                },
            )
            await db.execute(stmt)
            types_loaded += 1

        # Commit per group to avoid huge transactions
        await db.commit()

    logger.info(f"Loaded {types_loaded} types for category {category_id}")


async def load_all_static_data(db: AsyncSession):
    """Load all static data needed for the application.

    This is run on first boot or via a management command.
    Skips loading if data already exists.
    """
    # Check if we already have data
    count = await db.execute(select(func.count(ItemType.type_id)))
    existing = count.scalar()
    if existing and existing > 100:
        logger.info(f"Static data already loaded ({existing} types), skipping")
        return

    logger.info("Loading EVE static data from ESI (this may take a while)...")

    await load_categories(db)

    for category_id in TRACKABLE_CATEGORIES:
        logger.info(f"Loading types for category {category_id} ({TRACKABLE_CATEGORIES[category_id]})")
        await load_types_for_category(db, category_id)

    final_count = await db.execute(select(func.count(ItemType.type_id)))
    logger.info(f"Static data load complete: {final_count.scalar()} total types")
