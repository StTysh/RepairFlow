"""Tests for the archive's contractor-report generation (app/archive/dataset.py,
app/archive/importer.py).

Before this, `build_dataset()` produced appointments and COMPLETED work
orders for every resolved archival case but zero `ContractorReportModel`
rows anywhere in the batch -- every sample case showed "No contractor
reports yet" on the ticket detail screen despite having attended visits.
These tests cover the fix: one report per appointment, matching that
appointment's own visit outcome, ordered between the visit and the case's
closure, and cleanly removable with the rest of the batch.

Uses its own `archive_env` fixture (same shape as test_archive_import.py's)
rather than importing that module's, so this file has no dependency on
another test file's internals.
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
from app.archive.dataset import DEFAULT_LABEL, VisitOutcome, build_dataset
from app.archive.importer import import_archive, remove_archive, validate
from app.config import get_settings
from app.models import AppointmentModel, ArchiveBatchModel, ContractorReportModel, WorkOrderModel
from app.schemas import InterpretationStatus, Provenance, WorkOrderStatus


@pytest_asyncio.fixture
async def archive_env() -> AsyncIterator[Path]:
    """Isolated, file-backed temp database *and* a throwaway documents
    directory -- never backend/data/repairflow.db, never real DOCUMENTS_DIR."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    docs_dir = Path(tempfile.mkdtemp(prefix="archive-reports-test-"))

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


LABEL = "test-archive-reports-batch"


# --------------------------------------------------------------------------
# Pure, DB-free checks on build_dataset() -- fast, and pin the generator's
# own invariants independently of the importer.
# --------------------------------------------------------------------------


def test_every_appointment_gets_exactly_one_report():
    dataset = build_dataset()
    resolved_cases_with_appointments = 0
    for case in dataset.cases:
        assert len(case.reports) == len(case.appointments), (
            f"case {case.label}: {len(case.appointments)} appointment(s) but {len(case.reports)} report(s)"
        )
        if case.appointments:
            resolved_cases_with_appointments += 1
    assert resolved_cases_with_appointments > 0, "expected at least one case with appointments"

    # Cancelled cases never had a visit, so they must not get a report either.
    for case in dataset.cases:
        if not case.appointments:
            assert case.reports == []


def test_reports_are_deterministic_across_regenerations():
    a = build_dataset()
    b = build_dataset()
    a_texts = [(c.label, r.id, r.text, r.observed_at, r.received_at) for c in a.cases for r in c.reports]
    b_texts = [(c.label, r.id, r.text, r.observed_at, r.received_at) for c in b.cases for r in c.reports]
    assert a_texts == b_texts


def test_report_timestamps_are_ordered_between_visit_and_closure():
    dataset = build_dataset()
    for case in dataset.cases:
        for i, report in enumerate(case.reports):
            appt = case.appointments[i]
            assert appt.end_at <= report.observed_at, (
                f"case {case.label} report {i}: observed_at before the visit ended"
            )
            assert report.observed_at <= report.received_at, (
                f"case {case.label} report {i}: received_at before observed_at"
            )
            assert report.received_at <= case.archived_closed_at, (
                f"case {case.label} report {i}: received_at after case closure"
            )
            # Never in the future either, transitively: archived_closed_at
            # is itself always in the past (test_audit_regressions.py and
            # this module's own validate() check that already).


def test_non_completed_outcomes_do_not_read_as_completions():
    """A NO_ACCESS/FAILED/BLOCKED visit must produce a report that says so,
    not a completion write-up -- and the wording must actually differ."""
    dataset = build_dataset()
    completion_texts: set[str] = set()
    failure_texts: set[str] = set()
    outcomes_seen: set[VisitOutcome] = set()
    for case in dataset.cases:
        for i, report in enumerate(case.reports):
            outcome = case.appointments[i].visit_outcome
            outcomes_seen.add(outcome)
            if outcome == VisitOutcome.COMPLETED:
                completion_texts.add(report.text)
            else:
                failure_texts.add(report.text)

    # The seeded dataset actually exercises more than just the happy path.
    assert VisitOutcome.COMPLETED in outcomes_seen
    assert outcomes_seen & {VisitOutcome.NO_ACCESS, VisitOutcome.FAILED, VisitOutcome.BLOCKED}

    # No text is shared between a completion and a non-completion outcome --
    # a "completed" write-up never doubles as a failure write-up or vice versa.
    assert completion_texts.isdisjoint(failure_texts)


def test_report_text_is_varied_not_one_template_repeated():
    """Regression guard for "one template repeated 90 times": with ~100+
    reports generated, no single string should account for more than a
    small minority of them."""
    dataset = build_dataset()
    from collections import Counter

    texts = Counter(r.text for case in dataset.cases for r in case.reports)
    total = sum(texts.values())
    assert total > 50, "expected a substantial number of generated reports"
    assert len(texts) >= 20, f"only {len(texts)} distinct report texts across {total} reports"
    most_common_text, most_common_count = texts.most_common(1)[0]
    assert most_common_count <= total * 0.15, (
        f"{most_common_count}/{total} reports share one template: {most_common_text!r}"
    )


