"""The captured-intake fixture, and the two orderings it depends on.

These exist because both orderings were wrong first, and neither failure
was visible from reading the code -- one produced a UNIQUE violation and
one a FOREIGN KEY violation, each only at import time against a real
schema.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa

import app.db as db_module
from app.config import get_settings
from app.db import Base
from app.intake_fixture import (
    TABLE_ORDER,
    apply_fixture,
    dataset_case_ids,
    load_dataset,
    remove_fixture,
    status,
    validate,
)
from app.intake_fixture.export import scan_tables
from app.models import CaseEventModel, RepairCaseModel
from app.seed import seed


@pytest_asyncio.fixture
async def intake_env() -> AsyncIterator[None]:
    """A temp database with app.seed already applied.

    Same shape as test_sample_operations.ops_env: the fixture references
    seeded properties and tenants by id, so the reference data has to be
    there before it can import.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_PATH"] = db_path
    get_settings.cache_clear()
    db_module._engine = None
    db_module._session_factory = None
    await db_module.create_all()
    await seed()
    try:
        yield None
    finally:
        await db_module.dispose_engine()
        os.environ.pop("DATABASE_PATH", None)
        get_settings.cache_clear()
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(db_path + suffix)
            if candidate.exists():
                candidate.unlink()


def test_dataset_is_present_and_describes_cases() -> None:
    tables = load_dataset()
    assert tables, "app/intake_fixture/dataset.json is missing or empty"
    assert len(dataset_case_ids(tables)) == 14


def test_dataset_carries_no_personal_data() -> None:
    """The committed file is in a PUBLIC repository.

    This is the same scan the exporter runs before writing, applied to
    what is actually on disk -- so hand-editing personal data into the
    file fails the suite rather than reaching GitHub.
    """
    assert scan_tables(load_dataset()) == []


def test_dataset_carries_no_tenant_or_contractor_rows() -> None:
    """Identity data comes from app.seed, never from the capture.

    The only value that has ever tripped the personal-data gate was a real
    mobile number in a `tenants` row. Keeping those tables out of the
    fixture entirely is what makes that structurally impossible rather
    than merely checked.
    """
    tables = load_dataset()
    for forbidden in ("tenants", "properties", "contractors"):
        assert forbidden not in tables


def test_insert_order_matches_the_foreign_key_graph() -> None:
    """Regression: `dependencies` was hand-listed before `contractor_reports`.

    It carries `discovered_from_report_id`, so importing in the
    hand-written order raised `FOREIGN KEY constraint failed`. The order
    is now derived from `Base.metadata.sorted_tables`; this asserts the
    property that derivation is for, so a future hand-edit cannot undo it.
    """
    position = {model.__tablename__: i for i, model in enumerate(TABLE_ORDER)}
    for model in TABLE_ORDER:
        table = Base.metadata.tables[model.__tablename__]
        for column in table.columns:
            for fk in column.foreign_keys:
                target = fk.column.table.name
                if target == table.name or target not in position:
                    continue  # self-reference, or a table app.seed owns
                assert position[target] < position[table.name], (
                    f"{table.name}.{column.name} points at {target}, "
                    f"which must be inserted first"
                )


def test_case_events_self_reference_is_deferred() -> None:
    """`causation_event_id` points into its own table.

    A table-level sort cannot order rows *within* a table, so the import
    nulls this column on insert and restores it in a second pass. If the
    schema ever grows another self-reference, this fails and the author
    finds out here rather than at someone's first bootstrap.
    """
    from app.intake_fixture import _self_referential_columns

    assert _self_referential_columns(CaseEventModel) == ["causation_event_id"]
    others = {
        m.__tablename__: _self_referential_columns(m)
        for m in TABLE_ORDER
        if m is not CaseEventModel and _self_referential_columns(m)
    }
    assert others == {}


def test_captured_case_numbers_start_at_one() -> None:
    """Why app.bootstrap imports this BEFORE the generators.

    Both generators allocate `MAX(case_number) + 1`. These cases carry the
    numbers they were originally issued, so importing them after the
    generators collides on `uq_case_number`.
    """
    numbers = sorted(row["case_number"] for row in load_dataset()["repair_cases"])
    assert numbers == list(range(1, 15))


def test_bootstrap_runs_the_fixture_before_the_generators() -> None:
    from app.bootstrap import STEPS

    order = [module for module, _, _ in STEPS]
    assert order.index("app.seed") < order.index("app.intake_fixture"), (
        "the fixture references seeded properties and tenants"
    )
    for generator in ("app.archive", "app.sample_operations"):
        assert order.index("app.intake_fixture") < order.index(generator), (
            f"{generator} allocates MAX(case_number)+1 and would take 1-14 first"
        )
    assert order.index("app.backfill_case_history") == len(order) - 1


@pytest.mark.asyncio
async def test_apply_is_idempotent_and_remove_is_exact(intake_env) -> None:
    """Import, re-import, remove -- against a real schema.

    The counts matter less than the fact that this exercises the real
    foreign keys: every ordering bug in this module surfaced only here.
    """
    from app.db import session_scope

    tables = load_dataset()

    first = await apply_fixture(session_scope, tables)
    assert not first.skipped
    assert first.counts["repair_cases"] == 14

    report = await validate(session_scope, tables)
    assert report.passed, [c for c in report.checks if not c.passed]

    present = await status(session_scope, tables)
    assert all(p == e for p, e in present.values())

    second = await apply_fixture(session_scope, tables)
    assert second.skipped, "a second --apply must write nothing"

    # A neighbouring row the fixture does not own must survive --remove.
    async with session_scope() as session:
        before = (
            await session.execute(sa.select(sa.func.count()).select_from(RepairCaseModel))
        ).scalar_one()

    removed = await remove_fixture(session_scope, tables)
    assert removed.found
    assert removed.counts["repair_cases"] == 14

    async with session_scope() as session:
        after = (
            await session.execute(sa.select(sa.func.count()).select_from(RepairCaseModel))
        ).scalar_one()
    assert before - after == 14, "--remove deleted something it did not import"


@pytest.mark.asyncio
async def test_round_trip_preserves_every_captured_row(intake_env) -> None:
    """What is exported is what comes back, including the self-references."""
    from app.db import session_scope

    tables = load_dataset()
    await apply_fixture(session_scope, tables)

    for model in TABLE_ORDER:
        expected = tables.get(model.__tablename__, [])
        if not expected:
            continue
        async with session_scope() as session:
            actual = (
                await session.execute(
                    sa.select(sa.func.count())
                    .select_from(model)
                    .where(model.id.in_([r["id"] for r in expected]))
                )
            ).scalar_one()
        assert actual == len(expected), f"{model.__tablename__}: {actual} of {len(expected)}"

    # The second pass really did restore them, rather than leaving nulls.
    causations = [
        r["causation_event_id"]
        for r in tables["case_events"]
        if r.get("causation_event_id") is not None
    ]
    assert causations, "fixture no longer exercises the self-reference path"
    async with session_scope() as session:
        restored = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(CaseEventModel)
                .where(CaseEventModel.causation_event_id.is_not(None))
            )
        ).scalar_one()
    assert restored == len(causations)


def test_dataset_json_is_stable_on_disk() -> None:
    """Re-exporting an unchanged database must not churn the diff."""
    raw = (
        (load_dataset.__globals__["DATASET_PATH"]).read_text(encoding="utf-8")
    )
    payload = json.loads(raw)
    assert payload["case_count"] == 14
    for rows in payload["tables"].values():
        ids = [r["id"] for r in rows]
        assert ids == sorted(ids), "rows must be written in a stable id order"
