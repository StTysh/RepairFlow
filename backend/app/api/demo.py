"""Demo-only controls (docs/16). These submit through the same domain
services as real observations and never set lifecycle status directly."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from typing import Union

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain import services
from app.domain.errors import NotFoundError
from app.domain.services import ActorContext
from app.models import (
    ActionRecordModel,
    AppointmentModel,
    AvailabilityWindowModel,
    CaseEventModel,
    CommunicationModel,
    ContractorCandidateModel,
    ContractorReportModel,
    DependencyModel,
    JobModel,
    MockReservationModel,
    MockSlotModel,
    OrchestrationRunModel,
    RepairCaseModel,
    RepairIssueModel,
    ResearchSnapshotModel,
    WorkOrderModel,
)
from app.schemas import (
    ApprovalResponse,
    CommandResult,
    CommandResultStatus,
    DemoResetResponse,
    DemoSeedRefs,
    DemoTenantFeedbackResponse,
    EvidenceRef,
    IntakeResponse,
    IntakeSubmission,
    ObservationSubmission,
    Provenance,
    ReportSubmission,
    ReportSubmitResponse,
    RiskAssessment,
    SafetyAnswers,
    SimulationObservation,
    SimulationObservationAttendanceWindowEnded,
    SimulationObservationContractorReport,
    SimulationObservationTenantFeedback,
    SourceType,
)

router = APIRouter(prefix="/api/v1/demo", dependencies=[Depends(require_operator)])


@router.get("/seed-refs")
async def demo_seed_refs() -> DemoSeedRefs:
    """The demo property/tenant/contractor IDs (deterministic uuid5s, see
    app/seed.py), seeded idempotently at startup, so the operator UI can
    populate the intake form without a dedicated properties/tenants list
    endpoint -- docs/16 doesn't define one, and this is demo-only glue."""
    from app.seed import DEMO_PROPERTY_ID, DEMO_ROOFER_ID, DEMO_SCAFFOLDER_ID, DEMO_TENANT_ID

    return DemoSeedRefs(
        property_id=DEMO_PROPERTY_ID, tenant_id=DEMO_TENANT_ID, roofer_id=DEMO_ROOFER_ID, scaffolder_id=DEMO_SCAFFOLDER_ID,
    )


class DemoIntakeRequest(BaseModel):
    property_id: uuid.UUID
    tenant_id: uuid.UUID
    description: str
    location: str
    source_text: str
    safety_answers: SafetyAnswers = SafetyAnswers()


@router.post("/intake", status_code=201)
async def demo_intake(request: DemoIntakeRequest, session: AsyncSession = Depends(get_session)) -> IntakeResponse:
    """Labelled captured-intake path (docs/04): no browser voice session
    required. Creates its own FIXTURE Communication, then intakes exactly
    like a real one would once bound."""
    comm_id = str(uuid.uuid4())
    session.add(
        CommunicationModel(
            id=comm_id, purpose="INTAKE", direction="BROWSER", correlation_token_hash=str(uuid.uuid4()),
            state="ENDED", provenance="FIXTURE",
        )
    )
    await session.flush()
    case_id, result = await services.submit_intake(
        session, communication_id=comm_id,
        submission=IntakeSubmission(
            communication_id=uuid.UUID(comm_id), property_id=request.property_id, tenant_id=request.tenant_id,
            description=request.description, location=request.location, source_text=request.source_text,
            safety_answers=request.safety_answers,
        ),
        actor=ActorContext("OPERATOR", "operator", comm_id),
    )
    return IntakeResponse(case_id=case_id, communication_id=comm_id, result=result)


