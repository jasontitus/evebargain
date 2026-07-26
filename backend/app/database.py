import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


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


def _literal(value) -> str | None:
    """Render a column default as SQL, or None if it can't be expressed."""
    if value is None or callable(value):
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None


async def _add_missing_columns(conn):
    """Add columns that exist on the models but not yet in the database.

    create_all() only creates missing tables -- it will not alter one that
    already exists. Without this, a new field is silently absent on every
    database created before it, and the first query touching it fails with a
    bare "no such column" that looks nothing like the schema drift it is.

    Additive only: no drops, no type changes, no renames.
    """
    for table in Base.metadata.sorted_tables:
        result = await conn.exec_driver_sql(f"PRAGMA table_info('{table.name}')")
        existing = {row[1] for row in result.fetchall()}
        if not existing:
            continue  # Table isn't there at all; create_all just made it.

        for column in table.columns:
            if column.name in existing:
                continue

            ddl_type = column.type.compile(conn.dialect)
            stmt = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'

            default = _literal(column.default.arg if column.default is not None else None)
            if default is not None:
                stmt += f" DEFAULT {default}"
            elif not column.nullable:
                # SQLite refuses NOT NULL without a default on an existing
                # table, and there is no sane value to invent.
                logger.warning(
                    "Cannot add NOT NULL column %s.%s without a default",
                    table.name,
                    column.name,
                )
                continue

            await conn.exec_driver_sql(stmt)
            logger.info("Added missing column %s.%s", table.name, column.name)


async def init_db():
    async with engine.begin() as conn:
        # Enable WAL mode for better concurrent read/write
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_columns(conn)
