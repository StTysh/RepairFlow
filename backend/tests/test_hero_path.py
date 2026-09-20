"""The hero path (docs/04, docs/20), driven entirely through services +
executor + dispatcher + worker with a FixtureCoordinator standing in for
Gemini. This is the single most important test in the project: roof visit
fails for lack of scaffold access -> prerequisite discovered -> approved ->
installed -> roof rebooked -> completed -> removal released -> approved ->
completed -> tenant confirms -> case resolved.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db import session_scope
from app.domain import services
from app.domain.services import ActorContext
from app.integrations.booking import mock_booking_connector
from app.models import (
    ActionRecordModel,
    AppointmentModel,
    AvailabilityWindowModel,
    CommunicationModel,
    ContractorModel,
    PropertyModel,
    TenantModel,
    WorkOrderModel,
)
from app.orchestration import worker
from app.orchestration.dispatcher import FixtureCoordinator
from app.orchestration.executor import decide_approval
from app.schemas import (
    AcceptReport,
    ActionProposal,
    ActionState,
    AddPrerequisite,
    ApplyTriage,
    AppointmentQuery,
    ApprovalDecision,
    EvidenceRef,
    IntakeSubmission,
    ObservationSubmission,
    Provenance,
    ReportSubmission,
    RequestConfirmation,
    ResolveCase,
    RiskAssessment,
    ScheduleVisit,
    SourceType,
    Trade,
    WorkOrderKind,
)


def uid() -> str:
    return str(uuid.uuid4())


async def _seed_reference_data():
    property_id, tenant_id, roofer_id, scaffolder_id = uid(), uid(), uid(), uid()
    async with session_scope() as session:
        session.add(
            PropertyModel(id=property_id, address_line="1 Test St", postcode="BS1 1AA", landlord_reference="LL-1", roof_responsibility="LANDLORD")
        )
        session.add(
            TenantModel(id=tenant_id, property_id=property_id, display_name="Jordan Hale", preferred_channel="VOICE", contact_allowed=True)
        )
        session.add(
            ContractorModel(id=roofer_id, display_name="Apex Roofing", trades=[Trade.ROOFING.value], service_postcodes=["BS1"], approval_status="APPROVED", connector="MOCK", provenance="SIMULATED")
        )
        session.add(
            ContractorModel(id=scaffolder_id, display_name="Steadfast Scaffold", trades=[Trade.SCAFFOLDING.value], service_postcodes=["BS1"], approval_status="APPROVED", connector="MOCK", provenance="SIMULATED")
        )
    return property_id, tenant_id, roofer_id, scaffolder_id


async def _broad_tenant_window(case_id: str, tenant_id: str) -> None:
    """A wide availability window covering the connector's whole slot
    horizon, so the test doesn't need to hand-compute exact slot times.

    Starts at `now`, not `now + 1 day`. It used to start a day out, which
    silently failed to cover the horizon it advertises: with
    DEMO_SLOT_OFFSET_DAYS=1 the connector's earliest slot is tomorrow
    09:00, and `_first_slot_id` takes slots[0], so any run after 09:00 UTC
    picked a slot that fell before this window began and the booking was
    refused. That made the whole hero path fail by time of day -- green
    every morning, red every afternoon -- and only on a machine whose
    .env compresses the offset to 1."""
    now = datetime.now(timezone.utc)
    async with session_scope() as session:
        window = AvailabilityWindowModel(
            id=uid(), case_id=case_id, person_type="TENANT", person_id=tenant_id,
            start_at=now, end_at=now + timedelta(days=14),
            timezone="Europe/London", confirmed_at=now, expires_at=now + timedelta(days=14),
            source_ref=EvidenceRef(source_type=SourceType.OPERATOR, source_id=uid(), observed_at=now, provenance=Provenance.FIXTURE).model_dump(mode="json"),
            revision=1,
        )
        session.add(window)


async def _first_slot_id(case_id: str, work_order_id: str, contractor_id: str, trade: Trade) -> str:
    async with session_scope() as session:
        slots = await mock_booking_connector.list_slots(
            session, AppointmentQuery(case_id=case_id, work_order_id=work_order_id, contractor_id=contractor_id, tenant_availability_ids=[]),
            trade=trade,
        )
    assert slots, "connector produced no candidate slots"
    return slots[0].slot_id


async def _work_order(case_id: str, kind: str) -> WorkOrderModel:
    async with session_scope() as session:
        wo = (
            await session.execute(select(WorkOrderModel).where(WorkOrderModel.case_id == case_id, WorkOrderModel.kind == kind))
        ).scalars().first()
        assert wo is not None, f"no {kind} work order found"
        session.expunge(wo)
        return wo


async def _approve_latest_awaiting(case_id: str, reason: str, limit_pence: int | None = None) -> None:
    async with session_scope() as session:
        action = (
            await session.execute(
                select(ActionRecordModel).where(ActionRecordModel.case_id == case_id, ActionRecordModel.state == ActionState.AWAITING_APPROVAL.value)
            )
        ).scalars().first()
        assert action is not None, "expected an action awaiting approval"
        case = await services.load_case(session, case_id)
        decision = ApprovalDecision(
            action_id=uuid.UUID(action.id), expected_case_version=case.version, approve=True,
            authorized_limit_pence=limit_pence, reason=reason, action_payload_hash=action.payload_hash,
        )
        await decide_approval(session, decision, ActorContext("OPERATOR", "operator", uid()))


def _schedule_builder(trade: Trade, contractor_id: str, kind: str):
    async def builder(snapshot, trigger_event_id) -> ActionProposal:
        wo = next(w for w in snapshot.work_orders if w.kind.value == kind and w.status.value == "READY")
        slot_id = await _first_slot_id(str(snapshot.case.id), str(wo.id), contractor_id, trade)
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary=f"Book {kind} with approved contractor.", evidence_refs=[],
            action=ScheduleVisit(
                work_order_id=wo.id, contractor_id=uuid.UUID(contractor_id), slot_id=slot_id,
                tenant_availability_ids=[w.id for w in snapshot.availability],
            ),
        )

    return builder


def _accept_report_builder(kind: str, outcome: str = "COMPLETED"):
    async def builder(snapshot, trigger_event_id) -> ActionProposal:
        wo = next(w for w in snapshot.work_orders if w.kind.value == kind)
        report = next(r for r in snapshot.latest_reports if r.work_order_id == wo.id)
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary=f"Accept {kind} completion evidence.", evidence_refs=[],
            action=AcceptReport(report_id=report.id, outcome=outcome, completion_evidence_refs=[]),
        )

    return builder


async def _appointment_for(work_order_id: str, attempt_number: int | None = None) -> AppointmentModel:
    async with session_scope() as session:
        query = select(AppointmentModel).where(AppointmentModel.work_order_id == work_order_id)
        if attempt_number is not None:
            query = query.where(AppointmentModel.attempt_number == attempt_number)
        appt = (await session.execute(query)).scalars().first()
        assert appt is not None
        session.expunge(appt)
        return appt


async def _inject_report(*, work_order_id: str, appointment_id: str, contractor_id: str, text: str) -> None:
    async with session_scope() as session:
        await services.record_contractor_report(
            session,
            submission=ReportSubmission(
                work_order_id=uuid.UUID(work_order_id), appointment_id=uuid.UUID(appointment_id), contractor_id=uuid.UUID(contractor_id),
                text=text, observed_at=datetime.now(timezone.utc),
            ),
            source_ref=EvidenceRef(source_type=SourceType.REPORT, source_id=uid(), observed_at=datetime.now(timezone.utc), provenance=Provenance.SIMULATED),
            provenance=Provenance.SIMULATED, actor=ActorContext("CONTRACTOR_ADAPTER", contractor_id, uid()),
        )


@pytest.mark.asyncio
async def test_hero_roof_scaffold_recovery_loop(app_db):
    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()

    comm_id = uid()
    async with session_scope() as session:
        session.add(
            CommunicationModel(id=comm_id, purpose="INTAKE", direction="BROWSER", correlation_token_hash=uid(), state="ACTIVE", provenance="FIXTURE")
        )

    async with session_scope() as session:
        case_id, result = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description="Water is coming through the rear bedroom ceiling near the roofline.",
                location="Rear bedroom ceiling",
                source_text="novel paraphrase: water dripping from the roof edge into the back bedroom",
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )
    assert result.case_version == 1

    # Initial case must not already contain the scaffold branch (docs/04).
    async with session_scope() as session:
        initial_kinds = (
            await session.execute(select(WorkOrderModel.kind).where(WorkOrderModel.case_id == case_id))
        ).scalars().all()
        assert "SCAFFOLD_INSTALL" not in initial_kinds and "SCAFFOLD_REMOVE" not in initial_kinds

    await _broad_tenant_window(case_id, tenant_id)

    coordinator = FixtureCoordinator()

    async def triage(snapshot, trigger_event_id) -> ActionProposal:
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="Safe, routine roof ingress; dispatch a roofer.", evidence_refs=[],
            action=ApplyTriage(
                risk=RiskAssessment(
                    urgency="ROUTINE", gas="NO", fire="NO", water_near_electrics="NO",
                    structural_danger="NO", uncontrolled_flood="NO", vulnerability_concern="NO",
                ),
                issue_description=snapshot.issue.description,
                suggested_trade=Trade.ROOFING, scope="Inspect and repair roof ingress at the rear bedroom.",
            ),
        )

    coordinator.queue(triage)
    coordinator.queue(_schedule_builder(Trade.ROOFING, roofer_id, "REPAIR"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    repair_wo = await _work_order(case_id, "REPAIR")
    assert repair_wo.status == "SCHEDULED"

    first_repair_appointment = await _appointment_for(repair_wo.id, attempt_number=1)
    await _inject_report(
        work_order_id=repair_wo.id, appointment_id=first_repair_appointment.id, contractor_id=roofer_id,
        text="I got up there but the tiles are beyond safe ladder reach -- I'll need a proper platform rigged up before I can touch them.",
    )

    async def add_prerequisite(snapshot, trigger_event_id) -> ActionProposal:
        pending_report = snapshot.latest_reports[0]
        blocked = next(w for w in snapshot.work_orders if w.kind.value == "REPAIR")
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="Roofer cannot safely reach the tiles; scaffold access is required before repair can proceed.",
            evidence_refs=[EvidenceRef(source_type=SourceType.REPORT, source_id=pending_report.id, observed_at=datetime.now(timezone.utc), provenance=Provenance.SIMULATED)],
            action=AddPrerequisite(
                report_id=pending_report.id, blocked_work_order_id=blocked.id, prerequisite_trade=Trade.SCAFFOLDING,
                prerequisite_kind=WorkOrderKind.SCAFFOLD_INSTALL, prerequisite_scope="Erect scaffold platform for safe roof access.",
                reason="Contractor reports the tiles are not safely reachable by ladder.",
            ),
        )

    coordinator.queue(add_prerequisite)
    coordinator.queue(_schedule_builder(Trade.SCAFFOLDING, scaffolder_id, "SCAFFOLD_INSTALL"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    repair_wo = await _work_order(case_id, "REPAIR")
    scaffold_install = await _work_order(case_id, "SCAFFOLD_INSTALL")
    scaffold_remove = await _work_order(case_id, "SCAFFOLD_REMOVE")
    assert repair_wo.status == "BLOCKED"
    assert scaffold_install.status == "READY", "install work order is READY; the booking action awaits approval"
    assert scaffold_remove.status == "BLOCKED"
    assert scaffold_remove.required_for_resolution is True

    async with session_scope() as session:
        pending = (
            await session.execute(select(ActionRecordModel).where(ActionRecordModel.case_id == case_id, ActionRecordModel.state == ActionState.AWAITING_APPROVAL.value))
        ).scalars().first()
        assert pending is not None and pending.kind == "SCHEDULE_VISIT"

    await _approve_latest_awaiting(case_id, "Approved simulated scaffold installation booking.", limit_pence=30_000)
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    scaffold_install = await _work_order(case_id, "SCAFFOLD_INSTALL")
    assert scaffold_install.status == "SCHEDULED"

    install_appointment = await _appointment_for(scaffold_install.id)
    await _inject_report(
        work_order_id=scaffold_install.id, appointment_id=install_appointment.id, contractor_id=scaffolder_id,
        text="Scaffold is up and access has been handed over safely; roofer is clear to return.",
    )

    coordinator.queue(_accept_report_builder("SCAFFOLD_INSTALL"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    await _approve_latest_awaiting(case_id, "Approved scaffold handover acceptance.")
    coordinator.queue(_schedule_builder(Trade.ROOFING, roofer_id, "REPAIR"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    repair_wo = await _work_order(case_id, "REPAIR")
    scaffold_install = await _work_order(case_id, "SCAFFOLD_INSTALL")
    assert scaffold_install.status == "COMPLETED"
    assert repair_wo.status == "SCHEDULED", "roofing should have been automatically rebooked after scaffold handover"

    async with session_scope() as session:
        repair_appts = (
            await session.execute(select(AppointmentModel).where(AppointmentModel.work_order_id == repair_wo.id))
        ).scalars().all()
        assert len(repair_appts) == 2, "expected the original failed visit plus one rebooked attempt"

    second_repair_appointment = await _appointment_for(repair_wo.id, attempt_number=2)
    await _inject_report(
        work_order_id=repair_wo.id, appointment_id=second_repair_appointment.id, contractor_id=roofer_id,
        text="Roof repair complete, tiles resealed, no further leaks observed from the platform.",
    )

    coordinator.queue(_accept_report_builder("REPAIR"))
    coordinator.queue(_schedule_builder(Trade.SCAFFOLDING, scaffolder_id, "SCAFFOLD_REMOVE"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    repair_wo = await _work_order(case_id, "REPAIR")
    scaffold_remove = await _work_order(case_id, "SCAFFOLD_REMOVE")
    assert repair_wo.status == "COMPLETED"
    assert scaffold_remove.status == "READY", "roofing completion should have released the removal obligation"

    await _approve_latest_awaiting(case_id, "Approved scaffold removal booking.", limit_pence=7_500)
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    scaffold_remove = await _work_order(case_id, "SCAFFOLD_REMOVE")
    assert scaffold_remove.status == "SCHEDULED"

    remove_appointment = await _appointment_for(scaffold_remove.id)
    await _inject_report(
        work_order_id=scaffold_remove.id, appointment_id=remove_appointment.id, contractor_id=scaffolder_id,
        text="Scaffold fully removed and site left tidy.",
    )

    coordinator.queue(_accept_report_builder("SCAFFOLD_REMOVE"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    async def request_confirmation(snapshot, trigger_event_id) -> ActionProposal:
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="All work complete; ask the tenant to confirm resolution.", evidence_refs=[],
            action=RequestConfirmation(issue_id=snapshot.issue.id, questions=["Is the leak fully resolved?"]),
        )

    # Approving this COMPLETED acceptance satisfies the case's last required
    # order, which itself enqueues a fresh COORDINATE run -- queue the next
    # decision *before* draining so it's there when that run fires.
    coordinator.queue(request_confirmation)
    await _approve_latest_awaiting(case_id, "Approved scaffold removal completion evidence.")
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    scaffold_remove = await _work_order(case_id, "SCAFFOLD_REMOVE")
    assert scaffold_remove.status == "COMPLETED"

    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        assert case.status == "AWAITING_CONFIRMATION", "all required work is complete; case should await tenant confirmation"

    async with session_scope() as session:
        confirmation_comm = (
            await session.execute(select(CommunicationModel).where(CommunicationModel.case_id == case_id, CommunicationModel.purpose == "FOLLOW_UP"))
        ).scalars().first()
        assert confirmation_comm is not None
        confirmation_comm_id = confirmation_comm.id

    async with session_scope() as session:
        confirm_result = await services.record_observations(
            session, case_id=case_id, communication_id=confirmation_comm_id,
            submission=ObservationSubmission(communication_id=uuid.UUID(confirmation_comm_id), tenant_confirms_resolved=True, source_text="Yes, all sorted now, thank you!"),
            actor=ActorContext("VOICE_TOOL", confirmation_comm_id, uid()),
        )
    assert confirm_result.event_ids

    async def resolve(snapshot, trigger_event_id) -> ActionProposal:
        confirmation_event = next(e for e in snapshot.recent_events if e.type.value == "TENANT_CONFIRMATION_RECEIVED")
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="Tenant confirmed resolution and all required work is complete; resolve the case.", evidence_refs=[],
            action=ResolveCase(issue_id=snapshot.issue.id, confirmation_event_id=confirmation_event.id),
        )

    coordinator.queue(resolve)
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        assert case.status == "RESOLVED"
