from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db as db_module
from app.config import get_settings
from app.db import Base


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Isolated in-memory SQLite database per test, with the same durability
    pragmas as production (minus WAL, which needs a real file)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _pragma(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def new_id() -> callable:
    return lambda: str(uuid.uuid4())


@pytest_asyncio.fixture
async def app_db() -> AsyncIterator[None]:
    """Repoints app.db's process-wide engine singleton at an isolated,
    file-backed temp database for the duration of one test. Everything
    under test (services, executor, dispatcher, worker) calls
    app.db.session_scope() internally, so this is what actually isolates
    Phase 2+ tests from each other and from a developer's real data/."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_PATH"] = path
    get_settings.cache_clear()
    db_module._engine = None
    db_module._session_factory = None

    await db_module.create_all()
    try:
        yield
    finally:
        await db_module.dispose_engine()
        os.environ.pop("DATABASE_PATH", None)
        get_settings.cache_clear()
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(path + suffix)
            if candidate.exists():
                candidate.unlink()
