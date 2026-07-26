"""HTTP endpoints for the alert feed: list, dismiss, and clear.

Dismissing marks a row rather than deleting it. The alert history is what
suppresses repeat notifications for the same deal, so deleting a dismissed
alert would make it eligible to fire again immediately -- exactly the opposite
of what dismissing it implies.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertResponse, AlertListResponse

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


async def _get_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


@router.get("/", response_model=AlertListResponse)
async def get_alerts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    dismissed: bool | None = None,
    user_id: int = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get alert history with pagination."""
    query = select(Alert).where(Alert.user_id == user_id)

    if dismissed is not None:
        query = query.where(Alert.dismissed == dismissed)

    # Get total count
    count_query = select(func.count(Alert.id)).where(Alert.user_id == user_id)
    if dismissed is not None:
        count_query = count_query.where(Alert.dismissed == dismissed)
    total = (await db.execute(count_query)).scalar()

    # Get paginated results
    query = query.order_by(Alert.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    alerts = result.scalars().all()

    return AlertListResponse(
        alerts=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
    )


@router.post("/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: int,
    user_id: int = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a specific alert."""
    alert = await db.get(Alert, alert_id)
    if not alert or alert.user_id != user_id:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.dismissed = True
    await db.commit()
    return {"message": "Alert dismissed"}


@router.delete("/")
async def clear_alerts(
    user_id: int = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Clear all alert history for the user."""
    await db.execute(
        update(Alert).where(Alert.user_id == user_id).values(dismissed=True)
    )
    await db.commit()
    return {"message": "All alerts dismissed"}
