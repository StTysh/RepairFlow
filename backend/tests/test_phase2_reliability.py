"""docs/21 Phase 2's own gate, beyond the hero path itself: "restart and
duplicate report." The broader docs/22 matrix belongs in Phase 9; these two
protect exactly what Phase 2 just built.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

import app.db as db_module
from app.config import get_settings
from app.db import create_all, session_scope
from app.domain import services
from app.domain.services import ActorContext
from app.models import (
    ActionRecordModel,
    AppointmentModel,
    CaseEventModel,
    ContractorReportModel,
    DependencyModel,
    WorkOrderModel,
)
from app.orchestration import worker
from app.orchestration.dispatcher import FixtureCoordinator
from app.schemas import (
    AcceptReport,
    ActionProposal,
    AddPrerequisite,
    ApplyTriage,
    EvidenceRef,
    IntakeSubmission,
    Provenance,
    ReportSubmission,
    RiskAssessment,
    SourceType,
    Trade,
    WorkOrderKind,
)

from tests.test_hero_path import (
    _accept_report_builder,
    _appointment_for,
    _approve_latest_awaiting,
    _broad_tenant_window,
    _first_slot_id,
    _schedule_builder,
    _seed_reference_data,
    _work_order,
    uid,
)


async def _drive_to_blocked_repair(comm_id: str, property_id: str, tenant_id: str, roofer_id: str, scaffolder_id: str):
    """Shared setup: intake through a failed roofing visit whose report has
    already triggered ADD_PREREQUISITE and a scaffold booking proposal is
    sitting AWAITING_APPROVAL -- REPAIR BLOCKED, SCAFFOLD_INSTALL READY,
    one pending operator decision. Mirrors the hero test's first checkpoint."""
    async with session_scope() as session:
        from app.models import CommunicationModel

        session.add(
            CommunicationModel(id=comm_id, purpose="INTAKE", direction="BROWSER", correlation_token_hash=uid(), state="ACTIVE", provenance="FIXTURE")
        )

    async with session_scope() as session:
        case_id, _ = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description="Water ingress near the roofline.", location="Rear bedroom ceiling", source_text="src",
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )
    await _broad_tenant_window(case_id, tenant_id)

    coordinator = FixtureCoordinator()

    async def triage(snapshot, trigger_event_id) -> ActionProposal:
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="Safe, routine roof ingress.", evidence_refs=[],
            action=ApplyTriage(
                risk=RiskAssessment(urgency="ROUTINE", gas="NO", fire="NO", water_near_electrics="NO", structural_danger="NO", uncontrolled_flood="NO", vulnerability_concern="NO"),
                issue_description=snapshot.issue.description, suggested_trade=Trade.ROOFING, scope="Repair roof ingress.",
            ),
        )

    coordinator.queue(triage)
    coordinator.queue(_schedule_builder(Trade.ROOFING, roofer_id, "REPAIR"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    repair_wo = await _work_order(case_id, "REPAIR")
    first_appt = await _appointment_for(repair_wo.id, attempt_number=1)

    report_text = "Tiles are beyond safe ladder reach; scaffold platform needed."
    async with session_scope() as session:
        report_id, _ = await services.record_contractor_report(
            session,
            submission=ReportSubmission(
                work_order_id=uuid.UUID(repair_wo.id), appointment_id=uuid.UUID(first_appt.id), contractor_id=uuid.UUID(roofer_id),
                text=report_text, observed_at=datetime.now(timezone.utc),
            ),
            source_ref=EvidenceRef(source_type=SourceType.REPORT, source_id=uid(), observed_at=datetime.now(timezone.utc), provenance=Provenance.SIMULATED),
            provenance=Provenance.SIMULATED, actor=ActorContext("CONTRACTOR_ADAPTER", roofer_id, uid()),
        )

    async def add_prerequisite(snapshot, trigger_event_id) -> ActionProposal:
        pending_report = snapshot.latest_reports[0]
        blocked = next(w for w in snapshot.work_orders if w.kind.value == "REPAIR")
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="Scaffold required.",
            evidence_refs=[EvidenceRef(source_type=SourceType.REPORT, source_id=pending_report.id, observed_at=datetime.now(timezone.utc), provenance=Provenance.SIMULATED)],
            action=AddPrerequisite(
                report_id=pending_report.id, blocked_work_order_id=blocked.id, prerequisite_trade=Trade.SCAFFOLDING,
                prerequisite_kind=WorkOrderKind.SCAFFOLD_INSTALL, prerequisite_scope="Erect scaffold.",
                reason="No safe ladder access.",
            ),
        )

    coordinator.queue(add_prerequisite)
    coordinator.queue(_schedule_builder(Trade.SCAFFOLDING, scaffolder_id, "SCAFFOLD_INSTALL"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    return case_id, report_id, coordinator


@pytest.mark.asyncio
async def test_duplicate_report_and_duplicate_prerequisite_are_noop(app_db):
    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    case_id, report_id, coordinator = await _drive_to_blocked_repair(uid(), property_id, tenant_id, roofer_id, scaffolder_id)

    repair_wo = await _work_order(case_id, "REPAIR")
    assert repair_wo.status == "BLOCKED"

    async with session_scope() as session:
        reports_before = (await session.execute(select(ContractorReportModel).where(ContractorReportModel.case_id == case_id))).scalars().all()
        deps_before = (await session.execute(select(DependencyModel).where(DependencyModel.case_id == case_id))).scalars().all()
    assert len(reports_before) == 1
    assert len(deps_before) == 2, "install->repair and repair->removal"

    first_appt = await _appointment_for(repair_wo.id, attempt_number=1)

    # Redeliver the identical report (e.g. a retried webhook / duplicate submission).
    async with session_scope() as session:
        case_before = await services.load_case(session, case_id)
        version_before = case_before.version
        report_id_2, dup_result = await services.record_contractor_report(
            session,
            submission=ReportSubmission(
                work_order_id=uuid.UUID(repair_wo.id), appointment_id=uuid.UUID(first_appt.id), contractor_id=uuid.UUID(roofer_id),
                text="Tiles are beyond safe ladder reach; scaffold platform needed.", observed_at=(
                    (await session.get(ContractorReportModel, report_id)).observed_at
                ),
            ),
            source_ref=EvidenceRef(source_type=SourceType.REPORT, source_id=uid(), observed_at=datetime.now(timezone.utc), provenance=Provenance.SIMULATED),
            provenance=Provenance.SIMULATED, actor=ActorContext("CONTRACTOR_ADAPTER", roofer_id, uid()),
        )
    assert report_id_2 == report_id
    assert dup_result.status.value == "NOOP"
    assert dup_result.case_version == version_before, "a true duplicate must not bump the case version"

    async with session_scope() as session:
        reports_after = (await session.execute(select(ContractorReportModel).where(ContractorReportModel.case_id == case_id))).scalars().all()
    assert len(reports_after) == 1, "duplicate report must not create a second row"

    # Re-admitting the SAME AddPrerequisite proposal (e.g. two coordinate
    # runs racing on the same report) must not create a second scaffold order/edge.
    async with session_scope() as session:
        blocked = await session.get(WorkOrderModel, repair_wo.id)
        case_now = await services.load_case(session, case_id)
        report = await session.get(ContractorReportModel, report_id)
        replay_result = await services.add_prerequisite(
            session, case_id=case_id,
            action=AddPrerequisite(
                report_id=uuid.UUID(report.id), blocked_work_order_id=uuid.UUID(blocked.id), prerequisite_trade=Trade.SCAFFOLDING,
                prerequisite_kind=WorkOrderKind.SCAFFOLD_INSTALL, prerequisite_scope="Erect scaffold.", reason="No safe ladder access.",
            ),
            action_id=uid(), trigger_event_id=uid(), actor=ActorContext("COORDINATOR", "test", uid()),
        )
    assert replay_result.status.value == "NOOP"

    async with session_scope() as session:
        work_orders = (await session.execute(select(WorkOrderModel).where(WorkOrderModel.case_id == case_id))).scalars().all()
        deps_after = (await session.execute(select(DependencyModel).where(DependencyModel.case_id == case_id))).scalars().all()
    scaffold_installs = [w for w in work_orders if w.kind == "SCAFFOLD_INSTALL"]
    scaffold_removes = [w for w in work_orders if w.kind == "SCAFFOLD_REMOVE"]
    assert len(scaffold_installs) == 1, "duplicate prerequisite discovery must not create a second scaffold order"
    assert len(scaffold_removes) == 1
    assert len(deps_after) == 2, "still exactly install->repair and repair->removal, no extra edges"


@pytest.mark.asyncio
async def test_restart_while_blocked_preserves_state_and_resumes(app_db):
    """Disposes the engine and reconnects to the SAME on-disk database,
    simulating a process restart, then verifies the graph survived and a
    fresh worker can still approve/execute the rest of the loop."""
    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    case_id, report_id, _old_coordinator = await _drive_to_blocked_repair(uid(), property_id, tenant_id, roofer_id, scaffolder_id)

    async with session_scope() as session:
        case_before = await services.load_case(session, case_id)
        version_before = case_before.version
        events_before = (
            await session.execute(select(CaseEventModel).where(CaseEventModel.case_id == case_id))
        ).scalars().all()
    repair_wo_before = await _work_order(case_id, "REPAIR")
    scaffold_install_before = await _work_order(case_id, "SCAFFOLD_INSTALL")
    assert repair_wo_before.status == "BLOCKED"
    assert scaffold_install_before.status == "READY"

    # --- simulate a process restart: tear down and rebuild the engine
    # against the exact same file, exactly as a new `uvicorn` process would ---
    db_path = get_settings().database_path
    await db_module.dispose_engine()
    db_module._engine = None
    db_module._session_factory = None
    get_settings.cache_clear()
    import os

    os.environ["DATABASE_PATH"] = str(db_path)
    await create_all()  # idempotent: tables already exist

    async with session_scope() as session:
        case_after = await services.load_case(session, case_id)
        events_after = (
            await session.execute(select(CaseEventModel).where(CaseEventModel.case_id == case_id))
        ).scalars().all()
    assert case_after.version == version_before
    assert len(events_after) == len(events_before)

    repair_wo_after = await _work_order(case_id, "REPAIR")
    scaffold_install_after = await _work_order(case_id, "SCAFFOLD_INSTALL")
    assert repair_wo_after.status == "BLOCKED"
    assert scaffold_install_after.status == "READY"

    # The scaffold booking proposed before the "restart" is still sitting
    # AWAITING_APPROVAL -- a fresh worker/coordinator (new process) approves
    # and resumes it without anything having been lost.
    async with session_scope() as session:
        pending = (
            await session.execute(select(ActionRecordModel).where(ActionRecordModel.case_id == case_id, ActionRecordModel.state == "AWAITING_APPROVAL"))
        ).scalars().first()
        assert pending is not None and pending.kind == "SCHEDULE_VISIT"

    new_coordinator = FixtureCoordinator()
    await _approve_latest_awaiting(case_id, "Approved after restart.", limit_pence=30_000)
    await worker.drain_due_jobs(new_coordinator, raise_on_error=True)

    scaffold_install_final = await _work_order(case_id, "SCAFFOLD_INSTALL")
    assert scaffold_install_final.status == "SCHEDULED", "case resumed correctly after the simulated restart"
