"""ElevenLabs Conversational AI: signed browser session creation, post-call
webhook signature verification, and conversation/audio retrieval (docs/11).

No live ELEVENLABS_API_KEY/ELEVENLABS_AGENT_ID exist in this environment, so
none of the network calls here have been exercised against the real API --
see docs/23 for the honest live-gate status. Field names for the REST
responses (conversation details, transcript turns) are taken from docs/11's
description of the contract, not a captured live payload; parsing is
written defensively (multiple plausible key names, safe fallbacks) rather
than assuming an exact shape, and this is called out inline below.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.db import session_scope
from app.domain.errors import NotFoundError
from app.schemas import CallOutcome, CallOutcomeStatus, Recording, RecordingStatus, Speaker, TranscriptTurn

API_BASE = "https://api.elevenlabs.io"

WEBHOOK_SIGNATURE_HEADER = "ElevenLabs-Signature"
# ElevenLabs documents that webhooks are HMAC-signed and that the SDK
# verifier "validates the timestamp" (docs/11 citing their post-call
# webhooks page), but does not publish the exact header/signing format in
# prose. This implements the documented convention their own docs page
# describes them as following (Stripe/Svix-style `t=<ts>,v0=<hex hmac>`
# over `f"{ts}.{raw_body}"`, HMAC-SHA256). If a live secret is ever
# configured, verify this against one real webhook delivery before relying
# on it -- see docs/23.
WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS = 30 * 60


class WebhookSignatureError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def verify_webhook_signature(raw_body: bytes, signature_header: str | None, secret: str, *, now: datetime | None = None) -> None:
    """Raises WebhookSignatureError on any failure; returns None on success.
    Never processes a webhook body before this passes (CLAUDE.md: "no
    unsigned webhook acceptance")."""
    if not signature_header:
        raise WebhookSignatureError("missing signature header")

    parts: dict[str, str] = {}
    for item in signature_header.split(","):
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        parts[key.strip()] = value.strip()

    timestamp_raw = parts.get("t")
    signature = parts.get("v0")
    if not timestamp_raw or not signature:
        raise WebhookSignatureError("malformed signature header")

    try:
        timestamp = int(timestamp_raw)
    except ValueError:
        raise WebhookSignatureError("non-numeric timestamp")

    current = int((now or datetime.now(timezone.utc)).timestamp())
    if abs(current - timestamp) > WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS:
        raise WebhookSignatureError("timestamp outside tolerance")

    signed_payload = f"{timestamp_raw}.{raw_body.decode('utf-8')}"
    expected = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise WebhookSignatureError("signature mismatch")


async def create_signed_session(*, agent_id: str, api_key: str) -> str:
    """GET /v1/convai/conversation/get-signed-url -- returns the signed
    WebSocket URL the browser SDK connects to directly (docs/11: audio
    travels browser<->ElevenLabs, never through this backend)."""
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
        response = await client.get(
            "/v1/convai/conversation/get-signed-url",
            params={"agent_id": agent_id},
            headers={"xi-api-key": api_key},
        )
        response.raise_for_status()
        body = response.json()
        return body["signed_url"]


async def fetch_conversation_details(conversation_id: str, *, api_key: str) -> dict:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
        response = await client.get(
            f"/v1/convai/conversations/{conversation_id}",
            headers={"xi-api-key": api_key},
        )
        response.raise_for_status()
        return response.json()


async def fetch_conversation_audio(conversation_id: str, *, api_key: str) -> bytes:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
        response = await client.get(
            f"/v1/convai/conversations/{conversation_id}/audio",
            headers={"xi-api-key": api_key},
        )
        response.raise_for_status()
        return response.content


def map_transcript(raw_turns: list[dict]) -> list[TranscriptTurn]:
    """Defensive mapping -- see module docstring on why exact field names
    are not verified against a live payload. Tries the documented/likely
    key names for role, text and timing; skips a turn it cannot make sense
    of rather than fabricating content."""
    turns: list[TranscriptTurn] = []
    for index, raw in enumerate(raw_turns):
        role_raw = str(raw.get("role") or raw.get("speaker") or "").upper()
        if role_raw in ("USER", "TENANT", "CALLER"):
            speaker = Speaker.USER
        elif role_raw in ("AGENT", "ASSISTANT", "AI"):
            speaker = Speaker.AGENT
        elif role_raw == "TOOL":
            speaker = Speaker.TOOL
        else:
            speaker = Speaker.UNKNOWN

        text = raw.get("message") or raw.get("text") or raw.get("content") or ""
        if not text:
            continue
        time_in_call = raw.get("time_in_call_secs") or raw.get("timestamp") or raw.get("time_offset") or 0.0
        turns.append(
            TranscriptTurn(
                turn_id=str(raw.get("turn_id") or raw.get("id") or index),
                speaker=speaker, text=str(text), time_in_call_secs=max(0.0, float(time_in_call)),
                tool_name=raw.get("tool_name"),
            )
        )
    return turns


def map_outcome(communication_id: str, conversation_id: str, details: dict) -> CallOutcome:
    status_raw = str(details.get("status") or details.get("call_status") or "").upper()
    if status_raw in ("DONE", "COMPLETED", "ENDED"):
        outcome_status = CallOutcomeStatus.ANSWERED
    elif status_raw == "FAILED":
        outcome_status = CallOutcomeStatus.FAILED
    elif status_raw in ("NO_ANSWER",):
        outcome_status = CallOutcomeStatus.NO_ANSWER
    elif status_raw == "VOICEMAIL":
        outcome_status = CallOutcomeStatus.VOICEMAIL
    else:
        outcome_status = CallOutcomeStatus.UNKNOWN

    analysis = details.get("analysis") or {}
    return CallOutcome(
        communication_id=communication_id,
        conversation_id=conversation_id,
        outcome=outcome_status,
        tenant_confirms_resolved=analysis.get("tenant_confirms_resolved"),
        missing_questions=list(analysis.get("missing_questions") or []),
        transcript_refs=[],
    )


async def fetch_recording(communication_id: str) -> None:
    """Reconciliation job body for JobKind.FETCH_RECORDING (called from
    orchestration/worker.py). Fills gaps only -- never overwrites an
    already-populated transcript/outcome (docs/11: the webhook is the
    primary path; this is the fallback "webhook never arrived, or audio
    wasn't in it" path). Never holds a DB transaction across the network
    calls (CLAUDE.md non-negotiable)."""
    from app.models import CommunicationModel

    settings = get_settings()

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, communication_id)
        if comm is None:
            raise NotFoundError(f"communication {communication_id} not found")
        conversation_id = comm.provider_conversation_id
        case_id = comm.case_id
        has_transcript = bool(comm.transcript)
        recording_status = (comm.recording or {}).get("status")

    if conversation_id is None:
        # session created but never bound to a provider conversation --
        # nothing to reconcile yet; leave recording PENDING, don't fail loudly.
        return

    if not settings.elevenlabs_live:
        async with session_scope() as session:
            comm = await session.get(CommunicationModel, communication_id)
            if comm is not None:
                comm.recording = Recording(status=RecordingStatus.UNAVAILABLE, error_code="PROVIDER_NOT_CONFIGURED").model_dump(mode="json")
        return

    # Phase B: network calls, no open transaction.
    try:
        details = await fetch_conversation_details(conversation_id, api_key=settings.elevenlabs_api_key)
    except httpx.HTTPError as exc:
        async with session_scope() as session:
            comm = await session.get(CommunicationModel, communication_id)
            if comm is not None:
                comm.recording = Recording(status=RecordingStatus.FAILED, error_code=f"details_fetch_failed: {exc}"[:200]).model_dump(mode="json")
        return

    new_turns = map_transcript(details.get("transcript") or []) if not has_transcript else None
    new_outcome = map_outcome(communication_id, conversation_id, details) if not has_transcript else None

    audio_bytes: bytes | None = None
    audio_error: str | None = None
    if recording_status != RecordingStatus.AVAILABLE.value:
        try:
            audio_bytes = await fetch_conversation_audio(conversation_id, api_key=settings.elevenlabs_api_key)
            if not audio_bytes:
                audio_error = "empty audio response"
                audio_bytes = None
        except httpx.HTTPError as exc:
            audio_error = f"audio_fetch_failed: {exc}"[:200]

    # Phase C: persist.
    async with session_scope() as session:
        comm = await session.get(CommunicationModel, communication_id)
        if comm is None:
            return

        if new_turns is not None:
            comm.transcript = [t.model_dump(mode="json") for t in new_turns]
        if new_outcome is not None:
            comm.outcome = new_outcome.model_dump(mode="json")
        if comm.ended_at is None:
            comm.ended_at = datetime.now(timezone.utc)
        comm.state = "ENDED"

        if audio_bytes:
            settings.recordings_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{communication_id}.mp3"
            path = settings.recordings_dir / filename
            path.write_bytes(audio_bytes)
            comm.recording = Recording(
                status=RecordingStatus.AVAILABLE, media_path=filename, media_type="audio/mpeg",
                byte_count=len(audio_bytes), sha256=hashlib.sha256(audio_bytes).hexdigest(),
                acquired_at=datetime.now(timezone.utc),
            ).model_dump(mode="json")
        elif recording_status != RecordingStatus.AVAILABLE.value:
            comm.recording = Recording(status=RecordingStatus.FAILED, error_code=audio_error or "unknown").model_dump(mode="json")

        should_coordinate = case_id is not None and new_turns

    if should_coordinate:
        from app.domain import services

        async with session_scope() as session:
            await services.enqueue_job(
                session, case_id=case_id, kind="COORDINATE",
                dedupe_key=f"coordinate:reconciled-voice:{communication_id}",
                payload={"reason": "reconciled transcript via FETCH_RECORDING fallback"},
            )
