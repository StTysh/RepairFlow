"""Async SQLAlchemy engine/session with SQLite WAL durability settings."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _sqlite_url(db_path: str) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            _sqlite_url(str(settings.database_path)),
            echo=False,
            pool_pre_ping=True,
        )

        @event.listens_for(_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False
        )
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Short-lived transaction boundary. Never held open across a network/model call."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _add_missing_columns(conn) -> list[str]:
    """Bring an existing SQLite file up to the current model definitions.

    `Base.metadata.create_all` creates missing *tables* but never touches a
    table that already exists, so a column added to a model after a
    database was first created is silently absent until every query that
    mentions it fails. Alembic revisions are kept in `alembic/versions/`
    for the record, but the running application has always bootstrapped
    itself with create_all -- this closes the gap between the two rather
    than requiring an out-of-band migration step before the app will boot.

    Only ever ADDs nullable/defaulted columns, which is the one schema
    change SQLite performs in place and the only one that cannot lose
    data. Anything destructive (drop, retype, rename) is deliberately not
    handled here and belongs in a reviewed Alembic revision.
    """
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(conn)
    existing_tables = set(inspector.get_table_names())
    applied: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            if not column.nullable and column.default is None and column.server_default is None:
                # Adding a NOT NULL column with no default to a populated
                # table cannot succeed; surface it instead of half-applying.
                raise RuntimeError(
                    f"cannot auto-add non-nullable column {table.name}.{column.name} "
                    "without a default -- write an Alembic revision for it"
                )
            ddl_type = column.type.compile(dialect=conn.dialect)
            conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}')
            applied.append(f"{table.name}.{column.name}")

    return applied


async def create_all() -> None:
    from app import models  # noqa: F401  ensure models are registered

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        added = await conn.run_sync(_add_missing_columns)
    if added:
        print(f"Schema: added {len(added)} missing column(s): {', '.join(added)}")


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
