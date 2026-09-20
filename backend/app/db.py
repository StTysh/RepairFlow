"""Async SQLAlchemy engine/session with SQLite WAL durability settings."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar

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
            if not column.nullable and column.default is None:
                # Refuses BOTH the "no default at all" case AND the
                # "nullable=False with only a server_default" case.
                # SQLite's ALTER TABLE ADD COLUMN only accepts NOT NULL
                # when it can pre-fill every existing row with a constant
                # DEFAULT; `column.server_default` is an arbitrary SQL
                # expression (whatever was passed to
                # `sa.Column(server_default=...)`, e.g. `sa.text(...)`)
                # that this function has no general, safe way to prove is
                # a compile-time constant. An earlier version of this
                # guard only fired when *no* default existed at all,
                # which let a `nullable=False, server_default=...` column
                # sail through: the ALTER TABLE that followed rendered
                # only the column's type, so SQLite created it nullable
                # and default-less -- silently contradicting both
                # `nullable=False` and the intended server_default (see
                # docs/audit/04_schema_migrations.md, Finding 3a).
                # Refusing loudly is deliberately preferred over emitting
                # the DEFAULT clause here: write a reviewed Alembic
                # revision instead, which can inspect the expression by
                # hand and issue
                # `ALTER TABLE ... ADD COLUMN ... DEFAULT <expr> NOT NULL`
                # directly once a human has confirmed it is safe for
                # every existing row.
                raise RuntimeError(
                    f"cannot auto-add non-nullable column {table.name}.{column.name} "
                    "without a Python-side `default=` (a `server_default`-only "
                    "nullable=False column is refused too) -- write an Alembic "
                    "revision for it"
                )
            ddl_type = column.type.compile(dialect=conn.dialect)
            conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}')
            applied.append(f"{table.name}.{column.name}")

            # SQLite fills the new column with NULL on every existing row,
            # and a SQLAlchemy `default=` runs in Python at INSERT time --
            # it never touches rows that are already there. For a column
            # the model declares NOT NULL that is a latent crash rather
            # than a cosmetic gap: writes stay happy and the read side
            # raises the first time a pre-existing row is loaded. Backfill
            # in the same transaction as the ALTER so the table is never
            # left in that state.
            backfill = _default_value(column)
            if backfill is not _NO_DEFAULT:
                processor = column.type.bind_processor(conn.dialect)
                value = processor(backfill) if processor is not None else backfill
                conn.exec_driver_sql(
                    f'UPDATE "{table.name}" SET "{column.name}" = ? WHERE "{column.name}" IS NULL',
                    (value,),
                )

    return applied


_NO_DEFAULT = object()


def _default_value(column):
    """What a freshly-inserted row would get for this column, or
    `_NO_DEFAULT` when there is no single right answer.

    Covers both shapes SQLAlchemy stores: a scalar (`default="INTERNAL"`,
    or an Enum member) and a callable (`default=list`, which SQLAlchemy
    wraps to accept an execution context). A default that genuinely
    depends on the insert's other values cannot be reconstructed for a
    historical row, so it is skipped rather than guessed at.
    """
    default = column.default
    if default is None:
        return _NO_DEFAULT
    if getattr(default, "is_scalar", False):
        arg = default.arg
    elif getattr(default, "is_callable", False):
        try:
            arg = default.arg(None)
        except Exception:
            return _NO_DEFAULT
    else:
        return _NO_DEFAULT
    # An Enum column stores the member's value, not the member.
    return getattr(arg, "value", arg)


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


_T = TypeVar("_T")


def run_cli(coro: Coroutine[Any, Any, _T]) -> _T:
    """Entry point for every standalone `python -m app.xxx` script.

    `main.py`'s FastAPI lifespan is the only caller of `create_all()` in
    the running application; every other entry point
    (`app.seed`, `app.legacy_demo_purge`, `app.backfill_category`,
    `app.archive`) is invoked directly, so without this it queries
    whatever schema the database file happens to already be at. Against
    a real, already-deployed database that predates a later model
    change, that schema is missing tables/columns entirely --
    reproduced empirically in docs/audit/04_schema_migrations.md
    (Finding 2): `python -m app.legacy_demo_purge --dry-run` against a
    copy of the real database died with
    `OperationalError: no such table: cost_entries`.

    One shared helper instead of a `await create_all()` pasted at the
    top of each script's coroutine, so there is exactly one place that
    decides *how* a CLI bootstraps. `create_all()` is idempotent
    (`checkfirst=True` table creation, diff-based column/index backfill),
    so it is always safe to call once per process -- including a script
    like `backfill_category` whose `main()` calls this twice (`plan()`
    then `apply_changes()`).
    """

    async def _bootstrap_then_run() -> _T:
        await create_all()
        return await coro

    return asyncio.run(_bootstrap_then_run())
