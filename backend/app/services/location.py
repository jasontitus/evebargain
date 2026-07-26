"""Where the player's character is, and what the regions are called.

EVE's map is a hierarchy: solar system -> constellation -> region. ESI only
tells you the system a character is in, so finding the region means two more
lookups up that chain.

CACHING, AND WHY IT IS SAFE HERE
    Every lookup in this file is memoized in a module-level dictionary and never
    expires. That would be reckless for prices, but this is universe geometry:
    systems do not move between regions, and regions do not get renamed. The
    location poller runs every 30 seconds, so without caching it would ask ESI
    the same three questions forever.
"""

import asyncio
import logging

from app.services.esi_client import esi_client

logger = logging.getLogger(__name__)

# In-memory cache for system->region lookups (static data, never changes)
_system_region_cache: dict[int, int] = {}
_region_name_cache: dict[int, str] = {}

# id -> name for every region with a real market, built once per process.
_all_regions_cache: dict[int, str] = {}
_all_regions_lock = asyncio.Lock()

# Wormhole space starts at 11000000, and abyssal/void regions above it have no
# NPC stations and so no market orders. Listing them would be 44 dead entries.
K_SPACE_MAX_REGION_ID = 11000000


async def list_regions() -> dict[int, str]:
    """All k-space region IDs mapped to names.

    Two ESI calls total, then cached for the life of the process -- the
    universe doesn't get new regions. Names are resolved in a single bulk
    /universe/names/ POST rather than one GET per region.
    """
    if _all_regions_cache:
        return _all_regions_cache

    # A lock prevents two callers arriving at once from both deciding the cache
    # is empty and both doing the work. Only one gets in; the other waits.
    async with _all_regions_lock:
        # ...and then finds it already populated, hence this second check.
        # (Checking twice, either side of the lock, is a standard pattern: the
        # first check avoids taking the lock in the common case.)
        if _all_regions_cache:
            return _all_regions_cache

        response = await esi_client.get("/universe/regions/")
        region_ids = [r for r in response.json() if r < K_SPACE_MAX_REGION_ID]

        resolved = await esi_client.post("/universe/names/", json=region_ids)
        for entry in resolved.json():
            if entry.get("category") == "region":
                _all_regions_cache[entry["id"]] = entry["name"]
                _region_name_cache[entry["id"]] = entry["name"]

        logger.info(f"Loaded {len(_all_regions_cache)} k-space regions")

    return _all_regions_cache


async def get_character_location(character_id: int, token: str) -> dict:
    """Get character's current solar system.

    Returns dict with solar_system_id, and optionally station_id/structure_id.
    """
    response = await esi_client.get(
        f"/characters/{character_id}/location/",
        token=token,
    )
    return response.json()


async def resolve_system_to_region(system_id: int) -> int:
    """Resolve a solar system ID to its region ID.

    Two hops up the map hierarchy: system -> constellation -> region. Results
    are cached permanently, since the universe structure is static.
    """
    if system_id in _system_region_cache:
        return _system_region_cache[system_id]

    # Get system info -> constellation_id
    sys_resp = await esi_client.get(f"/universe/systems/{system_id}/")
    constellation_id = sys_resp.json()["constellation_id"]

    # Get constellation info -> region_id
    const_resp = await esi_client.get(f"/universe/constellations/{constellation_id}/")
    region_id = const_resp.json()["region_id"]

    _system_region_cache[system_id] = region_id
    return region_id


async def get_region_name(region_id: int) -> str:
    """Get the human-readable name for a region."""
    if region_id in _region_name_cache:
        return _region_name_cache[region_id]

    response = await esi_client.get(f"/universe/regions/{region_id}/")
    name = response.json()["name"]
    _region_name_cache[region_id] = name
    return name


async def detect_region_change(
    character_id: int, token: str, current_region_id: int | None
) -> tuple[int | None, int | None, bool]:
    """Check if the character has moved to a new region.

    Returns (system_id, region_id, changed) where changed is True
    if the region differs from current_region_id.

    Returning a tuple lets the caller unpack three values in one line:
        system_id, region_id, changed = await detect_region_change(...)

    `changed` is what triggers a market scan -- moving within a region does not
    change what is for sale there, so only a region crossing is worth acting on.
    """
    location = await get_character_location(character_id, token)
    system_id = location["solar_system_id"]
    region_id = await resolve_system_to_region(system_id)
    changed = region_id != current_region_id

    if changed:
        region_name = await get_region_name(region_id)
        logger.info(
            f"Character {character_id} entered new region: "
            f"{region_name} ({region_id})"
        )

    return system_id, region_id, changed
