"""Tests for app.sample_operations and app.backfill_case_history.

Both modules write *operational* rows -- rows the dashboard, the ticket
list and the metrics all count -- so the invariants worth pinning here are
the ones whose violation puts something untrue on an operator's screen:

* a generated orchestration run left at the model default (`RUNNING`)
  makes `agent_active` true forever, which is a spinner asserting the
  coordinator is mid-flight when nothing is running at all;
* a RESOLVED case with no `CASE_RESOLVED` event is invisible to both
  `resolved_this_week` and `avg_resolution_hours`;
* a case that already holds real ElevenLabs call evidence must never be
  rewritten by the backfill.

Uses its own temp-database fixture for the same reason
`test_archive_import.py` does.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa

import app.db as db_module
from app import backfill_case_history, sample_operations
from app.config import get_settings
from app.domain import services
from app.models import (
    CaseEventModel,
    CommunicationModel,
    ContractorModel,
    JobModel,
    OrchestrationRunModel,
    PropertyModel,
    RepairCaseModel,
    RepairIssueModel,
    TenantModel,
    WorkOrderModel,
)
from app.schemas import (
    CaseStatus,
    ConnectorType,
    ContractorApprovalStatus,
    OrchestrationRunState,
    Provenance,
    RoofResponsibility,
    Trade,
    WorkOrderKind,
    WorkOrderStatus,
)


@pytest_asyncio.fixture
async def ops_env() -> AsyncIterator[None]:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    docs_dir = Path(tempfile.mkdtemp(prefix="sample-ops-docs-"))
    os.environ["DATABASE_PATH"] = db_path
    os.environ["DOCUMENTS_DIR"] = str(docs_dir)
    get_settings.cache_clear()
    db_module._engine = None
    db_module._session_factory = None
    await db_module.create_all()
    try:
        yield None
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


def _uid(label: str) -> str:
    """Deterministic UUID for the fixture.

    The read schemas (`RepairCase`, `AssignedContractor`, ...) validate
    these ids as real UUIDs, so a readable-but-invalid id like "con-0"
    makes the fixture fail for a reason unrelated to the code under test.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"repairflow.test.sample-ops:{label}"))


PROP_ID = _uid("property")
CASE_PLAIN = _uid("case-plain")
CASE_LIVE = _uid("case-live")
TENANT_ID = _uid("tenant")


async def _seed_reference() -> None:
    """The minimum the generator needs: a property, a tenant, contractors
    covering every trade it might ask for."""
    async with db_module.session_scope() as session:
        session.add(PropertyModel(
            id=PROP_ID, address_line="1 Test Street", postcode="BS1 1AA",
            timezone="Europe/London", landlord_reference="LL-1",
            roof_responsibility=RoofResponsibility.LANDLORD, access_notes="",
        ))
        session.add(TenantModel(
            id=TENANT_ID, property_id=PROP_ID, display_name="Test Tenant",
            phone_e164="+441170000000", email="t@example.invalid",
            preferred_channel="VOICE", contact_allowed=True,
        ))
        for i, trade in enumerate(Trade):
            session.add(ContractorModel(
                id=_uid(f"contractor-{trade.value}"), display_name=f"Test {trade.value} Ltd (fictional, SIMULATED)",
                trades=[trade.value], service_postcodes=["BS1"],
                approval_status=ContractorApprovalStatus.APPROVED,
                connector=ConnectorType.MOCK, contact_reference=f"mock:{trade.value.lower()}",
                verification_note="test fixture", provenance=Provenance.SIMULATED, workers=[],
            ))


# --------------------------------------------------------------------------
# sample_operations
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_writes_every_scenario_and_validates(ops_env: None) -> None:
    await _seed_reference()
    async with db_module.session_scope() as session:
        counts = await sample_operations.apply(session)
    assert counts["cases"] == len(sample_operations.SCENARIOS)

    async with db_module.session_scope() as session:
        results = await sample_operations.validate(session)
    failures = [(label, detail) for ok, label, detail in results if not ok]
    assert not failures, f"validation failures: {failures}"


