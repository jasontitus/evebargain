from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    # EVE SSO
    eve_client_id: str = ""
    eve_secret_key: str = ""
    eve_callback_url: str = "http://localhost:8000/api/auth/callback"

    # Database
    database_url: str = "sqlite+aiosqlite:///./evebargain.db"

    # Session
    session_secret: str = "change-this-to-a-random-secret-key"

    # Polling intervals (seconds)
    location_poll_interval: int = 30
    market_update_interval: int = 300  # 5 minutes

    # Default alert config
    default_discount_threshold: float = 0.10

    # EVE SSO URLs
    eve_auth_url: str = "https://login.eveonline.com/v2/oauth/authorize"
    eve_token_url: str = "https://login.eveonline.com/v2/oauth/token"
    eve_jwks_url: str = "https://login.eveonline.com/oauth/jwks"

    # ESI Base URL
    esi_base_url: str = "https://esi.evetech.net/latest"

    # .env lives at the repo root, but uvicorn is launched from backend/, so a
    # relative path would resolve against the wrong directory and silently load
    # nothing. Resolve both locations absolutely; the later file wins, letting a
    # backend-local .env override the shared one.
    model_config = {
        "env_file": (REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
