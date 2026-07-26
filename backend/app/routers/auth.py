import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User, UserConfig
from app.schemas.user import UserResponse
from app.services import sso
from app.services.location import get_region_name
from app.tasks.scheduler import setup_user_polling, setup_market_refresh

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    """Redirect user to EVE SSO for authentication."""
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    authorize_url = sso.get_authorize_url(state)
    return RedirectResponse(url=authorize_url)


@router.get("/callback")
async def callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback from EVE SSO."""
    # Verify state parameter
    stored_state = request.session.get("oauth_state")
    if not stored_state or state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    # Exchange code for tokens
    token_data = await sso.exchange_code(code)

    # Find or create user
    result = await db.execute(
        select(User).where(User.character_id == token_data["character_id"])
    )
    user = result.scalar_one_or_none()

    if user:
        user.access_token = token_data["access_token"]
        user.refresh_token = token_data["refresh_token"]
        user.token_expires = token_data["expires_at"]
        user.character_name = token_data["character_name"]
        user.updated_at = datetime.utcnow()
    else:
        user = User(
            character_id=token_data["character_id"],
            character_name=token_data["character_name"],
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            token_expires=token_data["expires_at"],
        )
        db.add(user)
        await db.flush()

        # Create default config for new user
        config = UserConfig(user_id=user.id)
        db.add(config)

    await db.commit()

    # Store user ID in session
    request.session["user_id"] = user.id

    # Start background polling for this user
    setup_user_polling(user.id)
    setup_market_refresh(user.id)

    # Back to the web interface, not to "/" -- that is this API port.
    return RedirectResponse(url=settings.frontend_url or "/")


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get the currently authenticated user's info."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    region_name = None
    if user.current_region_id:
        region_name = await get_region_name(user.current_region_id)

    return UserResponse(
        character_id=user.character_id,
        character_name=user.character_name,
        current_region_id=user.current_region_id,
        current_system_id=user.current_system_id,
        current_region_name=region_name,
    )


@router.post("/logout")
async def logout(request: Request):
    """Clear the user session."""
    request.session.clear()
    return {"message": "Logged out"}