@pytest.mark.asyncio
async def test_generated_runs_are_not_left_running(ops_env: None) -> None:
    """The bug this pins: `OrchestrationRunModel.state` defaults to
    RUNNING. Generated history that leaves it there makes the dashboard's
    `agent_active` true permanently -- the UI claims the coordinator is
    working on something when the queue is empty and nothing is in flight.

    Revert the explicit `state=` in sample_operations._CaseBuilder.run and
    this fails.
    """
    await _seed_reference()
    async with db_module.session_scope() as session:
        await sample_operations.apply(session)

    async with db_module.session_scope() as session:
        running = (await session.execute(
            sa.select(sa.func.count()).select_from(OrchestrationRunModel)
            .where(OrchestrationRunModel.state == OrchestrationRunState.RUNNING)
        )).scalar_one()
        total = (await session.execute(
            sa.select(sa.func.count()).select_from(OrchestrationRunModel)
        )).scalar_one()
    assert total > 0, "no runs were generated, so this test proves nothing"
    assert running == 0, f"{running} of {total} generated runs left in RUNNING"


@pytest.mark.asyncio
async def test_generated_history_enqueues_no_jobs(ops_env: None) -> None:
    """A job is an instruction to go and act. Generated history must never
    cause the worker to wake up and work a case nobody filed."""
    await _seed_reference()
    async with db_module.session_scope() as session:
        await sample_operations.apply(session)
    async with db_module.session_scope() as session:
        jobs = (await session.execute(sa.select(sa.func.count()).select_from(JobModel))).scalar_one()
    assert jobs == 0


@pytest.mark.asyncio
async def test_metrics_the_generator_exists_to_populate(ops_env: None) -> None:
    """The point of the module: these three are 0/0/None on an empty
    workspace, and an operator reads that as a broken dashboard."""
    await _seed_reference()
    async with db_module.session_scope() as session:
        await sample_operations.apply(session)

    async with db_module.session_scope() as session:
        operational = RepairCaseModel.archive_batch_id.is_(None)
        rows = (await session.execute(
            sa.select(RepairCaseModel.status, sa.func.count()).where(operational)
            .group_by(RepairCaseModel.status)
        )).all()
        counts = {(s.value if hasattr(s, "value") else s): n for s, n in rows}

        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        resolved_this_week = (await session.execute(
            sa.select(sa.func.count(sa.func.distinct(CaseEventModel.case_id)))
            .join(RepairCaseModel, RepairCaseModel.id == CaseEventModel.case_id)
            .where(CaseEventModel.type == "CASE_RESOLVED",
                   CaseEventModel.occurred_at >= week_ago, operational)
        )).scalar_one()
        avg = await services.average_resolution_hours(session)

    assert counts.get("AWAITING_CONFIRMATION", 0) > 0
    assert counts.get("ESCALATED", 0) > 0
    assert counts.get("CANCELLED", 0) > 0
    assert resolved_this_week > 0
    assert avg is not None and avg > 0, "average resolution time must be a real duration"


@pytest.mark.asyncio
async def test_apply_is_idempotent_and_remove_is_exact(ops_env: None) -> None:
    await _seed_reference()
    async with db_module.session_scope() as session:
        first = await sample_operations.apply(session)
    async with db_module.session_scope() as session:
        second = await sample_operations.apply(session)
    assert second["cases"] == 0
    assert second["skipped"] == len(sample_operations.SCENARIOS)

    async with db_module.session_scope() as session:
        removed = await sample_operations.remove(session)
    assert removed["repair_cases"] == first["cases"]

    async with db_module.session_scope() as session:
        left = (await session.execute(
            sa.select(sa.func.count()).select_from(RepairCaseModel)
        )).scalar_one()
        orphan_events = (await session.execute(
            sa.select(sa.func.count()).select_from(CaseEventModel)
        )).scalar_one()
    assert left == 0 and orphan_events == 0, "remove left rows behind"


