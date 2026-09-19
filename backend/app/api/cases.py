"""Case reads, intake, reports, communications, research, appointments and
lifecycle transitions (docs/16). Bundled per the project's expected
structure (one router per concern group, not one route per file).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain import services
from app.domain.errors import ConflictError, NotFoundError, PolicyRejectedError
from app.domain.services import ActorContext
from app.domain.transitions import assert_case_transition
from app.models import (
    AppointmentModel,
    CaseEventModel,
    CommunicationModel,
    OrchestrationRunModel,
    RepairCaseModel,
    ResearchSnapshotModel,
)
from app.schemas import (
    AppointmentCancelResponse,
    CancelCaseRequest,
    CancellationRequest,
    CaseDetailResponse,
    CaseEventsResponse,
    CaseListItem,
    CaseListResponse,
    CaseRunsResponse,
    CaseStatus,
    CaseVersionResponse,
    CommandResultStatus,
    Communication,
    IntakeResponse,
    IntakeSubmission,
    OrchestrationRun,
    ReopenCaseRequest,
    ReportSubmission,
    ReportSubmitResponse,
    ResearchSnapshot,
    RetryRecordingResponse,
    ResumeCaseRequest,
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
    limit: int = Query(default=20, le=100), cursor: str | None = None, session: AsyncSession = Depends(get_session),
) -> CaseListResponse:
    query = select(RepairCaseModel).order_by(RepairCaseModel.updated_at.desc()).limit(limit + 1)
    if cursor:
        cursor_dt = datetime.fromisoformat(cursor)
        query = select(RepairCaseModel).where(RepairCaseModel.updated_at < cursor_dt).order_by(RepairCaseModel.updated_at.desc()).limit(limit + 1)
    rows = (await session.execute(query)).scalars().all()
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1].updated_at.isoformat()
        rows = rows[:limit]
    items = [CaseListItem(id=r.id, title=r.title, status=r.status, version=r.version, updated_at=r.updated_at) for r in rows]
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
async def get_case_events(case_id: str, after_seq: int = 0, limit: int = Query(default=50, le=100), session: AsyncSession = Depends(get_session)) -> CaseEventsResponse:
    from app.models import CaseEventModel
    from app.schemas import CaseEvent

    rows = (
        await session.execute(
            select(CaseEventModel).where(CaseEventModel.case_id == case_id, CaseEventModel.seq > after_seq).order_by(CaseEventModel.seq).limit(limit)
        )
    ).scalars().all()
    return CaseEventsResponse(items=[CaseEvent.model_validate(r) for r in rows], next_cursor=str(rows[-1].seq) if rows else None)


@router.get("/cases/{case_id}/runs")
async def get_case_runs(case_id: str, cursor: str | None = None, limit: int = Query(default=20, le=100), session: AsyncSession = Depends(get_session)) -> CaseRunsResponse:
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


@router.post("/cases/{case_id}/reports", status_code=202)
async def submit_report(case_id: str, submission: ReportSubmission, session: AsyncSession = Depends(get_session)) -> ReportSubmitResponse:
    report_id, result = await services.record_contractor_report(
        session, submission=submission,
        source_ref=EvidenceRef(source_type=SourceType.OPERATOR, source_id=str(uuid.uuid4()), observed_at=datetime.now(timezone.utc), provenance=Provenance.SIMULATED),
        provenance=Provenance.SIMULATED, actor=ActorContext("OPERATOR", "operator", str(uuid.uuid4())),
    )
    return ReportSubmitResponse(report_id=report_id, result=result)


@router.post("/cases/{case_id}/resume", status_code=202)
async def resume_case(case_id: str, request: ResumeCaseRequest, session: AsyncSession = Depends(get_session)) -> CaseVersionResponse:
    case = await services.load_case(session, case_id)
    if case.version != request.version:
        from app.domain.errors import StaleVersionError

        raise StaleVersionError("stale case version", current_version=case.version)
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
    if case.version != request.version:
        from app.domain.errors import StaleVersionError

        raise StaleVersionError("stale case version", current_version=case.version)
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
    appointment = await session.get(AppointmentModel, appointment_id)
    if appointment is None:
        raise NotFoundError(f"appointment {appointment_id} not found")
    from app.integrations.booking import mock_booking_connector

    outcome = await mock_booking_connector.cancel(session, appointment.provider_booking_id or "", f"cancel:{appointment_id}")
    if outcome.status.value == "CANCELLED":
        appointment.status = "CANCELLED"
    return AppointmentCancelResponse(appointment_id=appointment_id, outcome=outcome)


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
    job = await services.enqueue_job(
        session, case_id=comm.case_id, kind="FETCH_RECORDING",
        dedupe_key=f"recording:{communication_id}:{uuid.uuid4()}", payload={"communication_id": communication_id},
    )
    return RetryRecordingResponse(queued=job is not None)


@router.get("/research/{research_id}")
async def get_research(research_id: str, session: AsyncSession = Depends(get_session)) -> ResearchSnapshot:
    snapshot = await session.get(ResearchSnapshotModel, research_id)
    if snapshot is None:
        raise NotFoundError(f"research {research_id} not found")
    return ResearchSnapshot.model_validate(snapshot)
