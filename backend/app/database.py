"""Database setup: the connection, the session factory, and schema creation.

WHAT AN ORM IS
    This app never writes raw SQL for ordinary work. Instead it uses SQLAlchemy,
    an ORM (Object-Relational Mapper): you define Python classes (see the
    `models/` package), and SQLAlchemy translates them into tables, and
    translates Python expressions into SELECT/INSERT/UPDATE statements.

THE THREE OBJECTS DEFINED HERE
    engine   - owns the actual connection(s) to the database file. Created once
               for the whole process.
    Session  - a workspace for a unit of work. You add and query objects on a
               session, then `commit()` to write them. Each request gets its
               own.
    Base     - the parent class every model inherits from. Inheriting from it
               is what registers a class as a table.

WHY EVERYTHING IS ASYNC
    `async def` marks a coroutine: a function that can pause at an `await` and
    let the program do something else while it waits (for the disk, or for the
    network). This app polls ESI constantly in the background, so blocking the
    whole process on a database read would stall those. `async with` is the
    same idea for context managers -- it can pause while entering or exiting.
"""

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# The standard Python logging pattern: one logger per module, named after the
# module (`__name__` is e.g. "app.database"), so log lines say where they came
# from and can be filtered per module.
logger = logging.getLogger(__name__)


def _ensure_sqlite_dir(url: str) -> None:
    """Create the directory a SQLite file lives in.

    SQLite reports a missing parent directory as "unable to open database
    file", which reads like corruption rather than a path that needs
    creating. Deployments point DATABASE_URL at a mounted directory, so make
    it up front.

    (A leading underscore, as in `_ensure_sqlite_dir`, is the Python convention
    for "internal to this module" -- nothing enforces it, but it signals that
    other files should not call this.)
    """
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return  # Not SQLite (e.g. Postgres), so there is no file to make room for.

    # Slice off the prefix to leave just the filesystem path.
    path = url[len(prefix):]
    if not path or path == ":memory:":
        return  # An in-memory database has no file, and so no directory.

    parent = Path(path).parent
    if parent and str(parent) not in ("", "."):
        # parents=True also creates intermediate directories; exist_ok=True
        # means "already there" is success rather than an error.
        parent.mkdir(parents=True, exist_ok=True)


# Runs at import time, before the engine below tries to open the file.
_ensure_sqlite_dir(settings.database_url)

# The engine is the connection pool. Creating it does not connect yet -- that
# happens lazily on first use.
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Set True to print every SQL statement; very noisy but useful.
    # SQLite normally refuses to be used from a thread other than the one that
    # opened it. The async driver manages access safely itself, so that check
    # would only get in the way here.
    connect_args={"check_same_thread": False},
)

# A factory, not a session: calling `async_session()` produces a new session.
# expire_on_commit=False lets you keep reading an object's attributes after
# commit; the default would discard them and re-query on next access, which
# fails once the session is closed.
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """The shared parent of every model class.

    Subclassing it registers the model in `Base.metadata`, the catalogue of
    tables that `create_all()` below uses. `pass` means "no body" -- the class
    adds nothing of its own; inheriting is the whole point.
    """
    pass


async def get_db():
    """Hand out a database session, then close it. Used by FastAPI routes.

    This is a *generator*, not a normal function: `yield` hands a value to the
    caller and pauses here. FastAPI runs the route with that session, and when
    the response is finished it resumes this function so the `async with` block
    can exit and release the connection -- even if the route raised an error.

    Routes receive it by writing `db: AsyncSession = Depends(get_db)`. See
    routers/market.py for how that reads in practice.
    """
    async with async_session() as session:
        yield session


def _literal(value) -> str | None:
    """Render a column default as SQL text, or None if it can't be expressed.

    Used only by the migration helper below, to turn a Python default such as
    `50000.0` or `True` into something valid inside an ALTER TABLE statement.
    """
    # `callable(value)` catches defaults like `datetime.utcnow`, which are
    # functions to be called per row rather than a fixed value -- there is no
    # single literal that represents them.
    if value is None or callable(value):
        return None
    # bool must be tested before int: in Python `True` is also an int, so the
    # isinstance check below would otherwise match it and emit "True".
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # Doubling a quote is how SQL escapes it inside a quoted string.
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None


async def _add_missing_columns(conn):
    """Add columns that exist on the models but not yet in the database.

    create_all() only creates missing tables -- it will not alter one that
    already exists. Without this, a new field is silently absent on every
    database created before it, and the first query touching it fails with a
    bare "no such column" that looks nothing like the schema drift it is.

    Additive only: no drops, no type changes, no renames. A real project would
    normally use a migration tool such as Alembic; this is a deliberately small
    stand-in that covers the one case this app actually hits.
    """
    for table in Base.metadata.sorted_tables:
        # PRAGMA table_info is SQLite's "describe this table". Each row
        # describes one column, and index [1] of the row is its name.
        result = await conn.exec_driver_sql(f"PRAGMA table_info('{table.name}')")
        # A set comprehension: build a set of the existing column names, which
        # makes the `in` test below fast.
        existing = {row[1] for row in result.fetchall()}
        if not existing:
            continue  # Table isn't there at all; create_all just made it.

        for column in table.columns:
            if column.name in existing:
                continue  # Already present, nothing to do.

            # Ask SQLAlchemy what this column's type is called in SQL, e.g.
            # FLOAT or VARCHAR(255).
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
    """Prepare the database at startup. Safe to run every time.

    `engine.begin()` opens a connection *and* a transaction, committing when
    the block exits normally or rolling back if it raises.
    """
    async with engine.begin() as conn:
        # Write-Ahead Logging lets readers carry on while a write is in
        # progress. This app reads market data from web requests while the
        # background scanner writes to it, so without WAL they would block
        # each other.
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        # create_all inspects every model registered on Base and creates any
        # table that does not exist yet. Existing tables are left alone --
        # which is exactly the gap _add_missing_columns fills.
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_columns(conn)
