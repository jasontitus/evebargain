"""Application settings, loaded from environment variables and the .env file.

HOW THIS WORKS
    `Settings` inherits from pydantic-settings' `BaseSettings`. That base class
    does something unusual: for every attribute declared below, it looks for a
    matching environment variable (case-insensitively) and uses that value if
    it finds one. `eve_client_id` is filled from `EVE_CLIENT_ID`,
    `market_cache_ttl` from `MARKET_CACHE_TTL`, and so on.

    It also converts types. Environment variables are always strings, but
    because `market_cache_ttl: int` is annotated as an int, pydantic parses
    "300" into the integer 300 -- and raises a clear error at startup if
    someone sets it to "banana", rather than failing much later in a division.

    The value written after `=` is the default, used when the variable is not
    set anywhere.

PYTHON NOTES FOR NEWCOMERS
    - `name: str = ""` is a *type annotation* plus a default. Python does not
      enforce annotations at runtime, but libraries like pydantic read them and
      act on them, which is exactly what is happening here.
    - `@property` turns a method into something you read like an attribute:
      you write `settings.esi_user_agent`, not `settings.esi_user_agent()`.
    - An f-string (`f"{a} {b}"`) substitutes the values of `a` and `b` into the
      text.
"""

from pathlib import Path

from pydantic_settings import BaseSettings

# `__file__` is the path to this source file. `.resolve()` makes it absolute
# (following any symlinks), and each `.parent` walks one directory upwards:
#   this file  -> app/  -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    # --- EVE Single Sign-On credentials -------------------------------------
    # Created by registering an application at developers.eveonline.com. Without
    # these, login cannot work; main.py logs a warning at startup if they are
    # missing rather than letting the failure surface mid-login.
    eve_client_id: str = ""
    eve_secret_key: str = ""
    eve_callback_url: str = "http://localhost:8000/api/auth/callback"

    # Where the browser reaches the web interface. The SSO callback lands on
    # this backend, so it needs an absolute URL to send the user back to --
    # "/" would leave them on the API port. Vite dev server by default; set
    # FRONTEND_URL=http://localhost:3000 when running under Docker.
    frontend_url: str = "http://localhost:5173"

    # --- Database -----------------------------------------------------------
    # SQLAlchemy connection string. The "+aiosqlite" part selects the async
    # SQLite driver: this app talks to the database with async/await, so it
    # needs a driver that can yield control while waiting rather than blocking.
    database_url: str = "sqlite+aiosqlite:///./evebargain.db"

    # Signs the session cookie, which is how the server recognises a logged-in
    # browser. Anyone who knows this value can forge a login, so it must be
    # random in any real deployment -- the default below is a placeholder.
    session_secret: str = "change-this-to-a-random-secret-key"

    # --- Background timing (seconds) ----------------------------------------
    location_poll_interval: int = 30
    market_update_interval: int = 300  # 5 minutes

    # Used when creating a config row for a brand-new user: 0.10 means "alert
    # me when something is at least 10% cheaper than Jita".
    default_discount_threshold: float = 0.10

    # --- EVE SSO endpoints --------------------------------------------------
    # Fixed CCP URLs. They live here rather than being hardcoded further down
    # so a test or a mirror can point them elsewhere without editing code.
    eve_auth_url: str = "https://login.eveonline.com/v2/oauth/authorize"
    eve_token_url: str = "https://login.eveonline.com/v2/oauth/token"
    eve_jwks_url: str = "https://login.eveonline.com/oauth/jwks"

    # --- ESI (the EVE game data API) ----------------------------------------
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
        """The User-Agent header sent on every request to ESI.

        Built at read time rather than stored, so that changing ESI_CONTACT in
        .env changes the header without any other code needing to know.
        """
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


# Created once, when this module is first imported, and shared everywhere.
# Python caches imported modules, so every `from app.config import settings`
# elsewhere in the app gets this same object rather than re-reading .env.
settings = Settings()
