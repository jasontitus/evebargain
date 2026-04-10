import logging
from functools import lru_cache

from app.services.esi_client import esi_client

logger = logging.getLogger(__name__)

# In-memory cache for system->region lookups (static data, never changes)
_system_region_cache: dict[int, int] = {}
_region_name_cache: dict[int, str] = {}


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

    Results are cached permanently (universe structure is static).
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
