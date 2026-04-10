import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserConfig
from app.models.market import MarketCache
from app.schemas.market import ArbitrageResult, MarketDealResponse
from app.services.price_comparator import find_arbitrage
from app.services.location import get_region_name
from app.tasks.scheduler import scan_market_for_user

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


@router.get("/deals", response_model=MarketDealResponse)
async def get_deals(
    min_discount: float = 0.0,
    sort_by: str = "discount",
    user: User = Depends(_get_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current arbitrage opportunities for the user's region."""
    if not user.current_region_id:
        raise HTTPException(
            status_code=400,
            detail="Location not yet detected. Make sure you're logged into EVE.",
        )

    # Get user config
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == user.id)
    )
    user_config = result.scalar_one_or_none()
    if not user_config:
        raise HTTPException(status_code=400, detail="Config not found")

    # Find deals
    deals = await find_arbitrage(db, user.current_region_id, user_config)

    # Apply additional filters
    if min_discount > 0:
        deals = [d for d in deals if d.discount_pct >= min_discount]

    # Sort
    if sort_by == "profit":
        deals.sort(key=lambda d: d.profit_per_unit, reverse=True)
    elif sort_by == "name":
        deals.sort(key=lambda d: d.type_name)
    # Default sort is by discount (already sorted)

    region_name = await get_region_name(user.current_region_id)

    # Get last update time
    last_updated_result = await db.execute(
        select(func.max(MarketCache.fetched_at)).where(
            MarketCache.region_id == user.current_region_id
        )
    )
    last_updated = last_updated_result.scalar()

    return MarketDealResponse(
        deals=deals,
        region_id=user.current_region_id,
        region_name=region_name,
        last_updated=last_updated.isoformat() if last_updated else None,
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

    await scan_market_for_user(user.id, user.current_region_id)
    return {"message": "Market refresh triggered", "region_id": user.current_region_id}