@pytest.mark.asyncio
async def test_no_future_appointment_is_marked_confirmed(ops_env: None) -> None:
    """Provider request acceptance is not booking confirmation: a visit
    nobody has acknowledged is PENDING."""
    await _seed_reference()
    async with db_module.session_scope() as session:
        await sample_operations.apply(session)
    async with db_module.session_scope() as session:
        from app.models import AppointmentModel
        from app.schemas import AppointmentStatus
        bad = (await session.execute(
            sa.select(sa.func.count()).select_from(AppointmentModel)
            .where(AppointmentModel.start_at > datetime.now(timezone.utc),
                   AppointmentModel.status == AppointmentStatus.CONFIRMED)
        )).scalar_one()
    assert bad == 0


# --------------------------------------------------------------------------
# backfill_case_history
# --------------------------------------------------------------------------


async def _case_without_events(case_id: str, *, status: CaseStatus, live: bool) -> None:
    now = datetime.now(timezone.utc)
    async with db_module.session_scope() as session:
        session.add(RepairCaseModel(
            id=case_id, case_number=900 + (abs(hash(case_id)) % 90), property_id=PROP_ID, tenant_id=TENANT_ID,
            status=status, version=1, title="Historic case with no event log", risk={},
            created_at=now - timedelta(days=30), updated_at=now - timedelta(days=28),
            owner_operator_id="operator", category=Trade.PLUMBING,
        ))
        await session.flush()
        session.add(RepairIssueModel(
            id=_uid(f"issue-{case_id}"), case_id=case_id, description="The thing is broken.",
            location="Kitchen", evidence_refs=[], unresolved_concerns=[],
        ))
        await session.flush()
        session.add(WorkOrderModel(
            id=_uid(f"wo-{case_id}"), case_id=case_id, issue_id=_uid(f"issue-{case_id}"),
            kind=WorkOrderKind.REPAIR, trade=Trade.PLUMBING, scope="Fix the thing.",
            status=WorkOrderStatus.COMPLETED, contractor_id=_uid("contractor-PLUMBING"),
            required_for_resolution=True, created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=28),
        ))
        if live:
            await session.flush()
            session.add(CommunicationModel(
                id=_uid(f"comm-{case_id}"), case_id=case_id, tenant_id=TENANT_ID, purpose="INTAKE",
                direction="OUTBOUND", provider="elevenlabs", state="ENDED",
                correlation_token_hash=_uid(f"hash-{case_id}"),
                started_at=now - timedelta(days=30), provenance=Provenance.LIVE,
            ))


@pytest.mark.asyncio
async def test_backfill_gives_a_resolved_case_its_resolution_event(ops_env: None) -> None:
    await _seed_reference()
    await _case_without_events(CASE_PLAIN, status=CaseStatus.RESOLVED, live=False)

    async with db_module.session_scope() as session:
        eligible, skipped = await backfill_case_history._targets(session)
    assert [c.id for c, _, _ in eligible] == [CASE_PLAIN]
    assert skipped == []

    await backfill_case_history._run(apply=True)

    async with db_module.session_scope() as session:
        types = list((await session.execute(
            sa.select(CaseEventModel.type).where(CaseEventModel.case_id == CASE_PLAIN)
            .order_by(CaseEventModel.seq)
        )).scalars())
    assert "CASE_RESOLVED" in types, f"got {types}"
    assert types[0] == "CASE_CREATED"