# --------------------------------------------------------------------------
# Importer-level checks: rows actually land, are tagged/removable, and the
# new validate() check passes against a real import.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_writes_one_contractor_report_per_appointment(archive_env: Path) -> None:
    dataset = build_dataset(label=LABEL)
    expected_reports = sum(len(c.reports) for c in dataset.cases)
    expected_appointments = sum(len(c.appointments) for c in dataset.cases)
    assert expected_reports == expected_appointments and expected_reports > 0

    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        from app.models import RepairCaseModel

        batch = (
            await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == LABEL))
        ).scalar_one()
        real_case_ids = (
            await session.execute(sa.select(RepairCaseModel.id).where(RepairCaseModel.archive_batch_id == batch.id))
        ).scalars().all()

        reports = (
            await session.execute(sa.select(ContractorReportModel).where(ContractorReportModel.case_id.in_(real_case_ids)))
        ).scalars().all()
        appointments = (
            await session.execute(sa.select(AppointmentModel).where(AppointmentModel.case_id.in_(real_case_ids)))
        ).scalars().all()

    assert len(reports) == expected_reports
    assert len(reports) == len(appointments)

    reported_appointment_ids = {r.appointment_id for r in reports}
    assert reported_appointment_ids == {a.id for a in appointments}

    # Every report carries archival simulation provenance and is already
    # interpreted (a closed historical case has nothing left pending).
    for r in reports:
        assert r.provenance == Provenance.SIMULATED
        assert r.interpretation_status == InterpretationStatus.APPLIED


@pytest.mark.asyncio
async def test_completed_work_orders_have_a_matching_completion_report(archive_env: Path) -> None:
    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        from app.models import RepairCaseModel

        batch = (
            await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == LABEL))
        ).scalar_one()
        case_ids = (
            await session.execute(sa.select(RepairCaseModel.id).where(RepairCaseModel.archive_batch_id == batch.id))
        ).scalars().all()
        work_orders = (
            await session.execute(sa.select(WorkOrderModel).where(WorkOrderModel.case_id.in_(case_ids)))
        ).scalars().all()
        reports_by_id = {
            r.id: r
            for r in (
                await session.execute(
                    sa.select(ContractorReportModel).where(ContractorReportModel.case_id.in_(case_ids))
                )
            ).scalars().all()
        }
        appointments_by_id = {
            a.id: a
            for a in (
                await session.execute(sa.select(AppointmentModel).where(AppointmentModel.case_id.in_(case_ids)))
            ).scalars().all()
        }

    completed = [wo for wo in work_orders if wo.status == WorkOrderStatus.COMPLETED]
    assert completed, "expected at least one COMPLETED archival work order"

    for wo in completed:
        assert wo.completion_report_id, f"work order {wo.id} is COMPLETED with no completion_report_id"
        report = reports_by_id.get(wo.completion_report_id)
        assert report is not None, f"work order {wo.id} completion_report_id does not match any report"
        assert report.work_order_id == wo.id
        appt = appointments_by_id[report.appointment_id]
        assert appt.work_order_id == wo.id
        assert appt.visit_outcome == "COMPLETED"

    # And the inverse: a report behind a NO_ACCESS/FAILED/BLOCKED attempt is
    # never wired up as anyone's completion_report_id.
    completion_report_ids = {wo.completion_report_id for wo in completed}
    for report in reports_by_id.values():
        appt = appointments_by_id[report.appointment_id]
        if appt.visit_outcome != "COMPLETED":
            assert report.id not in completion_report_ids


@pytest.mark.asyncio
async def test_validate_includes_and_passes_contractor_reports_check(archive_env: Path) -> None:
    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        report = await validate(session, label=LABEL)

    by_name = {c.name: c for c in report.checks}
    assert "contractor_reports_complete_and_ordered" in by_name, "expected the new validation check to run"
    assert by_name["contractor_reports_complete_and_ordered"].passed, by_name["contractor_reports_complete_and_ordered"].detail
    assert report.passed is True


@pytest.mark.asyncio
async def test_removal_leaves_no_contractor_report_rows_or_orphans(archive_env: Path) -> None:
    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        before = (await session.execute(sa.select(sa.func.count()).select_from(ContractorReportModel))).scalar_one()
    assert before > 0

    removal = await remove_archive(LABEL)
    assert removal.found is True
    assert removal.counts.get("contractor_reports", 0) == before

    async with db_module.session_scope() as session:
        after = (await session.execute(sa.select(sa.func.count()).select_from(ContractorReportModel))).scalar_one()
        fk_rows = (await session.execute(sa.text("PRAGMA foreign_key_check"))).fetchall()

    assert after == 0
    assert fk_rows == []
