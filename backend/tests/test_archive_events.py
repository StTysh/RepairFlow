"""Tests for the archive's event log + coordinator decision history
(app/archive/dataset.py, app/archive/importer.py).

Before this, `build_dataset()` produced appointments, work orders, costs
and contractor reports for every resolved archival case but zero
CaseEventModel/OrchestrationRunModel rows anywhere in the batch -- every
historical case rendered as a single bare node with no story: no sense of
what came in, what the coordinator decided, or how the case progressed to
closure. These tests cover the fix: a coherent, timestamp-ordered event
log and decision history derived from each case's own structure (work
orders, appointments, visit outcomes, reports, dependencies and closure
date), plus the three hard constraints from the brief: MODEL_ID never
names a real model, CASE_RESOLVED/CASE_CANCELLED land exactly at
archived_closed_at, and none of it is reachable from an operational
surface.

Uses its own `archive_env` fixture (same shape as test_archive_import.py's
and test_archive_reports.py's) rather than importing either of those
modules', so this file has no dependency on another test file's internals.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa

import app.db as db_module
from app.archive.dataset import DEFAULT_LABEL, MODEL_ID, build_dataset
from app.archive.importer import import_archive, remove_archive, validate
from app.config import get_settings
from app.models import (
    ArchiveBatchModel,
    CaseEventModel,
    DependencyModel,
    OrchestrationRunModel,
)
from app.schemas import ActionProposal, CaseStatus, OrchestrationRunState


@pytest_asyncio.fixture
async def archive_env() -> AsyncIterator[Path]:
    """Isolated, file-backed temp database *and* a throwaway documents
    directory -- never backend/data/repairflow.db, never real DOCUMENTS_DIR."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    docs_dir = Path(tempfile.mkdtemp(prefix="archive-events-test-"))

    os.environ["DATABASE_PATH"] = db_path
    os.environ["DOCUMENTS_DIR"] = str(docs_dir)
    get_settings.cache_clear()
    db_module._engine = None
    db_module._session_factory = None

    await db_module.create_all()
    try:
        yield docs_dir
    finally:
        await db_module.dispose_engine()
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("DOCUMENTS_DIR", None)
        get_settings.cache_clear()
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(db_path + suffix)
            if candidate.exists():
                candidate.unlink()
        shutil.rmtree(docs_dir, ignore_errors=True)


LABEL = "test-archive-events-batch"


# --------------------------------------------------------------------------
# Pure, DB-free checks on build_dataset() -- fast, and pin the generator's
# own invariants independently of the importer.
# --------------------------------------------------------------------------


def test_every_case_has_events_and_a_terminal_event():
    dataset = build_dataset()
    assert dataset.cases, "expected at least one archival case"
    for case in dataset.cases:
        assert case.events, f"case {case.label} has no event log"
        expected_terminal = "CASE_RESOLVED" if case.status == CaseStatus.RESOLVED else "CASE_CANCELLED"
        assert case.events[-1].type == expected_terminal, (
            f"case {case.label} terminal event is {case.events[-1].type}, expected {expected_terminal}"
        )


def test_events_and_runs_are_deterministic_across_regenerations():
    a = build_dataset()
    b = build_dataset()
    a_events = [(c.label, [(e.id, e.type, e.occurred_at, e.causation_event_id) for e in c.events]) for c in a.cases]
    b_events = [(c.label, [(e.id, e.type, e.occurred_at, e.causation_event_id) for e in c.events]) for c in b.cases]
    assert a_events == b_events

    a_runs = [(c.label, [(r.id, r.trigger_event_id, r.action["kind"], r.started_at) for r in c.runs]) for c in a.cases]
    b_runs = [(c.label, [(r.id, r.trigger_event_id, r.action["kind"], r.started_at) for r in c.runs]) for c in b.cases]
    assert a_runs == b_runs


def test_event_timestamps_strictly_increasing_and_terminal_equals_closure():
    dataset = build_dataset()
    for case in dataset.cases:
        times = [e.occurred_at for e in case.events]
        assert times == sorted(times), f"case {case.label}: events not chronologically ordered"
        assert len(set(times)) == len(times), f"case {case.label}: two events share one timestamp"
        assert times[-1] == case.archived_closed_at, (
            f"case {case.label}: terminal event at {times[-1]} != archived_closed_at {case.archived_closed_at}"
        )
        assert all(t <= case.archived_closed_at for t in times), f"case {case.label}: an event postdates closure"


def test_causation_and_trigger_ids_resolve_within_the_same_case():
    dataset = build_dataset()
    for case in dataset.cases:
        event_ids = {e.id for e in case.events}
        for e in case.events:
            if e.causation_event_id is not None:
                assert e.causation_event_id in event_ids, (
                    f"case {case.label}: event {e.type} causation_event_id does not resolve within this case"
                )
        for r in case.runs:
            assert r.trigger_event_id in event_ids, (
                f"case {case.label}: run trigger_event_id does not resolve to an event on this case"
            )
            assert r.started_at < r.finished_at


