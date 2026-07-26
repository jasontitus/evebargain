"""Jump-distance measurement for the nearby-region scan."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services import jumps


def _resp(payload):
    return type("R", (), {"json": lambda self: payload})()


@pytest.fixture(autouse=True)
def _clear_caches():
    jumps._region_samples.clear()
    jumps._route_cache.clear()
    yield
    jumps._region_samples.clear()
    jumps._route_cache.clear()


@pytest.mark.asyncio
async def test_rejects_an_unknown_route_flag():
    with pytest.raises(ValueError):
        await jumps.region_distances(30004083, flag="banana")


@pytest.mark.asyncio
async def test_samples_are_spread_across_constellations():
    """Taking the first N would cluster on one side of the region."""
    constellations = list(range(100, 120))  # 20 constellations

    async def fake_get(path, **kwargs):
        if "/regions/" in path:
            return _resp({"constellations": constellations})
        cid = int(path.split("/constellations/")[1].strip("/"))
        return _resp({"systems": [cid * 10]})

    with patch.object(jumps, "esi_client") as client:
        client.get = AsyncMock(side_effect=fake_get)
        samples = await jumps._sample_systems(10000052)

    assert len(samples) == jumps.SAMPLES_PER_REGION
    # Stepping means the picks span the list rather than bunching at the front.
    assert samples == [1000, 1050, 1100, 1150]


@pytest.mark.asyncio
async def test_region_distance_is_the_nearest_sample():
    jumps._region_samples[10000052] = [111, 222, 333]
    jumps._route_cache[(30004083, 111, "shortest")] = 9
    jumps._route_cache[(30004083, 222, "shortest")] = 4
    jumps._route_cache[(30004083, 333, "shortest")] = 7

    with patch.object(jumps, "list_regions", AsyncMock(return_value={10000052: "Kador"})), \
         patch.object(jumps, "resolve_system_to_region", AsyncMock(return_value=99999)):
        distances = await jumps.region_distances(30004083, flag="shortest")

    assert distances[10000052] == 4


@pytest.mark.asyncio
async def test_current_region_is_always_zero_jumps():
    """It reported Kador as 3 jumps while the character was sitting in Kador."""
    jumps._region_samples[10000052] = [111]
    jumps._route_cache[(30004083, 111, "shortest")] = 3

    with patch.object(jumps, "list_regions", AsyncMock(return_value={10000052: "Kador"})), \
         patch.object(jumps, "resolve_system_to_region", AsyncMock(return_value=10000052)):
        distances = await jumps.region_distances(30004083, flag="shortest")

    assert distances[10000052] == 0


@pytest.mark.asyncio
async def test_unreachable_regions_are_omitted_not_zero():
    """A highsec-only route into nullsec has no answer -- that isn't 'here'."""
    jumps._region_samples[10000052] = [111]
    jumps._route_cache[(30004083, 111, "secure")] = None

    with patch.object(jumps, "list_regions", AsyncMock(return_value={10000052: "Kador"})), \
         patch.object(jumps, "resolve_system_to_region", AsyncMock(return_value=99999)):
        distances = await jumps.region_distances(30004083, flag="secure")

    assert 10000052 not in distances


@pytest.mark.asyncio
async def test_max_jumps_filters_out_distant_regions():
    jumps._region_samples[1] = [111]
    jumps._region_samples[2] = [222]
    jumps._route_cache[(30004083, 111, "shortest")] = 5
    jumps._route_cache[(30004083, 222, "shortest")] = 25

    with patch.object(jumps, "list_regions", AsyncMock(return_value={1: "Near", 2: "Far"})), \
         patch.object(jumps, "resolve_system_to_region", AsyncMock(return_value=99999)):
        distances = await jumps.region_distances(30004083, flag="shortest", max_jumps=10)

    assert distances == {1: 5}
