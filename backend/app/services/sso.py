import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta

import httpx
from jose import jwt as jose_jwt

from app.config import settings

logger = logging.getLogger(__name__)

# Cache for JWKS keys
_jwks_cache: dict | None = None


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def get_authorize_url(state: str) -> str:
    """Build EVE SSO authorization redirect URL."""
    scope = " ".join(["esi-location.read_location.v1"])
    params = {
        "response_type": "code",
        "client_id": settings.eve_client_id,
        "redirect_uri": settings.eve_callback_url,
        "scope": scope,
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{settings.eve_auth_url}?{query}"


def _get_auth_header() -> str:
    """Build Basic auth header for token requests."""
    credentials = f"{settings.eve_client_id}:{settings.eve_secret_key}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


async def exchange_code(code: str) -> dict:
    """Exchange authorization code for access and refresh tokens.

    Returns dict with: access_token, refresh_token, expires_at,
    character_id, character_name
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.eve_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
            },
            headers={
                "Authorization": _get_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response.raise_for_status()
        token_data = response.json()

    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]
    expires_in = token_data.get("expires_in", 1199)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Decode JWT to extract character info (without full validation for speed;
    # we trust the direct token endpoint response)
    claims = jose_jwt.get_unverified_claims(access_token)
    # sub format: "CHARACTER:EVE:<character_id>"
    sub = claims.get("sub", "")
    character_id = int(sub.split(":")[-1])
    character_name = claims.get("name", "Unknown")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "character_id": character_id,
        "character_name": character_name,
    }


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an expired access token.

    Returns dict with: access_token, refresh_token, expires_at
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.eve_token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={
                "Authorization": _get_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response.raise_for_status()
        token_data = response.json()

    expires_in = token_data.get("expires_in", 1199)
    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": datetime.utcnow() + timedelta(seconds=expires_in),
    }


async def get_valid_token(user) -> str:
    """Get a valid access token for a user, refreshing if needed.

    Mutates the user object with new token data if refreshed.
    Returns the valid access token string.
    """
    if datetime.utcnow() < user.token_expires - timedelta(minutes=1):
        return user.access_token

    logger.info(f"Refreshing token for character {user.character_id}")
    token_data = await refresh_access_token(user.refresh_token)
    user.access_token = token_data["access_token"]
    user.refresh_token = token_data["refresh_token"]
    user.token_expires = token_data["expires_at"]
    return user.access_token
