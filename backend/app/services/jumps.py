"""Jump distances from the character's system to other regions.

ESI has no "regions within N jumps" endpoint, so this routes to a sample of
systems per region and keeps the shortest. Routing to every system would be
thousands of requests per origin; routing to just one would report a region as
far away because the one system picked happened to be on its far side.

Everything here is static topology, so results are memoized for the process
lifetime and keyed by (origin, destination, flag).
"""

import asyncio
import logging

from app.services.esi_client import esi_client
from app.services.location import list_regions, resolve_system_to_region

logger = logging.getLogger(__name__)

# Route preference. "secure" sticks to highsec and can be dramatically longer:
# Kador to Jita is 6 jumps shortest but 50 jumps highsec-only.
ROUTE_FLAGS = ("shortest", "secure", "insecure")

# Systems sampled per region. Spread across the region's constellations, so a
# larger number tightens the estimate at a linear cost in requests.
SAMPLES_PER_REGION = 4

# region_id -> sampled system ids
_region_samples: dict[int, list[int]] = {}
_samples_lock = asyncio.Lock()

# (origin, destination, flag) -> jumps, or None when unreachable
_route_cache: dict[tuple[int, int, str], int | None] = {}


async def _sample_systems(region_id: int) -> list[int]:
    """Pick a spread of systems in a region to measure distance against."""
    if region_id in _region_samples:
        return _region_samples[region_id]

    try:
        resp = await esi_client.get(f"/universe/regions/{region_id}/")
        constellations = resp.json().get("constellations", [])
    except Exception as e:
        logger.warning(f"Could not read region {region_id}: {e}")
        return []

    if not constellations:
        return []

    # Spread the picks across the constellation list rather than taking the
    # first N, which would cluster on one side of the region.
    step = max(1, len(constellations) // SAMPLES_PER_REGION)
    chosen = constellations[::step][:SAMPLES_PER_REGION]

    async def first_system(constellation_id: int) -> int | None:
        try:
            r = await esi_client.get(f"/universe/constellations/{constellation_id}/")
            systems = r.json().get("systems", [])
            return systems[0] if systems else None
        except Exception:
            return None

    results = await asyncio.gather(*[first_system(c) for c in chosen])
    samples = [s for s in results if s]
    _region_samples[region_id] = samples
    return samples


async def _route_jumps(origin: int, destination: int, flag: str) -> int | None:
    """Jump count between two systems, or None if there's no route."""
    key = (origin, destination, flag)
    if key in _route_cache:
        return _route_cache[key]

    try:
        resp = await esi_client.get(
            f"/route/{origin}/{destination}/", params={"flag": flag}
        )
        # The route includes the origin, so hops is one less than systems.
        jumps = max(0, len(resp.json()) - 1)
    except Exception:
        # 404 means no route exists under this flag -- normal for highsec-only
        # routing into nullsec, not an error worth surfacing.
        jumps = None

    _route_cache[key] = jumps
    return jumps


async def region_distances(
    origin_system_id: int,
    flag: str = "shortest",
    max_jumps: int | None = None,
) -> dict[int, int]:
    """Map region_id -> jumps from origin, for every reachable k-space region.

    Regions with no route under the chosen flag are omitted entirely rather
    than reported as distance zero.
    """
    if flag not in ROUTE_FLAGS:
        raise ValueError(f"flag must be one of {ROUTE_FLAGS}")

    regions = await list_regions()

    async with _samples_lock:
        # Building the sample map is ~1 request per region plus one per sampled
        # constellation. Static, so this cost is paid once per process.
        await asyncio.gather(*[_sample_systems(r) for r in regions])

    async def nearest(region_id: int) -> tuple[int, int | None]:
        samples = _region_samples.get(region_id) or []
        if not samples:
            return region_id, None
        hops = await asyncio.gather(
            *[_route_jumps(origin_system_id, s, flag) for s in samples]
        )
        reachable = [h for h in hops if h is not None]
        return region_id, min(reachable) if reachable else None

    measured = await asyncio.gather(*[nearest(r) for r in regions])

    distances = {rid: jumps for rid, jumps in measured if jumps is not None}

    # The sampled systems are spread across each region, so the character's own
    # region measures as the distance to whichever sample was picked -- it
    # reported Kador as 3 jumps away while sitting in Kador. Being in a region
    # is zero jumps by definition, so override it.
    try:
        origin_region = await resolve_system_to_region(origin_system_id)
        if origin_region in regions:
            distances[origin_region] = 0
    except Exception:
        logger.warning("Could not resolve origin region for %s", origin_system_id)
    if max_jumps is not None:
        distances = {r: j for r, j in distances.items() if j <= max_jumps}
    return distances
