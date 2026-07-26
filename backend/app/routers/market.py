import logging
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserConfig
from app.models.market import MarketCache
from app.schemas.market import (
    ArbitrageResult,
    MarketDealResponse,
    NearbyDealsResponse,
    RegionListResponse,
    RegionSummary,
)
from app.services.price_comparator import find_arbitrage
from app.services.location import get_region_name, list_regions as get_all_regions
from app.services.jumps import region_distances
from app.services.market_fetcher import (
    get_tracked_type_ids,
    update_jita_cache,
    update_market_cache,
)
from app.services.notification import ws_manager
from app.tasks.scheduler import scan_market_for_user
from app.utils.eve_constants import THE_FORGE_REGION_ID

logger = logging.getLogger(__name__)

# A 15-jump radius can cover a large slice of the map, and every region costs
# an order-book fetch. Cap the work and tell the caller when the cap bit.
MAX_NEARBY_REGIONS = 25

router = APIRouter(prefix="/api/market", tags=["market"])


async def _get_authenticated_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/regions", response_model=RegionListResponse)
async def list_market_regions(
    max_jumps: int | None = None,
    flag: str = "shortest",
    user: User = Depends(_get_authenticated_user),
):
    """Every k-space region, for the browse-elsewhere dropdown.

    The Forge is omitted: it's the reference market every other region is
    priced against, so there is nothing to compare it to. Offering it would
    just be an option that always errors.

    Passing max_jumps annotates each region with its distance from the
    character's current system and drops the ones out of range.
    """
    regions = await get_all_regions()
    distances: dict[int, int] = {}

    if max_jumps is not None:
        if not user.current_system_id:
            raise HTTPException(
                status_code=400,
                detail="Location not yet detected, so distances can't be measured.",
            )
        try:
            distances = await region_distances(
                user.current_system_id, flag=flag, max_jumps=max_jumps
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    summaries = [
        RegionSummary(region_id=rid, name=name, jumps=distances.get(rid))
        for rid, name in regions.items()
        if rid != THE_FORGE_REGION_ID
        and (max_jumps is None or rid in distances)
    ]
    # Nearest first when distances are known; otherwise alphabetical.
    if max_jumps is not None:
        summaries.sort(key=lambda r: (r.jumps if r.jumps is not None else 999, r.name))
    else:
        summaries.sort(key=lambda r: r.name)

    return RegionListResponse(
        regions=summaries,
        current_region_id=user.current_region_id,
    )


@router.get("/nearby", response_model=NearbyDealsResponse)
async def nearby_deals(
    max_jumps: int = 10,
    flag: str = "shortest",
    sort_by: str = "discount",
    user: User = Depends(_get_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Arbitrage across every region within max_jumps of the character.

    Each region still needs its order book, so this is the expensive endpoint.
    The cache-freshness guard means a repeat scan within the ESI cache window
    costs nothing, and the scan is capped at MAX_NEARBY_REGIONS.
    """
    if not user.current_system_id:
        raise HTTPException(
            status_code=400,
            detail="Location not yet detected. Make sure you're logged into EVE.",
        )

    result = await db.execute(select(UserConfig).where(UserConfig.user_id == user.id))
    user_config = result.scalar_one_or_none()
    if not user_config:
        raise HTTPException(status_code=400, detail="Config not found")

    # Emit before any work starts. Measuring distances is a few hundred route
    # lookups and runs ~15s cold, and the Jita pull follows it -- so the first
    # progress message used to arrive 20s after the button was pressed, which
    # read as the scan not having started at all.
    await ws_manager.send_progress(
        user.id, "distances", "measuring jump distances", 0, 1
    )

    async def distance_progress(completed: int, total: int):
        await ws_manager.send_progress(
            user.id, "distances", "measuring jump distances", completed, total
        )

    try:
        distances = await region_distances(
            user.current_system_id,
            flag=flag,
            max_jumps=max_jumps,
            on_progress=distance_progress,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # The Forge is the reference market, not a destination.
    targets = sorted(
        ((r, j) for r, j in distances.items() if r != THE_FORGE_REGION_ID),
        key=lambda rj: rj[1],
    )
    in_range = len(targets)
    truncated = in_range > MAX_NEARBY_REGIONS
    if truncated:
        logger.info(
            f"Nearby scan capped at {MAX_NEARBY_REGIONS} of {in_range} regions "
            f"within {max_jumps} jumps"
        )
        targets = targets[:MAX_NEARBY_REGIONS]

    tracked = json.loads(user_config.tracked_category_ids)
    type_ids = await get_tracked_type_ids(db, tracked)

    # Jita once up front -- every comparison needs it. Reported too: cold it's
    # ~275 pages, which is otherwise another silent stretch before the
    # per-region loop starts.
    async def jita_progress(completed: int, total: int):
        await ws_manager.send_progress(user.id, "jita", "Jita", completed, total)

    await update_jita_cache(db, type_ids=type_ids, on_progress=jita_progress)

    all_deals: list[ArbitrageResult] = []
    for index, (region_id, jumps) in enumerate(targets, start=1):
        await ws_manager.send_progress(
            user.id, "nearby", f"{index} of {len(targets)} regions", index, len(targets)
        )
        try:
            await update_market_cache(db, region_id, type_filter=type_ids)
            region_deals = await find_arbitrage(db, region_id, user_config)
        except Exception:
            logger.exception(f"Nearby scan failed for region {region_id}")
            continue

        for deal in region_deals:
            deal.jumps = jumps
        all_deals.extend(region_deals)

    await ws_manager.send_progress(
        user.id, "nearby", "done", len(targets), len(targets), done=True
    )

    if sort_by == "profit":
        all_deals.sort(key=lambda d: d.profit_per_unit, reverse=True)
    elif sort_by == "name":
        all_deals.sort(key=lambda d: d.type_name)
    elif sort_by == "jumps":
        all_deals.sort(key=lambda d: (d.jumps if d.jumps is not None else 999, -d.discount_pct))
    else:
        all_deals.sort(key=lambda d: d.discount_pct, reverse=True)

    return NearbyDealsResponse(
        deals=all_deals,
        regions_scanned=len(targets),
        regions_in_range=in_range,
        max_jumps=max_jumps,
        flag=flag,
        truncated=truncated,
    )


@router.get("/deals", response_model=MarketDealResponse)
async def get_deals(
    min_discount: float = 0.0,
    sort_by: str = "discount",
    region_id: int | None = None,
    user: User = Depends(_get_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Arbitrage opportunities for the user's region, or a browsed one.

    Passing region_id looks somewhere other than where the character is, which
    is how the region dropdown works.
    """
    target_region = region_id or user.current_region_id
    if not target_region:
        raise HTTPException(
            status_code=400,
            detail="Location not yet detected. Make sure you're logged into EVE.",
        )

    if target_region == THE_FORGE_REGION_ID:
        raise HTTPException(
            status_code=400,
            detail="The Forge is the reference market -- there's nothing to compare it against.",
        )

    # Get user config
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == user.id)
    )
    user_config = result.scalar_one_or_none()
    if not user_config:
        raise HTTPException(status_code=400, detail="Config not found")

    # A browsed region may have never been fetched, or gone stale since. The
    # freshness guard inside these makes a repeat view of the same region free.
    if region_id is not None:
        tracked = json.loads(user_config.tracked_category_ids)
        type_ids = await get_tracked_type_ids(db, tracked)

        browsed_name = await get_region_name(target_region)

        def progress_for(phase: str, name: str):
            async def report(completed: int, total: int):
                await ws_manager.send_progress(
                    user.id, phase, name, completed, total
                )
            return report

        await update_market_cache(
            db,
            target_region,
            type_filter=type_ids,
            on_progress=progress_for("region", browsed_name),
        )
        await update_jita_cache(
            db, type_ids=type_ids, on_progress=progress_for("jita", "Jita")
        )
        await ws_manager.send_progress(
            user.id, "compare", browsed_name, 1, 1, done=True
        )

    # Find deals
    deals = await find_arbitrage(db, target_region, user_config)

    # Apply additional filters
    if min_discount > 0:
        deals = [d for d in deals if d.discount_pct >= min_discount]

    # Sort
    if sort_by == "profit":
        deals.sort(key=lambda d: d.profit_per_unit, reverse=True)
    elif sort_by == "name":
        deals.sort(key=lambda d: d.type_name)
    # Default sort is by discount (already sorted)

    region_name = await get_region_name(target_region)

    # Get last update time
    last_updated_result = await db.execute(
        select(func.max(MarketCache.fetched_at)).where(
            MarketCache.region_id == target_region
        )
    )
    last_updated = last_updated_result.scalar()

    return MarketDealResponse(
        deals=deals,
        region_id=target_region,
        region_name=region_name,
        last_updated=last_updated.isoformat() if last_updated else None,
        is_browsed=target_region != user.current_region_id,
    )


@router.post("/refresh")
async def refresh_market(
    user: User = Depends(_get_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Force an immediate market data refresh for the user's current region."""
    if not user.current_region_id:
        raise HTTPException(
            status_code=400, detail="Location not yet detected"
        )

    await scan_market_for_user(user.id, user.current_region_id, force=True)
    return {"message": "Market refresh triggered", "region_id": user.current_region_id}