@router.post(
    "/cases/{case_id}/observations", status_code=202,
    response_model=Union[ReportSubmitResponse, DemoTenantFeedbackResponse, ApprovalResponse],
)
async def demo_simulation_observation(case_id: str, observation: SimulationObservation, session: AsyncSession = Depends(get_session)):
    actor = ActorContext("OPERATOR", "operator-demo", str(uuid.uuid4()))

    if isinstance(observation, SimulationObservationContractorReport):
        appointment = await session.get(AppointmentModel, str(observation.appointment_id))
        if appointment is None or appointment.case_id != case_id:
            raise NotFoundError(f"appointment {observation.appointment_id} not in case {case_id}")
        report_id, result = await services.record_contractor_report(
            session,
            submission=ReportSubmission(
                work_order_id=uuid.UUID(appointment.work_order_id), appointment_id=observation.appointment_id,
                contractor_id=uuid.UUID(appointment.contractor_id), text=observation.text, observed_at=observation.observed_at,
            ),
            source_ref=EvidenceRef(source_type=SourceType.OPERATOR, source_id=str(uuid.uuid4()), observed_at=datetime.now(timezone.utc), provenance=Provenance.SIMULATED),
            provenance=Provenance.SIMULATED, actor=actor,
        )
        return ReportSubmitResponse(report_id=report_id, result=result)

    if isinstance(observation, SimulationObservationTenantFeedback):
        case = await services.load_case(session, case_id)
        comm_id = str(uuid.uuid4())
        session.add(
            CommunicationModel(
                id=comm_id, case_id=case_id, tenant_id=case.tenant_id, purpose="FOLLOW_UP", direction="BROWSER",
                correlation_token_hash=str(uuid.uuid4()), state="ENDED", provenance="SIMULATED",
            )
        )
        await session.flush()
        result = await services.record_observations(
            session, case_id=case_id, communication_id=comm_id,
            submission=ObservationSubmission(
                communication_id=uuid.UUID(comm_id), tenant_confirms_resolved=observation.confirms_resolved, source_text=observation.text,
            ),
            actor=actor,
        )
        return DemoTenantFeedbackResponse(communication_id=comm_id, result=result)

    if isinstance(observation, SimulationObservationAttendanceWindowEnded):
        result = await services.mark_attendance_window_ended(session, case_id=case_id, appointment_id=str(observation.appointment_id), actor=actor)
        return ApprovalResponse(result=result)

    raise NotFoundError("unrecognized simulation observation kind")


@router.post("/cases/{case_id}/replay", status_code=202)
async def demo_replay_case(case_id: str, session: AsyncSession = Depends(get_session)) -> IntakeResponse:
    """Demo-only: resets ONE case back to its just-created state -- same
    case_id/case_number, same tenant/property/description/location -- and
    re-triggers the coordinator, so an operator can replay the same ticket
    repeatedly during a demo without retyping an intake each time.

    Unlike /reset, this is a per-case operator choice, not a blanket safety
    scoped wipe: it clears the case's own communications regardless of
    provenance, including any real LIVE call recordings from a prior replay
    of this same case -- selecting "replay this ticket" is exactly asking
    for a clean slate on it."""
    case = await services.load_case(session, case_id)
    issue = await services.load_issue(session, case_id)

    work_order_ids = set(
        (await session.execute(select(WorkOrderModel.id).where(WorkOrderModel.case_id == case_id))).scalars().all()
    )
    if work_order_ids:
        slot_ids = set(
            (await session.execute(select(MockReservationModel.slot_id).where(MockReservationModel.work_order_id.in_(work_order_ids)))).scalars().all()
        )
        await session.execute(delete(MockReservationModel).where(MockReservationModel.work_order_id.in_(work_order_ids)))
        if slot_ids:
            await session.execute(update(MockSlotModel).where(MockSlotModel.slot_id.in_(slot_ids)).values(is_reserved=False))

    # Same deletion order as /reset (children before the parents they
    # reference), minus RepairCaseModel/RepairIssueModel -- those are reset
    # in place below rather than deleted, so case_id/case_number survive.
    for model in (
        DependencyModel, ContractorReportModel, AppointmentModel, OrchestrationRunModel,
        ActionRecordModel, JobModel, ContractorCandidateModel, ResearchSnapshotModel,
        AvailabilityWindowModel, CaseEventModel, WorkOrderModel,
    ):
        await session.execute(delete(model).where(model.case_id == case_id))
    await session.execute(delete(CommunicationModel).where(CommunicationModel.case_id == case_id))

    risk = RiskAssessment(
        urgency="UNKNOWN", gas="UNKNOWN", fire="UNKNOWN", water_near_electrics="UNKNOWN",
        structural_danger="UNKNOWN", uncontrolled_flood="UNKNOWN", vulnerability_concern="UNKNOWN",
    )
    case.status = "ACTIVE"
    case.version = 1
    case.risk = risk.model_dump(mode="json")
    case.last_decision_summary = None
    case.next_follow_up_at = None
    case.escalation_reason = None
    case.resume_status = None
    case.updated_at = datetime.now(timezone.utc)

    issue.evidence_refs = []
    issue.unresolved_concerns = []
    issue.tenant_resolution_confirmed_at = None
    issue.started_at = None

    comm_id = str(uuid.uuid4())
    session.add(
        CommunicationModel(
            id=comm_id, case_id=case_id, tenant_id=case.tenant_id, purpose="INTAKE", direction="BROWSER",
            correlation_token_hash=str(uuid.uuid4()), state="ENDED", provenance="FIXTURE",
        )
    )
    await session.flush()

    actor = ActorContext("OPERATOR", "operator-demo-replay", comm_id)
    event = await services.append_event(
        session, case_id=case_id, event_type="CASE_CREATED",
        payload={"communication_id": comm_id, "replayed": True},
        actor=actor, source_event_key=f"replay:{case_id}:{comm_id}",
    )
    await services.enqueue_job(
        session, case_id=case_id, kind="COORDINATE",
        dedupe_key=f"coordinate:{case_id}:replay:{comm_id}",
        payload={"trigger_event_id": event.id},
    )

    return IntakeResponse(
        case_id=case_id, communication_id=comm_id,
        result=CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id]),
    )


