import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import init_db
from app.routers import auth, config, market, alerts, ws
from app.services.esi_client import esi_client
from app.tasks.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Where the React app is served. This process only serves the API, so anyone
# who opens the backend port in a browser needs pointing at the real UI.
FRONTEND_URL = settings.frontend_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting EVE Bargain...")
    await init_db()
    start_scheduler()

    if not settings.eve_client_id or not settings.eve_secret_key:
        # Without these, /api/auth/login still redirects -- straight to an EVE
        # SSO error page. Say so at startup rather than at the end of an
        # OAuth round trip.
        logger.warning(
            "EVE_CLIENT_ID / EVE_SECRET_KEY are not set: login will fail. "
            "Copy .env.example to .env in the repo root and fill them in."
        )

    logger.info("EVE Bargain ready -- API on this port, web interface at %s", FRONTEND_URL)
    yield
    logger.info("Shutting down EVE Bargain...")
    stop_scheduler()
    await esi_client.close()


app = FastAPI(
    title="EVE Bargain",
    description="EVE Online Regional Market Arbitrage Alert App",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    max_age=86400 * 7,  # 7 days
)

app.add_middleware(
    CORSMiddleware,
    # The two documented dev origins, plus FRONTEND_URL so a custom port does
    # not need a code change to be allowed through.
    allow_origins=sorted(
        {"http://localhost:5173", "http://localhost:3000", FRONTEND_URL}
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(config.router)
app.include_router(market.router)
app.include_router(alerts.router)
app.include_router(ws.router)


@app.get("/", tags=["meta"])
async def root():
    """Index for the API root.

    Opening the backend port in a browser is the natural first move after
    starting the server, so describe what is running here and where the web
    interface lives rather than answering with a bare 404.
    """
    return {
        "app": "evebargain",
        "version": app.version,
        "status": "ok",
        "message": "EVE Bargain API. This port serves the API only.",
        "web_interface": FRONTEND_URL,
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": "evebargain"}


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: StarletteHTTPException):
    """Add a hint to 404s on non-API paths.

    The React app owns client-side routes the backend knows nothing about, so
    a stray browser request to one of them looks like a broken server when it
    is really the wrong port. API and WebSocket 404s are left as-is -- callers
    parse those.
    """
    path = request.url.path
    if path.startswith("/api") or path.startswith("/ws"):
        return JSONResponse(status_code=404, content={"detail": exc.detail})

    return JSONResponse(
        status_code=404,
        content={
            "detail": exc.detail,
            "hint": (
                f"'{path}' is not an API route. The EVE Bargain web interface "
                f"runs at {FRONTEND_URL} (npm run dev in frontend/); this port "
                "serves the API only. Browse the API at /docs."
            ),
        },
    )
