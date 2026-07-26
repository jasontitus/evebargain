"""HTTP endpoints for reading and updating the player's settings.

The update endpoint takes a UserConfigUpdate, where every field is optional, so
the browser can send only what changed. Hence the repeated

    if update.some_field is not None:
        config.some_field = update.some_field

Checking against None rather than truthiness is deliberate: `if
update.min_volume:` would treat a legitimate 0 as "not supplied" and silently
ignore it.

Note there is no explicit UPDATE statement. `config` is a live SQLAlchemy
object attached to the session, so assigning to its attributes is enough --
`db.commit()` works out what changed and writes it.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import UserConfig
from app.schemas.config import UserConfigResponse, UserConfigUpdate, CategoryInfo
from app.utils.eve_constants import TRACKABLE_CATEGORIES

router = APIRouter(prefix="/api/config", tags=["config"])


async def _get_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


@router.get("/", response_model=UserConfigResponse)
async def get_config(
    user_id: int = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's current configuration."""
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == user_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    return UserConfigResponse(
        discount_threshold=config.discount_threshold,
        tracked_category_ids=json.loads(config.tracked_category_ids),
        notifications_enabled=config.notifications_enabled,
        sound_enabled=config.sound_enabled,
        min_volume=config.min_volume,
        min_profit_isk=config.min_profit_isk,
        alert_discount_threshold=config.alert_discount_threshold,
        alert_min_profit_isk=config.alert_min_profit_isk,
        alert_min_volume=config.alert_min_volume,
        alert_on_blueprints=config.alert_on_blueprints,
    )


@router.put("/", response_model=UserConfigResponse)
async def update_config(
    update: UserConfigUpdate,
    user_id: int = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update the user's configuration."""
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == user_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    if update.discount_threshold is not None:
        config.discount_threshold = update.discount_threshold
    if update.tracked_category_ids is not None:
        # Validate category IDs
        valid_ids = set(TRACKABLE_CATEGORIES.keys())
        for cid in update.tracked_category_ids:
            if cid not in valid_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid category ID: {cid}",
                )
        config.tracked_category_ids = json.dumps(update.tracked_category_ids)
    if update.notifications_enabled is not None:
        config.notifications_enabled = update.notifications_enabled
    if update.sound_enabled is not None:
        config.sound_enabled = update.sound_enabled
    if update.min_volume is not None:
        config.min_volume = update.min_volume
    if update.min_profit_isk is not None:
        config.min_profit_isk = update.min_profit_isk
    if update.alert_discount_threshold is not None:
        config.alert_discount_threshold = update.alert_discount_threshold
    if update.alert_min_profit_isk is not None:
        config.alert_min_profit_isk = update.alert_min_profit_isk
    if update.alert_min_volume is not None:
        config.alert_min_volume = update.alert_min_volume
    if update.alert_on_blueprints is not None:
        config.alert_on_blueprints = update.alert_on_blueprints

    await db.commit()

    return UserConfigResponse(
        discount_threshold=config.discount_threshold,
        tracked_category_ids=json.loads(config.tracked_category_ids),
        notifications_enabled=config.notifications_enabled,
        sound_enabled=config.sound_enabled,
        min_volume=config.min_volume,
        min_profit_isk=config.min_profit_isk,
        alert_discount_threshold=config.alert_discount_threshold,
        alert_min_profit_isk=config.alert_min_profit_isk,
        alert_min_volume=config.alert_min_volume,
        alert_on_blueprints=config.alert_on_blueprints,
    )


@router.get("/categories", response_model=list[CategoryInfo])
async def get_categories():
    """List all available item categories for tracking."""
    return [
        CategoryInfo(category_id=cid, name=name)
        for cid, name in TRACKABLE_CATEGORIES.items()
    ]
