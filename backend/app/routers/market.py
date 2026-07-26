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
    RegionListResponse,
    RegionSummary,
)
from app.services.price_comparator import find_arbitrage
from app.services.location import get_region_name, list_regions as get_all_regions
from app.services.market_fetcher import (
    get_tracked_type_ids,
    update_jita_cache,
    update_market_cache,
)
from app.tasks.scheduler import scan_market_for_user
from app.utils.eve_constants import THE_FORGE_REGION_ID

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
    user: User = Depends(_get_authenticated_user),
):
    """Every k-space region, for the browse-elsewhere dropdown.

    The Forge is omitted: it's the reference market every other region is
    priced against, so there is nothing to compare it to. Offering it would
    just be an option that always errors.
    """
    regions = await get_all_regions()
    return RegionListResponse(
        regions=[
            RegionSummary(region_id=rid, name=name)
            for rid, name in sorted(regions.items(), key=lambda kv: kv[1])
            if rid != THE_FORGE_REGION_ID
        ],
        current_region_id=user.current_region_id,
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
        await update_market_cache(db, target_region, type_filter=type_ids)
        await update_jita_cache(db, type_ids=type_ids)

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
