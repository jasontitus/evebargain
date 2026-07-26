from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _ensure_sqlite_dir(url: str) -> None:
    """Create the directory a SQLite file lives in.

    SQLite reports a missing parent directory as "unable to open database
    file", which reads like corruption rather than a path that needs
    creating. Deployments point DATABASE_URL at a mounted directory, so make
    it up front.
    """
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return

    path = url[len(prefix):]
    if not path or path == ":memory:":
        return

    parent = Path(path).parent
    if parent and str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(settings.database_url)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},  # SQLite-specific
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        # Enable WAL mode for better concurrent read/write
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.run_sync(Base.metadata.create_all)
