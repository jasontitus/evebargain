"""Region browsing: the dropdown lets you look at a market you aren't in."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services import location


@pytest.fixture(autouse=True)
def _clear_region_cache():
    """list_regions memoizes for the process lifetime; isolate each test."""
    location._all_regions_cache.clear()
    yield
    location._all_regions_cache.clear()


@pytest.mark.asyncio
async def test_list_regions_drops_wormhole_space():
    """W-space and abyssal regions have no NPC stations, so no market orders."""
    ids = [10000002, 10000052, 11000001, 12000001]
    names = [
        {"id": 10000002, "name": "The Forge", "category": "region"},
        {"id": 10000052, "name": "Kador", "category": "region"},
    ]

    with patch.object(location, "esi_client") as client:
        client.get = AsyncMock(return_value=type("R", (), {"json": lambda self: ids})())
        client.post = AsyncMock(
            return_value=type("R", (), {"json": lambda self: names})()
        )
        regions = await location.list_regions()

        # Only the two k-space IDs should have been sent for name resolution.
        assert client.post.await_args.kwargs["json"] == [10000002, 10000052]

    assert regions == {10000002: "The Forge", 10000052: "Kador"}


@pytest.mark.asyncio
async def test_list_regions_is_cached_after_first_call():
    ids = [10000052]
    names = [{"id": 10000052, "name": "Kador", "category": "region"}]

    with patch.object(location, "esi_client") as client:
        client.get = AsyncMock(return_value=type("R", (), {"json": lambda self: ids})())
        client.post = AsyncMock(
            return_value=type("R", (), {"json": lambda self: names})()
        )
        await location.list_regions()
        await location.list_regions()
        await location.list_regions()

        # The universe doesn't gain regions -- one round trip is enough.
        assert client.get.await_count == 1
        assert client.post.await_count == 1
