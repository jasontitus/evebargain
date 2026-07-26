from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    # EVE SSO
    eve_client_id: str = ""
    eve_secret_key: str = ""
    eve_callback_url: str = "http://localhost:8000/api/auth/callback"

    # Where the browser reaches the web interface. The SSO callback lands on
    # this backend, so it needs an absolute URL to send the user back to --
    # "/" would leave them on the API port. Vite dev server by default; set
    # FRONTEND_URL=http://localhost:3000 when running under Docker.
    frontend_url: str = "http://localhost:5173"

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

    # CCP asks every third-party app to identify itself and provide a way to be
    # contacted, so they can reach out about a misbehaving client instead of
    # just blocking it. Set ESI_CONTACT in .env to an email or Discord handle.
    esi_contact: str = ""
    esi_app_name: str = "EVEBargain/1.0 (+https://github.com/jasontitus/evebargain)"

    # Max in-flight ESI requests. Region order pages are fetched concurrently,
    # and a full Jita pull is ~275 pages, so this is what stops the app opening
    # hundreds of sockets against ESI at once.
    esi_max_concurrency: int = 10

    # ESI caches market order pages for ~300s and returns the same bytes until
    # then, so re-fetching sooner burns requests for no new data. Refuse to
    # refetch a region whose cached rows are younger than this.
    market_cache_ttl: int = 300

    @property
    def esi_user_agent(self) -> str:
        if self.esi_contact:
            return f"{self.esi_app_name} {self.esi_contact}"
        return self.esi_app_name

    # .env lives at the repo root, but uvicorn is launched from backend/, so a
    # relative path would resolve against the wrong directory and silently load
    # nothing. Resolve both locations absolutely; the later file wins, letting a
    # backend-local .env override the shared one.
    model_config = {
        "env_file": (REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
