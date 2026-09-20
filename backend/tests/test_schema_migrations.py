"""Regression tests for docs/audit/04_schema_migrations.md.

Covers, one test class per finding: every standalone `python -m app.xxx`
entry point bootstrapping its own schema before it queries (Finding 2);
`_add_missing_columns`'s sibling index pass backfilling a declared index
onto an already-existing table, idempotently (Finding 3b); the
`nullable=False` + `server_default`-only column shape being refused
loudly rather than silently mis-added (Finding 3a); `enum_column()`'s
CHECK constraint on newly created tables (Finding 1); and the
`alembic/env.py` guard that replaces "bring the revision chain current"
as this project's answer to Finding 8/HIGH #5 (see that file's
docstring for the full reasoning).

Style follows conftest.py's `app_db` fixture and test_audit_regressions.py:
a temp-file SQLite database (never backend/data/repairflow.db), the
process-wide `app.db` engine singleton repointed at it per test. Unlike
`app_db`, `fresh_database_path` below deliberately never calls
create_all() itself -- bootstrapping is exactly the behavior under test,
so every test here must start from a database that is genuinely empty.
Every test that drives a CLI is a plain `def`, not `async def`: each
entry point's own `main()` calls `app.db.run_cli()`, which wraps
`asyncio.run()` and would raise "cannot be called from a running event
loop" if invoked from inside a pytest-asyncio test.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

import app.archive.__main__ as archive_cli
import app.backfill_category as backfill_category
import app.db as db_module
import app.legacy_demo_purge as legacy_demo_purge
import app.seed as seed_module
from app.archive.dataset import DEFAULT_LABEL
from app.config import get_settings
from app.db import Base, run_cli, session_scope
from app.models import PropertyModel, RepairCaseModel, TenantModel, new_uuid
from app.schemas import CaseStatus

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def fresh_database_path(tmp_path, monkeypatch):
    """Points app.db's process-wide engine singleton at a brand-new,
    empty SQLite file -- deliberately without calling create_all(),
    unlike conftest.py's `app_db` fixture.
    """
    db_path = tmp_path / "fresh.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    get_settings.cache_clear()
    db_module._engine = None
    db_module._session_factory = None
    yield db_path
    asyncio.run(db_module.dispose_engine())
    db_module._engine = None
    db_module._session_factory = None
    get_settings.cache_clear()


def _rebootstrap():
    """Disposes the current engine and forces the next `run_cli()` call
    to open a fresh connection pool -- needed between a `run_cli()` call
    and a raw `sqlite3` connection to the same file (WAL-mode SQLite
    does not like a pooled async connection and a bare sqlite3 one
    fighting over the same file), and again before re-bootstrapping.
    """
    asyncio.run(db_module.dispose_engine())
    db_module._engine = None
    db_module._session_factory = None


# ---------------------------------------------------------------------
# Finding 2 -- every standalone entry point bootstraps its own schema
# ---------------------------------------------------------------------


def test_legacy_demo_purge_bootstraps_schema_on_fresh_database(fresh_database_path):
    """Reproduces Finding 2 directly: `python -m app.legacy_demo_purge
    --dry-run` against a copy of the real, already-deployed database
    died with `OperationalError: no such table: cost_entries`, because
    only main.py's FastAPI lifespan ever called create_all() -- every
    standalone script inherited whatever schema the file happened to
    already be at. Seeds one row with a real scripted-demo case id so
    `purge()`'s per-table count loop actually reaches the
    once-missing `cost_entries` table, not just `repair_cases`.
    """
    case_id = legacy_demo_purge.scripted_case_ids()[0]

    async def _seed_one_scripted_case() -> None:
        async with session_scope() as session:
            property_id = new_uuid()
            tenant_id = new_uuid()
            prop = PropertyModel(
                id=property_id, address_line="1 Test St", postcode="BS1 1AA", landlord_reference="L1"
            )
            tenant = TenantModel(
                id=tenant_id, property_id=property_id, display_name="Test Tenant", preferred_channel="SMS"
            )
            session.add_all([prop, tenant])
            await session.flush()
            session.add(
                RepairCaseModel(
                    id=case_id,
                    case_number=1,
                    property_id=prop.id,
                    tenant_id=tenant.id,
                    title="Scripted demo case",
                    status=CaseStatus.ACTIVE,
                )
            )

    run_cli(_seed_one_scripted_case())
    counts = run_cli(legacy_demo_purge.purge(apply=False))

    assert counts["cases_found"] == 1
    assert counts["cost_entries"] == 0  # table exists and was queried, not crashed on


def test_backfill_category_bootstraps_schema_on_fresh_database(fresh_database_path):
    """`plan()` queries RepairCaseModel/WorkOrderModel via a plain
    session_scope() with no bootstrap of its own; against a completely
    schemaless file this must not raise."""
    changes, skipped, already_set = run_cli(backfill_category.plan())
    assert (changes, skipped, already_set) == ([], 0, 0)


def test_seed_bootstraps_schema_on_fresh_database(fresh_database_path):
    """`python -m app.seed` is the documented way to get a working
    database from nothing; it must not depend on anything else having
    booted the app first."""
    run_cli(seed_module.seed())

    async def _count_properties() -> int:
        async with session_scope() as session:
            return (
                await session.execute(sa.select(sa.func.count()).select_from(PropertyModel))
            ).scalar_one()

    assert run_cli(_count_properties()) > 0


def test_archive_cli_bootstraps_schema_on_fresh_database(fresh_database_path):
    """`_status` (and `_apply`/`_remove`/`_validate` alongside it) used
    to call `create_all()` itself -- except `_remove`, which never did
    and crashed on a database that predates `ArchiveBatchModel`/
    `CostEntryModel`/etc. Now every one of the four goes through the
    same `run_cli()` helper as the other CLIs, so this exercises the
    fix for all of them via the cheapest one to assert on."""
    result = run_cli(archive_cli._status(DEFAULT_LABEL))
    assert result == 0


# ---------------------------------------------------------------------
# Finding 3b -- indexes are backfilled onto an already-existing table
# ---------------------------------------------------------------------


def test_add_missing_indexes_creates_missing_index_on_existing_table(fresh_database_path):
    """Reproduces Finding 3b: `Base.metadata.create_all(checkfirst=True)`
    skips a table's DDL -- indexes included -- the instant the table
    already exists, and nothing else ever diffed or backfilled an index
    on an already-existing table. Confirmed against the real production
    database: all five `archive_batch_id` indexes were missing, making
    `WHERE archive_batch_id IS NULL` (analytics.py's leading filter
    almost everywhere) a full table scan. Simulates that exact real-world
    state -- an already-bootstrapped database missing one declared index
    -- by dropping it after a normal bootstrap, then re-bootstrapping and
    checking both that the index comes back and that SQLite's own query
    planner starts using it. A third bootstrap immediately afterward
    proves the index pass is idempotent (CREATE INDEX ... IF NOT EXISTS
    semantics)."""
    run_cli(asyncio.sleep(0))  # first bootstrap: full schema, index included
    _rebootstrap()

    conn = sqlite3.connect(str(fresh_database_path))
    try:
        conn.execute("DROP INDEX ix_repair_cases_archive_batch_id")
        conn.commit()
        before = conn.execute(
            "EXPLAIN QUERY PLAN SELECT count(*) FROM repair_cases WHERE archive_batch_id IS NULL"
        ).fetchall()
    finally:
        conn.close()
    assert any("SCAN repair_cases" in str(row) for row in before), before

    run_cli(asyncio.sleep(0))  # re-bootstrap: the index pass should recreate it
    _rebootstrap()

    conn = sqlite3.connect(str(fresh_database_path))
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "ix_repair_cases_archive_batch_id" in names
        after = conn.execute(
            "EXPLAIN QUERY PLAN SELECT count(*) FROM repair_cases WHERE archive_batch_id IS NULL"
        ).fetchall()
    finally:
        conn.close()
    assert any(
        "ix_repair_cases_archive_batch_id" in str(row) and "SCAN" not in str(row) for row in after
    ), after

    run_cli(asyncio.sleep(0))  # idempotent: must not raise "index already exists"


def test_add_missing_indexes_preserves_partial_unique_index_shape(fresh_database_path):
    """A naive `CREATE INDEX IF NOT EXISTS name ON t (cols)` would
    silently drop the UNIQUE-ness and the `sqlite_where` clause of
    `AppointmentModel`'s `uq_appointment_provider_booking` index -- the
    same class of "only the type gets rendered, the rest of the intent
    is dropped" bug Finding 3a already found for column defaults.
    Confirms the real DDL (compiled via `CreateIndex`, not hand-built
    text) round-trips correctly for a table create_all() builds fresh."""
    run_cli(asyncio.sleep(0))
    _rebootstrap()

    conn = sqlite3.connect(str(fresh_database_path))
    try:
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='uq_appointment_provider_booking'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert "UNIQUE" in sql
    assert "WHERE" in sql


# ---------------------------------------------------------------------
# Finding 3a -- nullable=False + server_default-only is refused, not
# silently mis-added
# ---------------------------------------------------------------------


def test_nullable_false_server_default_only_column_is_refused(monkeypatch):
    """The original guard only fired when a new column had *no* default
    at all; a `nullable=False, server_default=...` column (no
    Python-side `default=`) sailed past it, and the ALTER TABLE that
    followed rendered only the column's type -- SQLite created it
    nullable and default-less, silently contradicting the model. The
    fixed guard refuses this shape outright (see `_add_missing_columns`'s
    docstring for why refusing was chosen over compiling an arbitrary
    server_default expression into DDL)."""
    md = sa.MetaData()
    sa.Table(
        "t",
        md,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'ACTIVE'")),
    )

    class _FakeBase:
        metadata = md

    monkeypatch.setattr(db_module, "Base", _FakeBase)

    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql("CREATE TABLE t (id VARCHAR(36) PRIMARY KEY)")
            with pytest.raises(RuntimeError, match="server_default"):
                async with engine.begin() as conn:
                    await conn.run_sync(db_module._add_missing_columns)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_nullable_false_no_default_at_all_is_still_refused(monkeypatch):
    """The pre-existing "no default whatsoever" case must keep refusing
    too -- this fix must not narrow the guard, only widen it."""
    md = sa.MetaData()
    sa.Table(
        "t",
        md,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
    )

    class _FakeBase:
        metadata = md

    monkeypatch.setattr(db_module, "Base", _FakeBase)

    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql("CREATE TABLE t (id VARCHAR(36) PRIMARY KEY)")
            with pytest.raises(RuntimeError, match="Python-side"):
                async with engine.begin() as conn:
                    await conn.run_sync(db_module._add_missing_columns)
        finally:
            await engine.dispose()

    asyncio.run(_run())


# ---------------------------------------------------------------------
# Finding 1 -- enum_column() gets a CHECK constraint on new tables
# ---------------------------------------------------------------------


def test_enum_column_check_constraint_rejects_invalid_value_on_new_table():
    """Reproduces Finding 1's exact repro against `jobs.kind`:
    SQLAlchemy 2.0 defaults `Enum.create_constraint` to False, so no
    enum_column() ever got a CHECK constraint despite
    docs/17_DATABASE_DESIGN.md's "Enums have CHECK constraints" --
    confirmed by a raw INSERT with an invalid `kind` sailing in cleanly.
    `create_constraint=True` fixes this for every table created from now
    on (see enum_column's docstring for what an already-deployed
    database still lacks -- this test only proves the new-table case)."""

    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            with pytest.raises(IntegrityError, match="CHECK constraint failed"):
                async with engine.begin() as conn:
                    await conn.exec_driver_sql(
                        "INSERT INTO jobs (id, kind, dedupe_key, payload, run_at, status, attempts) "
                        "VALUES ('x', 'NOT_A_REAL_KIND', 'dedupe-x', '{}', "
                        "'2026-01-01T00:00:00+00:00', 'PENDING', 0)"
                    )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_repair_cases_two_castatus_columns_both_get_independent_checks():
    """`repair_cases` has two `CaseStatus` enum_column()s (`status` and
    `resume_status`); confirms SQLAlchemy doesn't collide their
    (unnamed) generated CHECK constraints into one, and that both are
    independently enforced."""

    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                def _ddl(sync_conn):
                    return sync_conn.exec_driver_sql(
                        "SELECT sql FROM sqlite_master WHERE name='repair_cases'"
                    ).fetchone()[0]
                ddl = await conn.run_sync(_ddl)
            assert ddl.count("CHECK") >= 3  # version>0 + status enum + resume_status enum
        finally:
            await engine.dispose()

    asyncio.run(_run())


# ---------------------------------------------------------------------
# Finding 8 / HIGH #5 -- the Alembic decision
# ---------------------------------------------------------------------
#
# `alembic upgrade head` on an empty database was 4 tables and 17+
# columns short of what app.models/the running app requires, and
# nothing said so. Bringing the chain current would mean hand-
# reproducing every JSON column, the UTCDateTime decorator and two
# partial unique indexes by hand, and it would be stale again on the
# very next model change -- the drift this audit found, recreated.
# `_add_missing_columns`'s own docstring already says the running app
# has always bootstrapped itself with create_all(); alembic/env.py now
# says so structurally too: it refuses to run at all unless
# REPAIRFLOW_ALLOW_ALEMBIC=1 is set, so a stale chain can never again be
# mistaken for a working migration path.


def test_alembic_upgrade_head_refuses_without_opt_in(tmp_path):
    db_path = tmp_path / "alembic_fresh.db"
    env = dict(os.environ)
    env["DATABASE_PATH"] = str(db_path)
    env.pop("REPAIRFLOW_ALLOW_ALEMBIC", None)

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode != 0
    assert "REPAIRFLOW_ALLOW_ALEMBIC" in result.stderr
    assert not db_path.exists()


def test_alembic_upgrade_head_opt_in_still_produces_incomplete_schema(tmp_path):
    """The opt-in exists for inspecting or reviving the frozen chain, not
    for bootstrapping a real database -- confirms it still produces the
    documented-incomplete schema, so nobody mistakes "it ran" for "it
    worked"."""
    db_path = tmp_path / "alembic_opt_in.db"
    env = dict(os.environ)
    env["DATABASE_PATH"] = str(db_path)
    env["REPAIRFLOW_ALLOW_ALEMBIC"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert "repair_cases" in tables
    assert "cost_entries" not in tables  # still incomplete -- documents the gap, doesn't fix it