@router.post("/reset", status_code=202)
async def demo_reset(confirm_reset: bool = Query(default=False), session: AsyncSession = Depends(get_session)) -> DemoResetResponse:
    """Clears synthetic case data. Preserves any Communication carrying LIVE
    provenance (a real captured call) and the case it belongs to, per
    docs/17: reset must not silently delete evidence used to demonstrate a
    live integration passed."""
    if not confirm_reset:
        return DemoResetResponse(cleared=False, reason="confirm_reset=true required")

    live_case_ids = set(
        (await session.execute(select(CommunicationModel.case_id).where(CommunicationModel.provenance == "LIVE", CommunicationModel.case_id.is_not(None)))).scalars().all()
    )
    all_case_ids = set((await session.execute(select(RepairCaseModel.id))).scalars().all())
    clearable = all_case_ids - live_case_ids

    if not clearable:
        return DemoResetResponse(cleared=True, case_count=0, preserved_live_cases=len(live_case_ids))

    # MockReservationModel/MockSlotModel have no case_id column (slots are
    # contractor calendar state, shared across cases); scope the cleanup
    # through the work orders being cleared instead, and release rather than
    # delete slots so the contractor's mock calendar stays consistent.
    work_order_ids = set(
        (await session.execute(select(WorkOrderModel.id).where(WorkOrderModel.case_id.in_(clearable)))).scalars().all()
    )
    if work_order_ids:
        slot_ids = set(
            (await session.execute(select(MockReservationModel.slot_id).where(MockReservationModel.work_order_id.in_(work_order_ids)))).scalars().all()
        )
        await session.execute(delete(MockReservationModel).where(MockReservationModel.work_order_id.in_(work_order_ids)))
        if slot_ids:
            await session.execute(update(MockSlotModel).where(MockSlotModel.slot_id.in_(slot_ids)).values(is_reserved=False))

    # Deletion order respects FKs: children before the parents they
    # reference. Dependency -> ContractorReport -> Appointment -> ActionRecord
    # is the load-bearing chain (each references the next); everything else
    # only needs to precede WorkOrder/CaseEvent/RepairCase.
    for model in (
        DependencyModel, ContractorReportModel, AppointmentModel, OrchestrationRunModel,
        ActionRecordModel, JobModel, ContractorCandidateModel, ResearchSnapshotModel,
        AvailabilityWindowModel, CaseEventModel, WorkOrderModel, RepairIssueModel,
    ):
        await session.execute(delete(model).where(model.case_id.in_(clearable)))

    await session.execute(delete(CommunicationModel).where(CommunicationModel.case_id.in_(clearable), CommunicationModel.provenance != "LIVE"))
    await session.execute(delete(RepairCaseModel).where(RepairCaseModel.id.in_(clearable)))

    return DemoResetResponse(cleared=True, case_count=len(clearable), preserved_live_cases=len(live_case_ids))
