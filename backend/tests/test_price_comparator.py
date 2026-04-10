"""Tests for the price comparison / arbitrage detection engine."""

import json
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.database import Base
from app.models.market import MarketCache
from app.models.item import ItemType, ItemCategory
from app.models.user import UserConfig
from app.services.price_comparator import find_arbitrage
from app.utils.eve_constants import THE_FORGE_REGION_ID


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        # Seed test data
        session.add(ItemCategory(category_id=6, name="Ships"))
        session.add(ItemType(
            type_id=100, name="Rifter", group_id=10,
            category_id=6, market_group_id=500, published=True,
        ))
        session.add(ItemType(
            type_id=101, name="Punisher", group_id=10,
            category_id=6, market_group_id=501, published=True,
        ))
        session.add(ItemType(
            type_id=102, name="Tristan", group_id=10,
            category_id=6, market_group_id=502, published=True,
        ))

        now = datetime.utcnow()

        # Jita prices (The Forge)
        session.add(MarketCache(
            region_id=THE_FORGE_REGION_ID, type_id=100,
            lowest_sell=1_000_000, order_count=50, volume_remain=100, fetched_at=now,
        ))
        session.add(MarketCache(
            region_id=THE_FORGE_REGION_ID, type_id=101,
            lowest_sell=800_000, order_count=30, volume_remain=80, fetched_at=now,
        ))
        session.add(MarketCache(
            region_id=THE_FORGE_REGION_ID, type_id=102,
            lowest_sell=500_000, order_count=40, volume_remain=60, fetched_at=now,
        ))

        # Local region (Devoid = 10000036) - Rifter is 20% cheaper, Punisher 5%, Tristan same
        local_region = 10000036
        session.add(MarketCache(
            region_id=local_region, type_id=100,
            lowest_sell=800_000, order_count=5, volume_remain=10, fetched_at=now,
        ))
        session.add(MarketCache(
            region_id=local_region, type_id=101,
            lowest_sell=760_000, order_count=3, volume_remain=8, fetched_at=now,
        ))
        session.add(MarketCache(
            region_id=local_region, type_id=102,
            lowest_sell=500_000, order_count=2, volume_remain=5, fetched_at=now,
        ))

        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_find_arbitrage_basic(db):
    """Test that deals meeting the threshold are found."""
    config = UserConfig(
        id=1, user_id=1,
        discount_threshold=0.10,
        tracked_category_ids=json.dumps([6]),
        min_volume=1,
        min_profit_isk=0,
    )

    deals = await find_arbitrage(db, 10000036, config)

    # Only Rifter should match (20% discount >= 10% threshold)
    assert len(deals) == 1
    assert deals[0].type_name == "Rifter"
    assert deals[0].discount_pct == pytest.approx(0.20, abs=0.01)
    assert deals[0].profit_per_unit == pytest.approx(200_000, abs=1)


@pytest.mark.asyncio
async def test_find_arbitrage_low_threshold(db):
    """Test with a lower threshold to find more deals."""
    config = UserConfig(
        id=1, user_id=1,
        discount_threshold=0.04,
        tracked_category_ids=json.dumps([6]),
        min_volume=1,
        min_profit_isk=0,
    )

    deals = await find_arbitrage(db, 10000036, config)

    # Rifter (20%) and Punisher (5%) should match
    assert len(deals) == 2
    names = {d.type_name for d in deals}
    assert "Rifter" in names
    assert "Punisher" in names


@pytest.mark.asyncio
async def test_find_arbitrage_min_profit_filter(db):
    """Test that min_profit_isk filter works."""
    config = UserConfig(
        id=1, user_id=1,
        discount_threshold=0.04,
        tracked_category_ids=json.dumps([6]),
        min_volume=1,
        min_profit_isk=100_000,
    )

    deals = await find_arbitrage(db, 10000036, config)

    # Only Rifter has 200k profit; Punisher has 40k
    assert len(deals) == 1
    assert deals[0].type_name == "Rifter"


@pytest.mark.asyncio
async def test_find_arbitrage_empty_categories(db):
    """Test with no tracked categories returns empty."""
    config = UserConfig(
        id=1, user_id=1,
        discount_threshold=0.05,
        tracked_category_ids=json.dumps([]),
        min_volume=1,
        min_profit_isk=0,
    )

    deals = await find_arbitrage(db, 10000036, config)
    assert len(deals) == 0