def test_model_id_never_names_a_real_model():
    """Hard constraint: CLAUDE.md prohibits "fake live traces" -- an
    archival OrchestrationRun's model_id must never look like a real
    model (this project's operational model is Gemini), so nobody
    mistakes synthesized reasoning for output a real model produced."""
    dataset = build_dataset()
    assert "gemini" not in MODEL_ID.lower()
    assert MODEL_ID.startswith("fixture:")
    for case in dataset.cases:
        for run in case.runs:
            # dataset.py's ArchiveOrchestrationRun doesn't carry model_id
            # itself (importer.py stamps every run with the one module
            # constant) -- this asserts the constant directly, and the
            # importer-level test below asserts every written row too.
            pass
    assert dataset.cases  # sanity: the loop above wasn't vacuous


def test_action_payloads_validate_against_the_real_action_proposal_schema():
    """Every run's `action` is meant to be a real NextAction payload, not
    an ad hoc dict that merely looks like one -- wrap each in the actual
    ActionProposal envelope and validate it the way importer.py does at
    import time, but here with no database involved."""
    dataset = build_dataset()
    kinds_seen: set[str] = set()
    validated = 0
    for case in dataset.cases:
        for run in case.runs:
            proposal = ActionProposal.model_validate(
                {
                    "case_id": case.id, "expected_case_version": 1, "trigger_event_id": run.trigger_event_id,
                    "decision_summary": run.decision_summary, "evidence_refs": [], "action": run.action,
                }
            )
            kinds_seen.add(proposal.action.kind)
            validated += 1
    assert validated > 0
    # Every action kind the brief calls for is actually exercised somewhere
    # in the generated dataset, not just declared as a possibility.
    assert {"APPLY_TRIAGE", "SCHEDULE_VISIT", "ACCEPT_REPORT", "REQUEST_CONFIRMATION", "RESOLVE_CASE", "ADD_PREREQUISITE"} <= kinds_seen


def test_dependency_cases_have_a_real_backing_row_and_matching_events():
    """DEPENDENCY_DISCOVERED/DEPENDENCY_SATISFIED must point at a real
    dependency (structure), never narrate an event about nothing."""
    dataset = build_dataset()
    dependency_cases = [c for c in dataset.cases if c.dependencies]
    assert dependency_cases, "expected at least one case with a real dependency in the generated seed"
    for case in dependency_cases:
        event_types = [e.type for e in case.events]
        assert "DEPENDENCY_DISCOVERED" in event_types
        assert "DEPENDENCY_SATISFIED" in event_types
        assert event_types.index("DEPENDENCY_DISCOVERED") < event_types.index("DEPENDENCY_SATISFIED")
        for dep in case.dependencies:
            assert 0 <= dep.prerequisite_work_order_index < len(case.work_orders)
            assert 0 <= dep.dependent_work_order_index < len(case.work_orders)
            assert dep.satisfied_at is not None


def test_case_histories_are_not_one_size_fits_all():
    """Regression guard for "every case reads like a three-visit roofing
    job": a single-visit, single-work-order case must have a visibly
    shorter history than a multi-work-order or retried one."""
    dataset = build_dataset()
    resolved = [c for c in dataset.cases if c.status == CaseStatus.RESOLVED]
    event_counts = sorted(len(c.events) for c in resolved)
    assert event_counts[0] < event_counts[-1], "every resolved case has the same-length history"
    assert event_counts[0] <= 9, "the simplest resolved case should be a short, linear story"
    assert event_counts[-1] >= 15, "expected at least one visibly longer, multi-round case"


# --------------------------------------------------------------------------
# Importer-level checks: rows actually land, are removable, and the new
# validate() checks pass against a real import.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_writes_case_events_and_orchestration_runs(archive_env: Path) -> None:
    dataset = build_dataset(label=LABEL)
    expected_events = sum(len(c.events) for c in dataset.cases)
    expected_runs = sum(len(c.runs) for c in dataset.cases)
    expected_deps = sum(len(c.dependencies) for c in dataset.cases)
    assert expected_events > 0 and expected_runs > 0 and expected_deps > 0

    result = await import_archive(db_module.session_scope, label=LABEL)
    assert result.case_event_count == expected_events
    assert result.orchestration_run_count == expected_runs
    assert result.dependency_count == expected_deps

    async with db_module.session_scope() as session:
        batch = (await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == LABEL))).scalar_one()
        events = (await session.execute(sa.select(CaseEventModel))).scalars().all()
        runs = (await session.execute(sa.select(OrchestrationRunModel))).scalars().all()
        deps = (await session.execute(sa.select(DependencyModel))).scalars().all()

    assert len(events) == expected_events
    assert len(runs) == expected_runs
    assert len(deps) == expected_deps

    for run in runs:
        # Hard constraint: never a real model id.
        assert run.model_id == MODEL_ID
        assert "gemini" not in run.model_id.lower()
        assert run.state == OrchestrationRunState.SUCCEEDED
        assert run.proposal is not None and run.proposal["action"]["kind"]
        assert isinstance(run.tool_calls, list)

    for event in events:
        assert event.provenance == "FIXTURE"

    _ = batch  # imported and tagged; nothing further to assert here


