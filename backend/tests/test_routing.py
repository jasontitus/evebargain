"""Tests for top-level routing and the SSO round trip's landing page.

These cover the paths a browser takes rather than an API client: opening the
backend port directly, and coming back from EVE SSO.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.services import sso


@pytest.mark.asyncio
async def test_root_points_at_the_web_interface(test_app):
    """GET / describes the API instead of 404ing."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["app"] == "evebargain"
    assert body["web_interface"] == settings.frontend_url


@pytest.mark.asyncio
async def test_non_api_404_explains_the_wrong_port(test_app):
    """A stray hit on a client-side route says where the UI actually is."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/dashboard")

    assert response.status_code == 404
    assert settings.frontend_url in response.json()["hint"]


@pytest.mark.asyncio
async def test_api_404_stays_machine_readable(test_app):
    """API callers parse these, so the body keeps its original shape."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.asyncio
async def test_callback_returns_to_the_frontend_not_the_api(test_app, monkeypatch):
    """After SSO the browser lands on the UI, not on this API port.

    Redirecting to "/" would drop the user on the backend's JSON index, which
    is what made a successful login look like a broken app.
    """
    async def fake_exchange_code(code: str) -> dict:
        from datetime import datetime, timedelta

        return {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": datetime.utcnow() + timedelta(hours=1),
            "character_id": 90000001,
            "character_name": "Test Pilot",
        }

    monkeypatch.setattr(sso, "exchange_code", fake_exchange_code)
    monkeypatch.setattr("app.routers.auth.setup_user_polling", lambda user_id: None)
    monkeypatch.setattr("app.routers.auth.setup_market_refresh", lambda user_id: None)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # /login stores the CSRF state in the session cookie the client keeps.
        login = await client.get("/api/auth/login")
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

        callback = await client.get(
            "/api/auth/callback", params={"code": "auth-code", "state": state}
        )

    assert callback.status_code == 307
    assert callback.headers["location"] == settings.frontend_url
