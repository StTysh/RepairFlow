"""Case reads, intake, reports, communications, research, appointments and
lifecycle transitions (docs/16). Bundled per the project's expected
structure (one router per concern group, not one route per file).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import analytics
from app.api.deps import get_session, require_operator
from app.domain import services
from app.domain.errors import ConflictError, DomainError, NotFoundError, PolicyRejectedError
from app.domain.services import ActorContext
from app.domain.transitions import assert_case_transition
from app.models import (
    CaseEventModel,
    CommunicationModel,
    OrchestrationRunModel,
    PropertyModel,
    RepairCaseModel,
    RepairIssueModel,
    ResearchSnapshotModel,
    TenantModel,
    WorkOrderModel,
)
from app.schemas import (
    AppointmentCancelResponse,
    CancelCaseRequest,
    CancellationRequest,
    CaseDetailResponse,
    CaseEventsResponse,
    CaseListItem,
    CaseListResponse,
    CaseMessagesResponse,
    CaseRunsResponse,
    CaseStatus,
    CaseVersionResponse,
    CommandResult,
    CommandResultStatus,
    Communication,
    IntakeResponse,
    IntakeSubmission,
    OrchestrationRun,
    PropertyHistoryResponse,
    PropertyStatsResponse,
    ReopenCaseRequest,
    ReportSubmission,
    ReportSubmitResponse,
    ResearchSnapshot,
    RetryRecordingResponse,
    SafetyAnswers,
    Trade,
    ResumeCaseRequest,
    UpcomingAppointmentsResponse,
    EvidenceRef,
    Provenance,
    SourceType,
    ReadinessResponse,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])


@router.get("/readiness")
async def readiness(session: AsyncSession = Depends(get_session)) -> ReadinessResponse:
    from app.config import get_settings

    settings = get_settings()
    await session.execute(select(1))
    return ReadinessResponse(
        database="ok", gemini_live=settings.gemini_live, elevenlabs_live=settings.elevenlabs_live, tavily_live=settings.tavily_live,
    )


@router.get("/cases")
async def list_cases(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    status: CaseStatus | None = None,
    property_id: str | None = None,
    q: str | None = None,
    contractor_id: str | None = None,
    category: Trade | None = None,
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> CaseListResponse:
    query = (
        select(RepairCaseModel, PropertyModel.address_line, RepairIssueModel.description, PropertyModel.photo_key)
        .join(PropertyModel, RepairCaseModel.property_id == PropertyModel.id)
        .outerjoin(RepairIssueModel, RepairIssueModel.case_id == RepairCaseModel.id)
        # Only needed for the `q` search below (tenant display name), but
        # tenant_id is a NOT NULL FK so this can't drop any case row.
        .join(TenantModel, TenantModel.id == RepairCaseModel.tenant_id)
        .order_by(RepairCaseModel.updated_at.desc())
        .limit(limit + 1)
    )
    if not include_archived:
        # Synthetic archival history is excluded from the operational list
        # by default: it exists to populate charts, not to be worked on.
        query = query.where(RepairCaseModel.archive_batch_id.is_(None))
    if category is not None:
        query = query.where(RepairCaseModel.category == category)
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
        except ValueError:
            raise DomainError(f"cursor {cursor!r} is not a valid ISO-8601 timestamp")
        query = query.where(RepairCaseModel.updated_at < cursor_dt)
    if status is not None:
        query = query.where(RepairCaseModel.status == status)
    if property_id is not None:
        query = query.where(RepairCaseModel.property_id == property_id)
    if q:
        like = f"%{q}%"
        query = query.where(
            or_(
                RepairCaseModel.title.like(like),
                RepairIssueModel.description.like(like),
                PropertyModel.address_line.like(like),
                TenantModel.display_name.like(like),
            )
        )
    if contractor_id is not None:
        # "Active work order" = not finished (COMPLETED/CANCELLED); a case
        # whose only work order for this contractor is long since done
        # shouldn't show up under a live "filter by contractor" control.
        active_work_order_for_contractor = (
            select(WorkOrderModel.id)
            .where(
                WorkOrderModel.case_id == RepairCaseModel.id,
                WorkOrderModel.contractor_id == contractor_id,
                WorkOrderModel.status.notin_(["COMPLETED", "CANCELLED"]),
            )
            .exists()
        )
        query = query.where(active_work_order_for_contractor)

    rows = (await session.execute(query)).all()
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1][0].updated_at.isoformat()
        rows = rows[:limit]

    contractors_by_case = await services.assigned_contractors_for_cases(session, [r[0].id for r in rows])

    items = [
        CaseListItem(
            id=case.id, case_number=case.case_number, title=case.title, status=case.status, version=case.version,
            updated_at=case.updated_at, property_address=address_line,
            urgency=(case.risk or {}).get("urgency", "UNKNOWN"),
            assigned_contractor_name=(
                contractors_by_case[case.id].display_name if case.id in contractors_by_case else None
            ),
            property_photo_key=photo_key,
            category=case.category,
            is_archived=case.archive_batch_id is not None,
        )
        for case, address_line, _description, photo_key in rows
    ]
    return CaseListResponse(items=items, next_cursor=next_cursor)


@router.get("/cases/{case_id}", response_model=CaseDetailResponse)
async def get_case(case_id: str, known_version: int | None = Query(default=None), session: AsyncSession = Depends(get_session)) -> Response:
    case = await session.get(RepairCaseModel, case_id)
    if case is None:
        raise NotFoundError(f"case {case_id} not found")
    if known_version is not None and known_version == case.version:
        from starlette.responses import Response as StarletteResponse

        return StarletteResponse(status_code=304)

    snapshot = await services.load_case_snapshot(session, case_id)
    latest_seq = (
        await session.execute(
            select(CaseEventModel.seq).where(CaseEventModel.case_id == case_id).order_by(CaseEventModel.seq.desc()).limit(1)
        )
    ).scalar_one_or_none() or 0
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

    body = CaseDetailResponse(snapshot=snapshot, latest_event_seq=latest_seq)
    return JSONResponse(content=jsonable_encoder(body))


@router.get("/cases/{case_id}/events")
async def get_case_events(case_id: str, after_seq: int = 0, limit: int = Query(default=50, ge=1, le=100), session: AsyncSession = Depends(get_session)) -> CaseEventsResponse:
    from app.models import CaseEventModel
    from app.schemas import CaseEvent

    rows = (
        await session.execute(
            select(CaseEventModel).where(CaseEventModel.case_id == case_id, CaseEventModel.seq > after_seq).order_by(CaseEventModel.seq).limit(limit)
        )
    ).scalars().all()
    return CaseEventsResponse(items=[CaseEvent.model_validate(r) for r in rows], next_cursor=str(rows[-1].seq) if rows else None)


@router.get("/cases/{case_id}/runs")
async def get_case_runs(case_id: str, cursor: str | None = None, limit: int = Query(default=20, ge=1, le=100), session: AsyncSession = Depends(get_session)) -> CaseRunsResponse:
    rows = (
        await session.execute(
            select(OrchestrationRunModel).where(OrchestrationRunModel.case_id == case_id).order_by(OrchestrationRunModel.started_at.desc()).limit(limit)
        )
    ).scalars().all()
    return CaseRunsResponse(items=[OrchestrationRun.model_validate(r) for r in rows], next_cursor=None)


@router.post("/intakes")
async def submit_intake_endpoint(submission: IntakeSubmission, response: Response, session: AsyncSession = Depends(get_session)) -> IntakeResponse:
    case_id, result = await services.submit_intake(
        session, communication_id=str(submission.communication_id), submission=submission,
        actor=ActorContext("OPERATOR", "operator", str(submission.communication_id)),
    )
    response.status_code = 200 if result.status == CommandResultStatus.NOOP else 201
    return IntakeResponse(case_id=case_id, communication_id=submission.communication_id, result=result)


# Fixed namespace so an Idempotency-Key maps to the same communication id
# on every call, in every process, for the lifetime of the database.
_INTAKE_IDEMPOTENCY_NAMESPACE = uuid.UUID("6f3d1a52-6e1c-4a1e-9f3f-7a5f2b0c9d11")


class OperatorIntakeRequest(BaseModel):
    """An operator typing a reported repair into the New Ticket form.

    This is a real intake channel, not a demo shortcut: a housing officer
    taking a report over the counter or by phone is exactly how most cases
    start. It differs from the voice path only in where the words came
    from, so it goes through the same `services.submit_intake` -- same
    safety triage, same policy, same events -- rather than writing a case
    row directly.
    """

    property_id: uuid.UUID
    tenant_id: uuid.UUID
    description: str = Field(min_length=8, max_length=2000)
    location: str = Field(min_length=1, max_length=128)
    # Verbatim record of what the reporter actually said, kept separate
    # from the operator's own summary above so the two are never confused.
    source_text: str = Field(min_length=1, max_length=4000)
    category: Trade | None = None
    started_at: datetime | None = None
    safety_answers: SafetyAnswers = Field(default_factory=SafetyAnswers)


@router.post("/cases", status_code=201)
async def create_case_from_operator_intake(
    request: OperatorIntakeRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    operator: str = Depends(require_operator),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IntakeResponse:
    """Create a case from an operator-recorded report.

    A Communication row is still created because intake is defined in
    terms of one (docs/16): it records *which conversation* produced the
    case. Here that conversation happened in person or on a handset the
    operator was holding, so the row is marked as an operator-recorded
    intake with LIVE provenance -- this genuinely happened, it simply was
    not carried by a provider. Nothing about it is simulated.

    **Idempotency.** `services.submit_intake` has always been idempotent
    per *communication*: hand it one whose `case_id` is already bound and
    it returns that case as a NOOP. The gap was here -- this endpoint
    minted a fresh communication on every call, so a double-submitted
    form (impatient click, retried request, flaky connection) produced
    two real cases for one report. An optional `Idempotency-Key` header
    now derives the communication id deterministically, which routes a
    repeat into that existing NOOP path instead of adding a table or a
    second dedupe mechanism. The key is namespaced by operator so two
    people cannot collide on a generic value like "1".

    Without the header the behaviour is unchanged, because a caller that
    has not opted in cannot have its retries distinguished from two
    genuinely separate reports of the same fault -- which do happen, and
    must not be silently merged.
    """
    property_row = await session.get(PropertyModel, str(request.property_id))
    if property_row is None:
        raise NotFoundError(f"property {request.property_id} not found")
    if property_row.archive_batch_id is not None:
        raise ConflictError(
            "this property is an archival sample record; new cases cannot be raised against it"
        )
    tenant_row = await session.get(TenantModel, str(request.tenant_id))
    if tenant_row is None:
        raise NotFoundError(f"tenant {request.tenant_id} not found")
    if tenant_row.property_id != property_row.id:
        raise ConflictError("that tenant does not live at the selected property")

    if idempotency_key is not None:
        comm_id = str(uuid.uuid5(_INTAKE_IDEMPOTENCY_NAMESPACE, f"{operator}:{idempotency_key.strip()}"))
        existing = await session.get(CommunicationModel, comm_id)
        if existing is not None and existing.case_id is not None:
            case_row = await services.load_case(session, existing.case_id)
            response.status_code = 200
            return IntakeResponse(
                case_id=uuid.UUID(existing.case_id),
                communication_id=uuid.UUID(comm_id),
                result=CommandResult(status=CommandResultStatus.NOOP, case_version=case_row.version),
            )
    else:
        comm_id = str(uuid.uuid4())
    session.add(
        CommunicationModel(
            id=comm_id,
            purpose="INTAKE",
            direction="BROWSER",
            provider="OPERATOR",
            correlation_token_hash=str(uuid.uuid4()),
            state="ENDED",
            provenance=Provenance.LIVE,
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
        )
    )
    await session.flush()

    case_id, result = await services.submit_intake(
        session,
        communication_id=comm_id,
        submission=IntakeSubmission(
            communication_id=uuid.UUID(comm_id),
            property_id=request.property_id,
            tenant_id=request.tenant_id,
            description=request.description,
            location=request.location,
            started_at=request.started_at,
            source_text=request.source_text,
            safety_answers=request.safety_answers,
        ),
        actor=ActorContext("OPERATOR", operator, comm_id),
    )

    if request.category is not None:
        case_row = await session.get(RepairCaseModel, case_id)
        if case_row is not None and case_row.category is None:
            case_row.category = request.category

    response.status_code = 200 if result.status == CommandResultStatus.NOOP else 201
    return IntakeResponse(case_id=case_id, communication_id=comm_id, result=result)


class CaseEditRequest(BaseModel):
    """Editable descriptive fields on a case.

    Status is absent on purpose: it is not a property of the case that an
    operator sets, it is the outcome of domain actions with preconditions
    (see /cases/{id}/cancel, /resume, /reopen and the approval flow). An
    edit endpoint that could write it would be a back door around every
    one of those rules.

    `expected_version` is required for the same reason every other write
    requires it: two operators editing the same case must not silently
    overwrite each other.
    """

    expected_version: int
    title: str | None = Field(default=None, min_length=4, max_length=255)
    category: Trade | None = None
    location: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, min_length=4, max_length=2000)
    access_notes: str | None = Field(default=None, max_length=2000)


@router.patch("/cases/{case_id}")
async def edit_case(
    case_id: str,
    request: CaseEditRequest,
    session: AsyncSession = Depends(get_session),
    operator: str = Depends(require_operator),
) -> CaseVersionResponse:
    case = await services.load_case(session, case_id)
    if case.archive_batch_id is not None:
        raise ConflictError(
            "this is an archival sample case; archival records are read-only"
        )
    if case.version != request.expected_version:
        from app.domain.errors import StaleVersionError

        raise StaleVersionError("stale case version", current_version=case.version)

    changed: dict[str, object] = {}
    if request.title is not None and request.title != case.title:
        changed["title"] = {"from": case.title, "to": request.title}
        case.title = request.title
    if request.category is not None and request.category != case.category:
        changed["category"] = {
            "from": case.category.value if case.category else None,
            "to": request.category.value,
        }
        case.category = request.category

    issue = (
        await session.execute(select(RepairIssueModel).where(RepairIssueModel.case_id == case_id))
    ).scalars().first()
    if issue is not None:
        if request.location is not None and request.location != issue.location:
            changed["location"] = {"from": issue.location, "to": request.location}
            issue.location = request.location
        if request.description is not None and request.description != issue.description:
            changed["description"] = {"from": issue.description, "to": request.description}
            issue.description = request.description

    if request.access_notes is not None:
        property_row = await session.get(PropertyModel, case.property_id)
        if property_row is not None and property_row.access_notes != request.access_notes:
            changed["access_notes"] = {
                "from": property_row.access_notes,
                "to": request.access_notes,
            }
            property_row.access_notes = request.access_notes

    if not changed:
        # Nothing actually differs. Returning the current version without
        # bumping it keeps a no-op save from invalidating everyone else's
        # in-flight version, and keeps the event log free of empty edits.
        return CaseVersionResponse(case_id=case_id, version=case.version)

    services.bump_version(case)
    await services.append_event(
        session,
        case_id=case_id,
        event_type="CASE_EDITED",
        payload={"changes": changed, "edited_by": operator},
        actor=ActorContext("OPERATOR", operator, str(uuid.uuid4())),
        source_event_key=f"case-edited:{case_id}:{case.version}",
    )
    return CaseVersionResponse(case_id=case_id, version=case.version)


@router.post("/cases/{case_id}/reports", status_code=202)
async def submit_report(case_id: str, submission: ReportSubmission, session: AsyncSession = Depends(get_session)) -> ReportSubmitResponse:
    # `record_contractor_report` derives the case from the work order, not
    # from this URL, so without this check a report posted to case A with
    # case B's work_order_id silently landed on case B and returned 202.
    # `load_work_order` raises NotFoundError unless the work order really
    # belongs to the case in the path.
    await services.load_work_order(session, case_id, str(submission.work_order_id))
    report_id, result = await services.record_contractor_report(
        session, submission=submission,
        source_ref=EvidenceRef(source_type=SourceType.OPERATOR, source_id=str(uuid.uuid4()), observed_at=datetime.now(timezone.utc), provenance=Provenance.SIMULATED),
        provenance=Provenance.SIMULATED, actor=ActorContext("OPERATOR", "operator", str(uuid.uuid4())),
    )
    return ReportSubmitResponse(report_id=report_id, result=result)


@router.post("/cases/{case_id}/resume", status_code=202)
async def resume_case(case_id: str, request: ResumeCaseRequest, session: AsyncSession = Depends(get_session)) -> CaseVersionResponse:
    case = await services.load_case(session, case_id)
    if case.archive_batch_id is not None:
        raise ConflictError(
            "this is an archival sample case; archival records are read-only"
        )
    if case.version != request.version:
        from app.domain.errors import StaleVersionError

        raise StaleVersionError("stale case version", current_version=case.version)
    # assert_case_transition treats a self-transition as a permitted
    # no-op, which is right for an internal retry but wrong for an
    # operator action: "resume" on a case that was never paused is a
    # mistake, and letting it through bumps the version and appends a
    # CASE_RESUMED event describing something that did not happen.
    if case.status != CaseStatus.ESCALATED:
        raise PolicyRejectedError(
            f"only an ESCALATED case can be resumed; this case is {case.status.value}"
        )
    target = case.resume_status or CaseStatus.ACTIVE
    assert_case_transition(case.status, target)
    case.status = target
    case.escalation_reason = None
    services.bump_version(case)
    event = await services.append_event(
        session, case_id=case_id, event_type="CASE_RESUMED", payload={"reason": request.reason, "evidence": request.resolved_hold_evidence},
        actor=ActorContext("OPERATOR", "operator", str(uuid.uuid4())), source_event_key=f"resume:{case_id}:{case.version}",
    )
    await services.enqueue_job(session, case_id=case_id, kind="COORDINATE", dedupe_key=f"coordinate:{case_id}:{case.version}", payload={"trigger_event_id": event.id})
    return CaseVersionResponse(case_id=case_id, version=case.version)


@router.post("/cases/{case_id}/reopen", status_code=202)
async def reopen_case(case_id: str, request: ReopenCaseRequest, session: AsyncSession = Depends(get_session)) -> CaseVersionResponse:
    case = await services.load_case(session, case_id)
    if case.archive_batch_id is not None:
        raise ConflictError(
            "this is an archival sample case; archival records are read-only"
        )
    if case.version != request.version:
        from app.domain.errors import StaleVersionError

        raise StaleVersionError("stale case version", current_version=case.version)
    if case.status != CaseStatus.RESOLVED:
        raise PolicyRejectedError("only a RESOLVED case can be reopened")
    assert_case_transition(case.status, CaseStatus.ESCALATED)
    case.status = CaseStatus.ESCALATED
    case.resume_status = CaseStatus.ACTIVE
    case.escalation_reason = request.reason
    services.bump_version(case)
    await services.append_event(
        session, case_id=case_id, event_type="CASE_ESCALATED", payload={"reason": request.reason, "kind": "late_reopen"},
        actor=ActorContext("OPERATOR", "operator", str(uuid.uuid4())), source_event_key=f"reopen:{case_id}:{case.version}",
    )
    return CaseVersionResponse(case_id=case_id, version=case.version)


@router.post("/cases/{case_id}/cancel", status_code=202)
async def cancel_case(case_id: str, request: CancelCaseRequest, session: AsyncSession = Depends(get_session)) -> CaseVersionResponse:
    case = await services.load_case(session, case_id)
    if case.archive_batch_id is not None:
        raise ConflictError(
            "this is an archival sample case; archival records are read-only"
        )
    if case.version != request.version:
        from app.domain.errors import StaleVersionError

        raise StaleVersionError("stale case version", current_version=case.version)
    # Same reasoning as resume_case above: a self-transition is a legal
    # internal no-op but not a legal operator action. Re-cancelling an
    # already-cancelled case would record a second CASE_CANCELLED event
    # with a different reason, so the history would show it closed twice
    # for two different reasons.
    if case.status == CaseStatus.CANCELLED:
        raise PolicyRejectedError("this case is already cancelled")
    assert_case_transition(case.status, CaseStatus.CANCELLED)
    case.status = CaseStatus.CANCELLED
    services.bump_version(case)
    await services.append_event(
        session, case_id=case_id, event_type="CASE_CANCELLED", payload={"reason": request.reason},
        actor=ActorContext("OPERATOR", "operator", str(uuid.uuid4())), source_event_key=f"cancel:{case_id}:{case.version}",
    )
    return CaseVersionResponse(case_id=case_id, version=case.version)


@router.post("/appointments/{appointment_id}/cancel", status_code=202)
async def cancel_appointment(appointment_id: str, request: CancellationRequest, session: AsyncSession = Depends(get_session)) -> AppointmentCancelResponse:
    """Cancels an appointment and, if it was SCHEDULED, puts the work order
    back to READY and wakes the coordinator (see services.cancel_appointment
    docstring). This is the whole "reschedule" flow: cancel here, then a
    fresh ScheduleVisit proposal comes back through the normal
    coordinator/policy/approval path -- no separate reschedule endpoint."""
    outcome, case_version = await services.cancel_appointment(
        session, appointment_id=appointment_id, reason=request.reason,
        actor=ActorContext("OPERATOR", "operator", str(uuid.uuid4())),
    )
    return AppointmentCancelResponse(appointment_id=appointment_id, outcome=outcome, case_version=case_version)


class RescheduleRequest(BaseModel):
    """An operator moving a visit to a time they arranged themselves."""

    start_at: datetime
    end_at: datetime
    reason: str = Field(min_length=3, max_length=500)
    # Who actually agreed the new slot, in the operator's words. Required:
    # an appointment with no named source is indistinguishable from one the
    # system invented, and this system never invents availability.
    arranged_with: str = Field(min_length=2, max_length=128)


@router.post("/appointments/{appointment_id}/reschedule", status_code=202)
async def reschedule_appointment(
    appointment_id: str,
    request: RescheduleRequest,
    session: AsyncSession = Depends(get_session),
    operator: str = Depends(require_operator),
) -> dict:
    """Move a visit to a time the operator arranged out-of-band.

    Two separate facts, kept separate (docs/19; "provider acceptance is not
    booking confirmation" cuts both ways):

    * the old appointment is genuinely cancelled through the connector, so
      its slot is released rather than orphaned;
    * the replacement is recorded as **PENDING**, never CONFIRMED, with
      `provider_booking_id = None` and `connector = HUMAN`. An operator
      writing a time into this system is not a contractor accepting it.
      Confirmation is a separate, later fact.

    The event records who arranged it and with whom, so the case history
    can always answer "who says this visit is happening?".
    """
    from app.models import AppointmentModel
    from app.schemas import AppointmentStatus, ConnectorType

    now = datetime.now(timezone.utc)
    if request.end_at <= request.start_at:
        raise DomainError("the new visit must end after it starts")
    if request.start_at <= now:
        raise DomainError("the new visit must be in the future")

    appointment = await session.get(AppointmentModel, appointment_id)
    if appointment is None:
        raise NotFoundError(f"appointment {appointment_id} not found")
    if appointment.status in (AppointmentStatus.FINISHED, AppointmentStatus.CANCELLED):
        raise ConflictError(
            f"appointment {appointment_id} is {appointment.status.value.lower()} and cannot be moved"
        )

    case_id = appointment.case_id
    work_order_id = appointment.work_order_id
    contractor_id = appointment.contractor_id
    action_id = appointment.action_id
    attempt = appointment.attempt_number

    outcome, _version = await services.cancel_appointment(
        session,
        appointment_id=appointment_id,
        reason=f"Rescheduled by {operator}: {request.reason}",
        actor=ActorContext("OPERATOR", operator, str(uuid.uuid4())),
    )

    replacement_id = str(uuid.uuid4())
    session.add(
        AppointmentModel(
            id=replacement_id,
            case_id=case_id,
            work_order_id=work_order_id,
            contractor_id=contractor_id,
            slot_id=f"manual:{replacement_id}",
            start_at=request.start_at,
            end_at=request.end_at,
            status=AppointmentStatus.PENDING,
            connector=ConnectorType.HUMAN,
            provider_booking_id=None,
            action_id=action_id,
            attempt_number=attempt + 1,
            provenance=Provenance.LIVE,
        )
    )
    await session.flush()

    case = await services.load_case(session, case_id)
    services.bump_version(case)
    await services.append_event(
        session,
        case_id=case_id,
        event_type="APPOINTMENT_RESCHEDULED",
        payload={
            "previous_appointment_id": appointment_id,
            "appointment_id": replacement_id,
            "work_order_id": work_order_id,
            "start_at": request.start_at.isoformat(),
            "end_at": request.end_at.isoformat(),
            "reason": request.reason,
            "arranged_with": request.arranged_with,
            "recorded_by": operator,
            "recorded_at": now.isoformat(),
            "contractor_confirmed": False,
        },
        actor=ActorContext("OPERATOR", operator, str(uuid.uuid4())),
        source_event_key=f"appointment-rescheduled:{replacement_id}",
    )

    return {
        "previous_appointment_id": appointment_id,
        "appointment_id": replacement_id,
        "status": AppointmentStatus.PENDING.value,
        "cancellation": outcome.model_dump(mode="json"),
        "case_version": case.version,
        "note": (
            "Recorded as pending. The contractor has not confirmed this time through "
            "any provider; confirmation is a separate fact."
        ),
    }


@router.get("/appointments/upcoming")
async def get_upcoming_appointments(
    limit: int = Query(default=100, ge=1, le=200), session: AsyncSession = Depends(get_session),
) -> UpcomingAppointmentsResponse:
    """Cross-case "next visits" list -- date, contractor, property address
    and time window for every CONFIRMED appointment starting in the
    future, soonest first."""
    items = await services.load_upcoming_appointments(session, limit=limit)
    return UpcomingAppointmentsResponse(items=items)


@router.get("/properties/{property_id}/history")
async def get_property_history(
    property_id: str,
    include_archived: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> PropertyHistoryResponse:
    """Defaults to including archival sample cases, which is what this
    screen has always shown. The response says which it did."""
    prop = await session.get(PropertyModel, property_id)
    if prop is None:
        raise NotFoundError(f"property {property_id} not found")
    # analytics.property_history_items is the single reader of this
    # money. A second implementation in domain.services once summed
    # WorkOrderModel.quote_pence directly and disagreed with
    # Insights/Reports/CSV; it went unused after the reconciliation fix
    # and was deleted on 2026-09-21. See analytics.py's "QUOTED MONEY
    # RECONCILIATION RULE" and docs/26 2026-09-20.
    items = await analytics.property_history_items(session, property_id, include_archived=include_archived)
    return PropertyHistoryResponse(
        property_id=property_id, items=items,
        includes_archived_history=include_archived,
        archived_case_count=sum(1 for i in items if i.is_archived),
    )


@router.get("/properties/{property_id}/stats")
async def get_property_stats(
    property_id: str,
    include_archived: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> PropertyStatsResponse:
    prop = await session.get(PropertyModel, property_id)
    if prop is None:
        raise NotFoundError(f"property {property_id} not found")
    # analytics.property_stats -- see the comment on get_property_history
    # above for why this has one implementation and not two.
    return await analytics.property_stats(session, property_id, prop.build_year, include_archived=include_archived)


@router.get("/cases/{case_id}/messages")
async def get_case_messages(case_id: str, session: AsyncSession = Depends(get_session)) -> CaseMessagesResponse:
    """Read-only tenant/contractor/operator message thread for a case
    (CLAUDE.md: chat history is not authoritative state -- display only,
    never fed to the coordinator). No write endpoint exists yet, so this
    is honestly empty until one does."""
    case = await session.get(RepairCaseModel, case_id)
    if case is None:
        raise NotFoundError(f"case {case_id} not found")
    items = await services.load_case_messages(session, case_id)
    return CaseMessagesResponse(case_id=case_id, items=items)


@router.get("/communications/{communication_id}")
async def get_communication(communication_id: str, session: AsyncSession = Depends(get_session)) -> Communication:
    comm = await session.get(CommunicationModel, communication_id)
    if comm is None:
        raise NotFoundError(f"communication {communication_id} not found")
    return Communication.model_validate(comm)


@router.get("/communications/{communication_id}/recording")
async def get_recording(communication_id: str, session: AsyncSession = Depends(get_session)):
    from fastapi.responses import FileResponse

    from app.config import get_settings

    comm = await session.get(CommunicationModel, communication_id)
    if comm is None:
        raise NotFoundError(f"communication {communication_id} not found")
    recording = comm.recording or {}
    if recording.get("status") != "AVAILABLE" or not recording.get("media_path"):
        raise HTTPException(status_code=409, detail="recording not available")
    settings = get_settings()
    path = settings.recordings_dir / recording["media_path"]
    if not path.exists():
        raise HTTPException(status_code=409, detail="recording file missing on disk")
    return FileResponse(path, media_type=recording.get("media_type") or "audio/mpeg")


@router.post("/communications/{communication_id}/retry-recording", status_code=202)
async def retry_recording(communication_id: str, session: AsyncSession = Depends(get_session)) -> RetryRecordingResponse:
    comm = await session.get(CommunicationModel, communication_id)
    if comm is None:
        raise NotFoundError(f"communication {communication_id} not found")
    # A fresh uuid4() here can never collide with itself, so this never
    # deduped anything -- a double-click always queued two jobs. A fully
    # fixed key would fix that but then permanently block any LATER retry
    # too (enqueue_job's dedupe has no TTL). Bucket like the reconciliation
    # sweep does: collapses rapid double-clicks, still allows a genuine
    # retry a few seconds later.
    retry_bucket = int(datetime.now(timezone.utc).timestamp() // 10)
    job = await services.enqueue_job(
        session, case_id=comm.case_id, kind="FETCH_RECORDING",
        dedupe_key=f"recording:{communication_id}:retry:{retry_bucket}", payload={"communication_id": communication_id},
    )
    return RetryRecordingResponse(queued=job is not None)


@router.get("/research/{research_id}")
async def get_research(research_id: str, session: AsyncSession = Depends(get_session)) -> ResearchSnapshot:
    snapshot = await session.get(ResearchSnapshotModel, research_id)
    if snapshot is None:
        raise NotFoundError(f"research {research_id} not found")
    return ResearchSnapshot.model_validate(snapshot)
