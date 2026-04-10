import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting EVE Bargain...")
    await init_db()
    start_scheduler()
    logger.info("EVE Bargain ready")
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
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": "evebargain"}