@pytest.mark.asyncio
async def test_case_resolved_event_matches_property_history_resolution_date(archive_env: Path) -> None:
    """The exact reconciliation the brief calls out: app.analytics.
    property_history_items reads the CASE_RESOLVED CaseEvent for a
    property-history resolution date, and RepairCaseModel.archived_closed_at
    is what other screens (Property Stats, Reports) use for the same case's
    closure -- both must agree."""
    from app.analytics import property_history_items
    from app.models import RepairCaseModel

    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        batch = (await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == LABEL))).scalar_one()
        resolved_cases = (
            await session.execute(
                sa.select(RepairCaseModel).where(
                    RepairCaseModel.archive_batch_id == batch.id, RepairCaseModel.status == CaseStatus.RESOLVED,
                )
            )
        ).scalars().all()
        assert resolved_cases, "expected at least one resolved archival case"

        property_ids = {c.property_id for c in resolved_cases}
        checked = 0
        for property_id in property_ids:
            items = await property_history_items(session, property_id, include_archived=True)
            for item in items:
                case = next((c for c in resolved_cases if c.id == str(item.case_id)), None)
                if case is None:
                    continue
                assert item.resolved_at is not None, f"case {case.id}: property history has no resolved_at"
                assert item.resolved_at == case.archived_closed_at, (
                    f"case {case.id}: property history shows {item.resolved_at}, "
                    f"archived_closed_at is {case.archived_closed_at}"
                )
                checked += 1
        assert checked == len(resolved_cases)


@pytest.mark.asyncio
async def test_validate_includes_and_passes_the_new_event_checks(archive_env: Path) -> None:
    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        report = await validate(session, label=LABEL)

    by_name = {c.name: c for c in report.checks}
    for name in (
        "every_case_has_an_event_log",
        "event_seq_monotonic_per_case",
        "no_event_postdates_closure",
        "terminal_event_matches_case_closure",
        "run_trigger_resolves_to_same_case_event",
        "no_live_model_id_on_archival_runs",
    ):
        assert name in by_name, f"expected the new validation check {name!r} to run"
        assert by_name[name].passed, f"{name}: {by_name[name].detail}"
    assert report.passed is True


@pytest.mark.asyncio
async def test_removal_leaves_no_event_run_dependency_rows_or_orphans(archive_env: Path) -> None:
    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        events_before = (await session.execute(sa.select(sa.func.count()).select_from(CaseEventModel))).scalar_one()
        runs_before = (await session.execute(sa.select(sa.func.count()).select_from(OrchestrationRunModel))).scalar_one()
        deps_before = (await session.execute(sa.select(sa.func.count()).select_from(DependencyModel))).scalar_one()
    assert events_before > 0 and runs_before > 0 and deps_before > 0

    removal = await remove_archive(LABEL)
    assert removal.found is True
    assert removal.counts.get("case_events", 0) == events_before
    assert removal.counts.get("orchestration_runs", 0) == runs_before
    assert removal.counts.get("dependencies", 0) == deps_before

    async with db_module.session_scope() as session:
        events_after = (await session.execute(sa.select(sa.func.count()).select_from(CaseEventModel))).scalar_one()
        runs_after = (await session.execute(sa.select(sa.func.count()).select_from(OrchestrationRunModel))).scalar_one()
        deps_after = (await session.execute(sa.select(sa.func.count()).select_from(DependencyModel))).scalar_one()
        fk_rows = (await session.execute(sa.text("PRAGMA foreign_key_check"))).fetchall()

    assert events_after == 0
    assert runs_after == 0
    assert deps_after == 0
    assert fk_rows == []


@pytest.mark.asyncio
async def test_archival_events_and_runs_are_invisible_to_operational_surfaces(archive_env: Path) -> None:
    """Archival containment: the new rows must not be reachable from any
    surface that aggregates across every case. analytics.recent_activity
    and services.load_notifications already filter archive_batch_id is
    None on the *case* join (confirmed by reading both before this change);
    this proves it end to end against a real import with real event/run
    rows behind it, not just by reading the query."""
    from app.analytics import recent_activity
    from app.domain.services import load_notifications

    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        activity = await recent_activity(session, limit=50)
        notifications = await load_notifications(session, limit=50)

    assert activity == [], "an archival case's events must never appear in the operational activity feed"
    assert notifications == [], "an archival case must never produce an operational notification"