@pytest.mark.asyncio
async def test_backfill_never_touches_a_case_with_live_evidence(ops_env: None) -> None:
    """Cases carrying real recorded calls are left exactly as they are.
    Writing a synthetic decision on top of real call evidence would be a
    fabricated live trace, which the project prohibits outright.
    """
    await _seed_reference()
    await _case_without_events(CASE_LIVE, status=CaseStatus.RESOLVED, live=True)

    async with db_module.session_scope() as session:
        eligible, skipped = await backfill_case_history._targets(session)
    assert eligible == []
    assert [number for number, _ in skipped], "the live case should be reported as skipped"

    await backfill_case_history._run(apply=True)

    async with db_module.session_scope() as session:
        events = (await session.execute(
            sa.select(sa.func.count()).select_from(CaseEventModel)
            .where(CaseEventModel.case_id == CASE_LIVE)
        )).scalar_one()
    assert events == 0, "backfill wrote events onto a case with live call evidence"


@pytest.mark.asyncio
async def test_backfilled_runs_are_not_left_running(ops_env: None) -> None:
    await _seed_reference()
    await _case_without_events(CASE_PLAIN, status=CaseStatus.RESOLVED, live=False)
    await backfill_case_history._run(apply=True)

    async with db_module.session_scope() as session:
        running = (await session.execute(
            sa.select(sa.func.count()).select_from(OrchestrationRunModel)
            .where(OrchestrationRunModel.state == OrchestrationRunState.RUNNING)
        )).scalar_one()
        total = (await session.execute(
            sa.select(sa.func.count()).select_from(OrchestrationRunModel)
        )).scalar_one()
    assert total > 0
    assert running == 0


# --------------------------------------------------------------------------
# Regressions found by exercising the HTTP surface, not by reading the code
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_generated_case_snapshot_loads(ops_env: None) -> None:
    """`GET /cases/{id}` returned 500 for all 20 generated cases that had a
    contractor report.

    `ContractorReportModel.source_ref` is a free-form JSON column, so an
    ad-hoc dict is accepted on write -- but `services.load_case_snapshot`
    revalidates it as an `EvidenceRef`, and the wrong shape only surfaces
    later, as a 500 on the one page an operator opens most.

    Put any dict back in `source_ref` and this fails.
    """
    await _seed_reference()
    async with db_module.session_scope() as session:
        await sample_operations.apply(session)

    failures: list[tuple[int, str]] = []
    async with db_module.session_scope() as session:
        cases = list((await session.execute(
            sa.select(RepairCaseModel).order_by(RepairCaseModel.case_number)
        )).scalars())
        assert cases, "no cases generated, so this test proves nothing"
        for case in cases:
            try:
                await services.load_case_snapshot(session, case.id)
            except Exception as exc:  # noqa: BLE001 - the point is to report any failure
                failures.append((case.case_number, f"{type(exc).__name__}: {exc}"[:200]))
    assert not failures, f"case snapshot failed to load: {failures}"


@pytest.mark.asyncio
async def test_every_generated_run_proposal_revalidates(ops_env: None) -> None:
    """`GET /cases/{id}/runs` returned 500 for every backfilled case.

    The endpoint revalidates each stored proposal as an `OrchestrationRun`.
    A proposal written with `report_id: None` (an ACCEPT_REPORT decision on
    a case that has no report) is a UUID field set to null: invalid, and
    also a decision that could never have been made. Both generators are
    covered here.
    """
    await _seed_reference()
    await _case_without_events(CASE_PLAIN, status=CaseStatus.RESOLVED, live=False)
    async with db_module.session_scope() as session:
        await sample_operations.apply(session)
    await backfill_case_history._run(apply=True)

    from app.schemas import OrchestrationRun

    failures: list[str] = []
    async with db_module.session_scope() as session:
        runs = list((await session.execute(sa.select(OrchestrationRunModel))).scalars())
        assert runs, "no runs generated, so this test proves nothing"
        for run in runs:
            try:
                OrchestrationRun.model_validate(run)
            except Exception as exc:  # noqa: BLE001
                kind = ((run.proposal or {}).get("action") or {}).get("kind")
                failures.append(f"{run.model_id} {kind}: {str(exc)[:160]}")
    assert not failures, f"{len(failures)} run(s) failed revalidation: {failures[:3]}"
