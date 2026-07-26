"""The cache-freshness guard is what keeps the app from re-pulling ~275 pages
of Jita orders every five minutes to receive byte-identical data."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.models.market import MarketCache
from app.services.market_fetcher import is_cache_fresh, update_market_cache

REGION = 10000002


async def _seed(db, age_seconds: float):
    db.add(
        MarketCache(
            region_id=REGION,
            type_id=34,
            lowest_sell=5.0,
            order_count=1,
            volume_remain=100,
            fetched_at=datetime.utcnow() - timedelta(seconds=age_seconds),
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_cache_is_stale_when_region_never_fetched(db_session):
    assert await is_cache_fresh(db_session, REGION) is False


@pytest.mark.asyncio
async def test_cache_is_fresh_inside_the_ttl(db_session):
    await _seed(db_session, age_seconds=10)
    assert await is_cache_fresh(db_session, REGION) is True


@pytest.mark.asyncio
async def test_cache_is_stale_past_the_ttl(db_session):
    await _seed(db_session, age_seconds=settings.market_cache_ttl + 30)
    assert await is_cache_fresh(db_session, REGION) is False


@pytest.mark.asyncio
async def test_fresh_cache_skips_the_esi_fetch(db_session):
    await _seed(db_session, age_seconds=10)
    with patch(
        "app.services.market_fetcher.fetch_region_sell_orders", new_callable=AsyncMock
    ) as fetch:
        await update_market_cache(db_session, REGION)
    fetch.assert_not_called()


@pytest.mark.asyncio
async def test_stale_cache_triggers_a_fetch(db_session):
    await _seed(db_session, age_seconds=settings.market_cache_ttl + 30)
    with patch(
        "app.services.market_fetcher.fetch_region_sell_orders", new_callable=AsyncMock
    ) as fetch:
        fetch.return_value = {34: {"lowest_sell": 6.0, "order_count": 2, "volume_remain": 50}}
        await update_market_cache(db_session, REGION)
    fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_force_bypasses_a_fresh_cache(db_session):
    """The manual Refresh button must still do something."""
    await _seed(db_session, age_seconds=10)
    with patch(
        "app.services.market_fetcher.fetch_region_sell_orders", new_callable=AsyncMock
    ) as fetch:
        fetch.return_value = {34: {"lowest_sell": 6.0, "order_count": 2, "volume_remain": 50}}
        await update_market_cache(db_session, REGION, force=True)
    fetch.assert_awaited_once()
