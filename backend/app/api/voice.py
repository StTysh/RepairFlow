"""Voice endpoints (docs/16): operator/UI-facing session lifecycle under
/api/v1/voice (Basic auth like the rest of the operator API -- this is a
synthetic single-operator demo, so the "tenant browser" is the operator's
own browser per docs/16's auth section), plus the two ElevenLabs-owned
surfaces that deliberately bypass operator auth and use their own
verification instead: the signed post-call webhook and the dedicated-secret
server tools the voice agent calls mid-conversation (docs/11, docs/16).

The voice agent is a constrained conversational adapter, never the central
coordinator (CLAUDE.md). Facts/availability it surfaces flow through the
same typed ingestion (services.submit_intake/record_observations) any other
caller uses, tagged with ActorContext("VOICE_TOOL", ...).
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.config import get_settings
from app.db import session_scope
from app.domain import services
from app.domain.errors import ConflictError, ExternalResultUnknownError, ForbiddenError, NotFoundError, PolicyRejectedError, ProviderUnavailableError
from app.domain.services import ActorContext
from app.integrations import elevenlabs as elevenlabs_integration
from app.models import CommunicationModel, PropertyModel, RepairCaseModel, TenantModel, new_uuid
from app.orchestration.dedupe import record_webhook_receipt
from app.schemas import (
    ConversationContextResponse,
    Recording,
    RecordingStatus,
    ToolAckResponse,
    ToolContextRequest,
    ToolIntakeRequest,
    ToolObservationsRequest,
    VoiceSessionBindRequest,
    VoiceSessionBindResponse,
    VoiceSessionEndedRequest,
    VoiceSessionEndedResponse,
    VoiceSessionRequest,
    VoiceSessionResponse,
    WebhookAckResponse,
)

router = APIRouter(prefix="/api/v1/voice", dependencies=[Depends(require_operator)])
webhook_router = APIRouter(prefix="/webhooks/elevenlabs")
tools_router = APIRouter(prefix="/integrations/elevenlabs/tools")


# --------------------------------------------------------------------------
# /api/v1/voice/* -- operator-authed session lifecycle
# --------------------------------------------------------------------------


@router.post("/sessions")
async def create_voice_session(request: VoiceSessionRequest) -> VoiceSessionResponse:
    settings = get_settings()
    if not request.disclosure_accepted:
        raise PolicyRejectedError("AI/recording disclosure must be accepted before starting a voice session")
    if request.purpose.value != "INTAKE" and request.case_id is None:
        raise PolicyRejectedError(f"purpose {request.purpose.value} requires an existing case_id")
    if not settings.elevenlabs_live:
        raise ProviderUnavailableError(
            "ElevenLabs is not configured in this environment (missing ELEVENLABS_API_KEY/ELEVENLABS_AGENT_ID) -- live voice sessions are unavailable"
        )

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    comm_id = new_uuid()
    direction = "OUTBOUND" if request.channel == "PSTN" else "BROWSER"

    # Phase A: durable correlation record, committed before the network call.
    async with session_scope() as session:
        session.add(
            CommunicationModel(
                id=comm_id, case_id=str(request.case_id) if request.case_id else None,
                tenant_id=str(request.tenant_id) if request.tenant_id else None, purpose=request.purpose.value, direction=direction,
                provider="ELEVENLABS", correlation_token_hash=token_hash, state="REQUESTED", provenance="LIVE",
            )
        )

    dynamic_variables = {
        "correlation_token": raw_token, "communication_id": comm_id,
        "repair_case_id": str(request.case_id) if request.case_id else "",
        "call_purpose": request.purpose.value,
    }

    if request.channel == "PSTN":
        # A telephony call is placed by ElevenLabs' own Twilio integration,
        # not by a browser SDK connecting to a signed WebSocket URL -- that
        # call would be meaningless here, so it is skipped for this channel.
        return VoiceSessionResponse(
            communication_id=comm_id, session_credential=None, connection_type="pstn",
            dynamic_variables=dynamic_variables, expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )

    # Phase B: network call, no open transaction (CLAUDE.md non-negotiable).
    try:
        signed_url = await elevenlabs_integration.create_signed_session(
            agent_id=settings.elevenlabs_agent_id, api_key=settings.elevenlabs_api_key,
        )
    except httpx.HTTPError as exc:
        raise ExternalResultUnknownError(f"failed to obtain a signed ElevenLabs session: {exc}") from exc

    return VoiceSessionResponse(
        communication_id=comm_id, session_credential=signed_url, connection_type="websocket",
        dynamic_variables=dynamic_variables,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )


@router.post("/sessions/{communication_id}/bind")
async def bind_voice_session(communication_id: str, request: VoiceSessionBindRequest, session: AsyncSession = Depends(get_session)) -> VoiceSessionBindResponse:
    comm = await session.get(CommunicationModel, communication_id)
    if comm is None:
        raise NotFoundError(f"communication {communication_id} not found")

    already_bound_elsewhere = (
        await session.execute(
            select(CommunicationModel).where(CommunicationModel.provider_conversation_id == request.provider_conversation_id)
        )
    ).scalars().first()
    if already_bound_elsewhere is not None and already_bound_elsewhere.id != communication_id:
        raise ConflictError(f"provider_conversation_id {request.provider_conversation_id} is already bound to a different communication")

    if comm.provider_conversation_id and comm.provider_conversation_id != request.provider_conversation_id:
        raise ConflictError("this communication is already bound to a different provider conversation")

    comm.provider_conversation_id = request.provider_conversation_id
    if comm.started_at is None:
        comm.started_at = datetime.now(timezone.utc)
    comm.state = "ACTIVE"
    return VoiceSessionBindResponse(communication_id=communication_id, case_id=comm.case_id, bound=True)


@router.post("/sessions/{communication_id}/ended")
async def voice_session_ended(communication_id: str, request: VoiceSessionEndedRequest, session: AsyncSession = Depends(get_session)) -> VoiceSessionEndedResponse:
    """Browser disconnect notice. Advisory only (docs/11: "Browser disconnect
    is not proof provider processing finished") -- schedules reconciliation,
    does not itself mark anything AVAILABLE/ENDED with certainty beyond
    what's locally known."""
    comm = await session.get(CommunicationModel, communication_id)
    if comm is None:
        raise NotFoundError(f"communication {communication_id} not found")
    if comm.provider_conversation_id and comm.provider_conversation_id != request.provider_conversation_id:
        raise ConflictError("provider_conversation_id does not match this communication's bound conversation")
    if comm.state not in ("ENDED", "FAILED"):
        comm.state = "ENDED"
    if comm.ended_at is None:
        comm.ended_at = datetime.now(timezone.utc)

    job = await services.enqueue_job(
        session, case_id=comm.case_id, kind="FETCH_RECORDING",
        dedupe_key=f"recording:{communication_id}:session-ended", payload={"communication_id": communication_id},
    )
    return VoiceSessionEndedResponse(queued=job is not None)


# --------------------------------------------------------------------------
# /webhooks/elevenlabs/post-call -- signed, provider-owned, no operator auth
# --------------------------------------------------------------------------


@webhook_router.post("/post-call", status_code=200)
async def elevenlabs_post_call_webhook(request: Request) -> WebhookAckResponse:
    settings = get_settings()
    raw_body = await request.body()
    signature = request.headers.get(elevenlabs_integration.WEBHOOK_SIGNATURE_HEADER)

    if not settings.elevenlabs_webhook_secret:
        raise HTTPException(status_code=401, detail="webhook signing secret not configured")
    try:
        elevenlabs_integration.verify_webhook_signature(raw_body, signature, settings.elevenlabs_webhook_secret)
    except elevenlabs_integration.WebhookSignatureError as exc:
        raise HTTPException(status_code=401, detail=f"invalid webhook signature: {exc.reason}")

    try:
        envelope = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    event_type = str(envelope.get("type") or "")
    event_timestamp = str(envelope.get("event_timestamp") or "")
    data = envelope.get("data") or {}
    conversation_id = data.get("conversation_id")

    async with session_scope() as session:
        receipt, is_new = await record_webhook_receipt(
            session, provider="ELEVENLABS", event_type=event_type, conversation_id=conversation_id,
            event_timestamp=event_timestamp, raw_body=raw_body, envelope=envelope,
        )
        if not is_new:
            return WebhookAckResponse(receipt_id=receipt.id, status="DUPLICATE")

        comm = None
        if conversation_id:
            comm = (
                await session.execute(select(CommunicationModel).where(CommunicationModel.provider_conversation_id == conversation_id))
            ).scalars().first()

        if comm is None:
            # Unknown/unmapped conversation: durably record and expose for
            # operator review rather than guessing a case (docs/16, docs/11:
            # "preserve the unbound communication and require operator
            # binding; do not discard the call or attach it to a guessed
            # property").
            receipt.processing_status = "QUARANTINED"
            return WebhookAckResponse(receipt_id=receipt.id, status="QUARANTINED")

        if event_type not in ("post_call_transcription", "post_call_audio", "call_initiation_failure"):
            receipt.processing_status = "IGNORED"
            return WebhookAckResponse(receipt_id=receipt.id, status="IGNORED")

        if event_type == "post_call_transcription":
            turns = elevenlabs_integration.map_transcript(data.get("transcript") or [])
            comm.transcript = [t.model_dump(mode="json") for t in turns]
            comm.outcome = elevenlabs_integration.map_outcome(comm.id, str(conversation_id), data).model_dump(mode="json")
            if comm.ended_at is None:
                comm.ended_at = datetime.now(timezone.utc)
            comm.state = "ENDED"
            case_id = comm.case_id
            await services.enqueue_job(
                session, case_id=case_id, kind="FETCH_RECORDING",
                dedupe_key=f"recording:{comm.id}:webhook", payload={"communication_id": comm.id},
            )
            if case_id:
                # COORDINATE jobs require a real trigger_event_id (worker.py
                # reads payload["trigger_event_id"] unconditionally) -- record
                # receipt as its own CaseEvent rather than enqueueing without
                # one, which would raise KeyError and fail the job silently.
                transcript_event = await services.append_event(
                    session, case_id=case_id, event_type="CALL_ENDED",
                    payload={"communication_id": comm.id, "turn_count": len(turns)},
                    actor=ActorContext("SYSTEM", "post-call-webhook", comm.id),
                    source_event_key=f"post-call-webhook:{comm.id}",
                )
                await services.enqueue_job(
                    session, case_id=case_id, kind="COORDINATE",
                    dedupe_key=f"coordinate:voice-transcript:{comm.id}",
                    payload={"trigger_event_id": transcript_event.id, "reason": "post_call_transcription webhook"},
                )
        elif event_type == "post_call_audio":
            audio_b64 = data.get("full_audio")
            if audio_b64:
                audio_bytes = base64.b64decode(audio_b64)
                settings.recordings_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{comm.id}.mp3"
                (settings.recordings_dir / filename).write_bytes(audio_bytes)
                comm.recording = Recording(
                    status=RecordingStatus.AVAILABLE, media_path=filename, media_type="audio/mpeg",
                    byte_count=len(audio_bytes), sha256=hashlib.sha256(audio_bytes).hexdigest(),
                    acquired_at=datetime.now(timezone.utc),
                ).model_dump(mode="json")
        elif event_type == "call_initiation_failure":
            comm.state = "FAILED"
            comm.recording = Recording(status=RecordingStatus.UNAVAILABLE, error_code="call_initiation_failure").model_dump(mode="json")

        receipt.processing_status = "PROCESSED"
        return WebhookAckResponse(receipt_id=receipt.id, status="PROCESSED")


# --------------------------------------------------------------------------
# /integrations/elevenlabs/tools/* -- dedicated bearer secret + scoped
# correlation token, no operator auth (docs/16)
# --------------------------------------------------------------------------


def _require_tool_secret(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.elevenlabs_tool_secret:
        raise HTTPException(status_code=503, detail="ElevenLabs tool secret not configured")
    expected = f"Bearer {settings.elevenlabs_tool_secret}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="invalid tool secret")


async def _resolve_scoped_communication(session: AsyncSession, communication_id: str, correlation_token: str) -> CommunicationModel:
    comm = await session.get(CommunicationModel, communication_id)
    if comm is None:
        raise NotFoundError(f"communication {communication_id} not found")
    token_hash = hashlib.sha256(correlation_token.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(token_hash, comm.correlation_token_hash):
        raise ForbiddenError("correlation token does not match this communication")
    return comm


@tools_router.post("/intake", dependencies=[Depends(_require_tool_secret)])
async def tool_submit_intake(request: ToolIntakeRequest, session: AsyncSession = Depends(get_session)) -> ToolAckResponse:
    comm = await _resolve_scoped_communication(session, str(request.submission.communication_id), request.correlation_token)
    case_id, _result = await services.submit_intake(
        session, communication_id=comm.id, submission=request.submission,
        actor=ActorContext("VOICE_TOOL", comm.id, comm.id),
    )
    return ToolAckResponse(
        accepted=True, communication_id=comm.id, case_id=case_id,
        message="Your report is saved; coordination is pending.",
    )


@tools_router.post("/observations", dependencies=[Depends(_require_tool_secret)])
async def tool_record_observations(request: ToolObservationsRequest, session: AsyncSession = Depends(get_session)) -> ToolAckResponse:
    comm = await _resolve_scoped_communication(session, str(request.submission.communication_id), request.correlation_token)
    if comm.case_id is None:
        raise PolicyRejectedError("this communication is not yet bound to a case; the intake tool must run first")
    await services.record_observations(
        session, case_id=comm.case_id, communication_id=comm.id, submission=request.submission,
        actor=ActorContext("VOICE_TOOL", comm.id, comm.id),
    )
    return ToolAckResponse(
        accepted=True, communication_id=comm.id, case_id=comm.case_id,
        message="Your update is saved; coordination is pending.",
    )


@tools_router.post("/context", dependencies=[Depends(_require_tool_secret)])
async def tool_conversation_context(request: ToolContextRequest, session: AsyncSession = Depends(get_session)) -> ConversationContextResponse:
    comm = await _resolve_scoped_communication(session, str(request.communication_id), request.correlation_token)

    tenant_name: str | None = None
    property_address: str | None = None
    if comm.tenant_id:
        tenant = await session.get(TenantModel, comm.tenant_id)
        if tenant is not None:
            tenant_name = tenant.display_name
            prop = await session.get(PropertyModel, tenant.property_id)
            property_address = prop.address_line if prop is not None else None

    issue_summary: str | None = None
    if comm.case_id:
        case = await session.get(RepairCaseModel, comm.case_id)
        issue_summary = case.title if case is not None else None

    return ConversationContextResponse(
        communication_id=comm.id, case_id=comm.case_id, purpose=comm.purpose,
        tenant_display_name=tenant_name, property_address=property_address, issue_summary=issue_summary,
        current_date=datetime.now(timezone.utc), timezone="Europe/London",
    )
