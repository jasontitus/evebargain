from pydantic_settings import BaseSettings


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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
