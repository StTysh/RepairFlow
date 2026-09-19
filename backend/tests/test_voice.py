"""Phase 5: ElevenLabs voice code path (docs/11, docs/16, docs/22's "Voice
adapter and recording tests" checklist). No live ElevenLabs credentials
exist in this environment -- every test here uses a synthetic secret/signed
payload or a monkeypatched network boundary, never the real API. Covers:
valid/invalid signature, duplicate delivery, new envelope fields, missing
analysis, empty transcript, user/agent roles, initiation failure, out-of-
order binding, unknown token/case scope, and missing audio flags.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.main as main_module
from app.config import get_settings
from app.db import session_scope
from app.integrations import elevenlabs as elevenlabs_integration
from app.models import CommunicationModel, JobModel, WebhookReceiptModel

from tests.test_hero_path import _seed_reference_data, uid

AUTH = ("operator", "repairflow-demo")
WEBHOOK_SECRET = "test-webhook-secret"
TOOL_SECRET = "test-tool-secret"


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=main_module.app), base_url="http://test")


def _sign(body: bytes, secret: str, *, timestamp: int | None = None) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{body.decode('utf-8')}"
    digest = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={ts},v0={digest}"


def _configure_webhook_secret() -> None:
    os.environ["ELEVENLABS_WEBHOOK_SECRET"] = WEBHOOK_SECRET
    get_settings.cache_clear()


def _configure_tool_secret() -> None:
    os.environ["ELEVENLABS_TOOL_SECRET"] = TOOL_SECRET
    get_settings.cache_clear()


def _clear_elevenlabs_env() -> None:
    for key in ("ELEVENLABS_WEBHOOK_SECRET", "ELEVENLABS_TOOL_SECRET", "ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID"):
        os.environ.pop(key, None)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_elevenlabs_env():
    _clear_elevenlabs_env()
    yield
    _clear_elevenlabs_env()


# --------------------------------------------------------------------------
# Pure signature math -- no app/DB involved
# --------------------------------------------------------------------------


def test_verify_webhook_signature_accepts_a_genuine_signature():
    body = b'{"type": "post_call_transcription", "event_timestamp": 1, "data": {}}'
    header = _sign(body, "shh")
    elevenlabs_integration.verify_webhook_signature(body, header, "shh")  # does not raise


def test_verify_webhook_signature_rejects_wrong_secret():
    body = b'{"type": "post_call_transcription"}'
    header = _sign(body, "shh")
    with pytest.raises(elevenlabs_integration.WebhookSignatureError):
        elevenlabs_integration.verify_webhook_signature(body, header, "different-secret")


def test_verify_webhook_signature_rejects_missing_header():
    with pytest.raises(elevenlabs_integration.WebhookSignatureError):
        elevenlabs_integration.verify_webhook_signature(b"{}", None, "shh")


def test_verify_webhook_signature_rejects_malformed_header():
    with pytest.raises(elevenlabs_integration.WebhookSignatureError):
        elevenlabs_integration.verify_webhook_signature(b"{}", "not-a-valid-header", "shh")


def test_verify_webhook_signature_rejects_stale_timestamp():
    body = b'{"type": "x"}'
    stale_ts = int(time.time()) - elevenlabs_integration.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS - 60
    header = _sign(body, "shh", timestamp=stale_ts)
    with pytest.raises(elevenlabs_integration.WebhookSignatureError):
        elevenlabs_integration.verify_webhook_signature(body, header, "shh")


# --------------------------------------------------------------------------
# transcript/outcome mapping helpers
# --------------------------------------------------------------------------


def test_map_transcript_preserves_user_agent_roles_and_skips_empty_turns():
    raw = [
        {"role": "user", "message": "The roof is leaking near the chimney.", "time_in_call_secs": 1.5},
        {"role": "agent", "message": "Thanks, can you confirm the location?", "time_in_call_secs": 4.0},
        {"role": "user", "message": ""},  # empty text -- must be skipped, not fabricated
    ]
    turns = elevenlabs_integration.map_transcript(raw)
    assert len(turns) == 2
    assert turns[0].speaker.value == "USER"
    assert turns[0].text == "The roof is leaking near the chimney."
    assert turns[1].speaker.value == "AGENT"


def test_map_transcript_handles_empty_list():
    assert elevenlabs_integration.map_transcript([]) == []


def test_map_outcome_handles_missing_analysis():
    outcome = elevenlabs_integration.map_outcome(uid(), "conv-123", {"status": "done"})
    assert outcome.outcome.value == "ANSWERED"
    assert outcome.tenant_confirms_resolved is None
    assert outcome.missing_questions == []


# --------------------------------------------------------------------------
# Webhook route, over real HTTP
# --------------------------------------------------------------------------


async def _seed_bound_communication(case_id: str | None, conversation_id: str) -> str:
    comm_id = uid()
    async with session_scope() as session:
        session.add(
            CommunicationModel(
                id=comm_id, case_id=case_id, purpose="INTAKE", direction="BROWSER",
                provider="ELEVENLABS", provider_conversation_id=conversation_id,
                correlation_token_hash=uid(), state="ACTIVE", provenance="LIVE",
            )
        )
    return comm_id


@pytest.mark.asyncio
async def test_webhook_requires_configured_secret(app_db):
    async with await _client() as client:
        r = await client.post("/webhooks/elevenlabs/post-call", content=b"{}")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(app_db):
    _configure_webhook_secret()
    body = json.dumps({"type": "post_call_transcription", "event_timestamp": int(time.time()), "data": {}}).encode()
    async with await _client() as client:
        r = await client.post(
            "/webhooks/elevenlabs/post-call", content=body,
            headers={elevenlabs_integration.WEBHOOK_SIGNATURE_HEADER: "t=1,v0=deadbeef"},
        )
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_webhook_quarantines_unmapped_conversation(app_db):
    _configure_webhook_secret()
    body = json.dumps(
        {"type": "post_call_transcription", "event_timestamp": int(time.time()), "data": {"conversation_id": "unknown-conv"}}
    ).encode()
    async with await _client() as client:
        r = await client.post(
            "/webhooks/elevenlabs/post-call", content=body,
            headers={elevenlabs_integration.WEBHOOK_SIGNATURE_HEADER: _sign(body, WEBHOOK_SECRET)},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "QUARANTINED"


@pytest.mark.asyncio
async def test_webhook_processes_transcript_and_enqueues_jobs(app_db):
    _configure_webhook_secret()
    property_id, tenant_id, _roofer_id, _scaffolder_id = await _seed_reference_data()

    from app.domain import services
    from app.domain.services import ActorContext
    from app.schemas import IntakeSubmission

    comm_id = await _seed_bound_communication(None, "conv-abc")
    async with session_scope() as session:
        case_id, _ = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description="Leak", location="Kitchen", source_text="src",
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )

    body = json.dumps(
        {
            "type": "post_call_transcription", "event_timestamp": int(time.time()),
            "data": {
                "conversation_id": "conv-abc",
                "transcript": [
                    {"role": "user", "message": "It's the kitchen ceiling.", "time_in_call_secs": 2.0},
                    {"role": "agent", "message": "Got it, thanks.", "time_in_call_secs": 5.0},
                ],
                "unexpected_future_field": {"nested": True},  # new/unknown field must not break parsing
            },
        }
    ).encode()

    async with await _client() as client:
        r = await client.post(
            "/webhooks/elevenlabs/post-call", content=body,
            headers={elevenlabs_integration.WEBHOOK_SIGNATURE_HEADER: _sign(body, WEBHOOK_SECRET)},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "PROCESSED"

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert len(comm.transcript) == 2
        assert comm.transcript[0]["speaker"] == "USER"
        assert comm.transcript[1]["speaker"] == "AGENT"
        assert comm.state == "ENDED"

        jobs = (await session.execute(select(JobModel).where(JobModel.case_id == case_id))).scalars().all()
        kinds = {j.kind for j in jobs}
        assert "FETCH_RECORDING" in kinds
        assert "COORDINATE" in kinds


@pytest.mark.asyncio
async def test_webhook_duplicate_delivery_is_idempotent(app_db):
    _configure_webhook_secret()
    comm_id = await _seed_bound_communication(None, "conv-dup")
    body = json.dumps(
        {"type": "post_call_transcription", "event_timestamp": int(time.time()), "data": {"conversation_id": "conv-dup", "transcript": []}}
    ).encode()
    signature = _sign(body, WEBHOOK_SECRET)

    async with await _client() as client:
        r1 = await client.post("/webhooks/elevenlabs/post-call", content=body, headers={elevenlabs_integration.WEBHOOK_SIGNATURE_HEADER: signature})
        r2 = await client.post("/webhooks/elevenlabs/post-call", content=body, headers={elevenlabs_integration.WEBHOOK_SIGNATURE_HEADER: signature})
    assert r1.json()["status"] == "PROCESSED"
    assert r2.json()["status"] == "DUPLICATE"

    async with session_scope() as session:
        receipts = (await session.execute(select(WebhookReceiptModel).where(WebhookReceiptModel.conversation_id == "conv-dup"))).scalars().all()
    assert len(receipts) == 1, "a redelivered identical payload must not create a second receipt"


@pytest.mark.asyncio
async def test_webhook_call_initiation_failure_marks_communication_failed(app_db):
    _configure_webhook_secret()
    comm_id = await _seed_bound_communication(None, "conv-fail")
    body = json.dumps(
        {"type": "call_initiation_failure", "event_timestamp": int(time.time()), "data": {"conversation_id": "conv-fail"}}
    ).encode()
    async with await _client() as client:
        r = await client.post("/webhooks/elevenlabs/post-call", content=body, headers={elevenlabs_integration.WEBHOOK_SIGNATURE_HEADER: _sign(body, WEBHOOK_SECRET)})
        assert r.status_code == 200

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert comm.state == "FAILED"
        assert comm.recording["status"] in ("UNAVAILABLE", "FAILED")


@pytest.mark.asyncio
async def test_webhook_missing_audio_never_reports_available(app_db):
    """post_call_audio with no full_audio payload must never leave the
    recording status AVAILABLE -- a transcript-only call is an incomplete
    integration (docs/22)."""
    _configure_webhook_secret()
    comm_id = await _seed_bound_communication(None, "conv-noaudio")
    body = json.dumps({"type": "post_call_audio", "event_timestamp": int(time.time()), "data": {"conversation_id": "conv-noaudio"}}).encode()
    async with await _client() as client:
        r = await client.post("/webhooks/elevenlabs/post-call", content=body, headers={elevenlabs_integration.WEBHOOK_SIGNATURE_HEADER: _sign(body, WEBHOOK_SECRET)})
        assert r.status_code == 200

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert comm.recording.get("status") != "AVAILABLE"


# --------------------------------------------------------------------------
# /api/v1/voice/sessions -- honest offline behavior, out-of-order binding
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_voice_session_is_honest_when_not_configured(app_db):
    async with await _client() as client:
        r = await client.post(
            "/api/v1/voice/sessions",
            json={"purpose": "INTAKE", "tenant_id": uid(), "case_id": None, "disclosure_accepted": True},
            auth=AUTH,
        )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"

    async with session_scope() as session:
        leaked = (await session.execute(select(CommunicationModel))).scalars().all()
    assert leaked == [], "a failed/unconfigured session must not leave an orphan Communication row"


@pytest.mark.asyncio
async def test_create_voice_session_rejects_missing_disclosure(app_db):
    async with await _client() as client:
        r = await client.post(
            "/api/v1/voice/sessions",
            json={"purpose": "INTAKE", "tenant_id": uid(), "case_id": None, "disclosure_accepted": False},
            auth=AUTH,
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_bind_voice_session_rejects_conflicting_conversation_id(app_db):
    comm_a = await _seed_bound_communication(None, "conv-a-already-bound")
    comm_b = uid()
    async with session_scope() as session:
        session.add(
            CommunicationModel(
                id=comm_b, purpose="INTAKE", direction="BROWSER", provider="ELEVENLABS",
                correlation_token_hash=uid(), state="REQUESTED", provenance="LIVE",
            )
        )
    async with await _client() as client:
        r = await client.post(
            f"/api/v1/voice/sessions/{comm_b}/bind", json={"provider_conversation_id": "conv-a-already-bound"}, auth=AUTH,
        )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_bind_voice_session_out_of_order_after_ended_is_still_valid(app_db):
    """Binding can race with an early "ended" notice; both must apply
    cleanly against the same communication (docs/22: out-of-order binding)."""
    comm_id = uid()
    async with session_scope() as session:
        session.add(
            CommunicationModel(
                id=comm_id, purpose="INTAKE", direction="BROWSER", provider="ELEVENLABS",
                correlation_token_hash=uid(), state="REQUESTED", provenance="LIVE",
            )
        )
    async with await _client() as client:
        r_end = await client.post(f"/api/v1/voice/sessions/{comm_id}/ended", json={"provider_conversation_id": "conv-race"}, auth=AUTH)
        assert r_end.status_code == 200
        r_bind = await client.post(f"/api/v1/voice/sessions/{comm_id}/bind", json={"provider_conversation_id": "conv-race"}, auth=AUTH)
        assert r_bind.status_code == 200


# --------------------------------------------------------------------------
# /integrations/elevenlabs/tools/* -- dedicated secret + scoped token
# --------------------------------------------------------------------------


async def _seed_session_with_token(raw_token: str) -> str:
    comm_id = uid()
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    async with session_scope() as session:
        session.add(
            CommunicationModel(
                id=comm_id, purpose="INTAKE", direction="BROWSER", provider="ELEVENLABS",
                correlation_token_hash=token_hash, state="ACTIVE", provenance="LIVE",
            )
        )
    return comm_id


@pytest.mark.asyncio
async def test_tool_intake_requires_bearer_secret(app_db):
    _configure_tool_secret()
    comm_id = await _seed_session_with_token("right-token")
    async with await _client() as client:
        r = await client.post(
            "/integrations/elevenlabs/tools/intake",
            json={
                "correlation_token": "right-token",
                "submission": {
                    "communication_id": comm_id, "property_id": uid(), "tenant_id": uid(),
                    "description": "x", "location": "y", "source_text": "z",
                },
            },
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_tool_intake_rejects_wrong_correlation_token(app_db):
    _configure_tool_secret()
    comm_id = await _seed_session_with_token("right-token")
    async with await _client() as client:
        r = await client.post(
            "/integrations/elevenlabs/tools/intake",
            headers={"Authorization": f"Bearer {TOOL_SECRET}"},
            json={
                "correlation_token": "wrong-token",
                "submission": {
                    "communication_id": comm_id, "property_id": uid(), "tenant_id": uid(),
                    "description": "x", "location": "y", "source_text": "z",
                },
            },
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_tool_intake_accepts_scoped_token_and_creates_case(app_db):
    _configure_tool_secret()
    property_id, tenant_id, _roofer_id, _scaffolder_id = await _seed_reference_data()
    comm_id = await _seed_session_with_token("good-token")
    async with await _client() as client:
        r = await client.post(
            "/integrations/elevenlabs/tools/intake",
            headers={"Authorization": f"Bearer {TOOL_SECRET}"},
            json={
                "correlation_token": "good-token",
                "submission": {
                    "communication_id": comm_id, "property_id": property_id, "tenant_id": tenant_id,
                    "description": "Water ingress", "location": "Bedroom", "source_text": "src",
                },
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] is True
    assert body["case_id"] is not None
    assert "coordination is pending" in body["message"].lower()


@pytest.mark.asyncio
async def test_tool_context_returns_minimum_permitted_context(app_db):
    _configure_tool_secret()
    property_id, tenant_id, _roofer_id, _scaffolder_id = await _seed_reference_data()
    comm_id = uid()
    token_hash = hashlib.sha256(b"ctx-token").hexdigest()
    async with session_scope() as session:
        session.add(
            CommunicationModel(
                id=comm_id, tenant_id=tenant_id, purpose="INTAKE", direction="BROWSER", provider="ELEVENLABS",
                correlation_token_hash=token_hash, state="ACTIVE", provenance="LIVE",
            )
        )
    async with await _client() as client:
        r = await client.post(
            "/integrations/elevenlabs/tools/context",
            headers={"Authorization": f"Bearer {TOOL_SECRET}"},
            json={"correlation_token": "ctx-token", "communication_id": comm_id},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_display_name"] == "Jordan Hale"
    assert body["property_address"] == "1 Test St"


# --------------------------------------------------------------------------
# FETCH_RECORDING reconciliation, against a monkeypatched network boundary
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_recording_persists_transcript_and_audio(app_db, monkeypatch):
    os.environ["ELEVENLABS_API_KEY"] = "fake-key"
    os.environ["ELEVENLABS_AGENT_ID"] = "fake-agent"
    get_settings.cache_clear()

    comm_id = await _seed_bound_communication(None, "conv-fetch")

    async def fake_details(conversation_id: str, *, api_key: str) -> dict:
        assert conversation_id == "conv-fetch"
        return {
            "status": "done",
            "transcript": [{"role": "user", "message": "Test phrase.", "time_in_call_secs": 1.0}],
            "analysis": {"tenant_confirms_resolved": True},
        }

    async def fake_audio(conversation_id: str, *, api_key: str) -> bytes:
        return b"FAKE-MP3-BYTES"

    monkeypatch.setattr(elevenlabs_integration, "fetch_conversation_details", fake_details)
    monkeypatch.setattr(elevenlabs_integration, "fetch_conversation_audio", fake_audio)

    await elevenlabs_integration.fetch_recording(comm_id)

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert len(comm.transcript) == 1
        assert comm.transcript[0]["text"] == "Test phrase."
        assert comm.outcome["tenant_confirms_resolved"] is True
        assert comm.recording["status"] == "AVAILABLE"
        assert comm.recording["byte_count"] == len(b"FAKE-MP3-BYTES")

    settings = get_settings()
    saved = settings.recordings_dir / comm.recording["media_path"]
    assert saved.exists()
    assert saved.read_bytes() == b"FAKE-MP3-BYTES"


@pytest.mark.asyncio
async def test_fetch_recording_does_not_overwrite_existing_transcript(app_db, monkeypatch):
    os.environ["ELEVENLABS_API_KEY"] = "fake-key"
    os.environ["ELEVENLABS_AGENT_ID"] = "fake-agent"
    get_settings.cache_clear()

    comm_id = await _seed_bound_communication(None, "conv-already-has-transcript")
    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        comm.transcript = [{"turn_id": "1", "speaker": "USER", "text": "original", "time_in_call_secs": 0.0, "tool_name": None}]

    async def fake_details(conversation_id: str, *, api_key: str) -> dict:
        return {"status": "done", "transcript": [{"role": "user", "message": "should not appear"}]}

    async def fake_audio(conversation_id: str, *, api_key: str) -> bytes:
        return b""  # empty -- must not report AVAILABLE

    monkeypatch.setattr(elevenlabs_integration, "fetch_conversation_details", fake_details)
    monkeypatch.setattr(elevenlabs_integration, "fetch_conversation_audio", fake_audio)

    await elevenlabs_integration.fetch_recording(comm_id)

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert len(comm.transcript) == 1
        assert comm.transcript[0]["text"] == "original", "reconciliation must not overwrite an already-populated transcript"
        assert comm.recording["status"] != "AVAILABLE", "empty audio bytes must never be reported as AVAILABLE"


@pytest.mark.asyncio
async def test_fetch_recording_honest_when_not_configured(app_db):
    comm_id = await _seed_bound_communication(None, "conv-unconfigured")
    await elevenlabs_integration.fetch_recording(comm_id)
    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert comm.recording["status"] == "UNAVAILABLE"
        assert comm.recording["error_code"] == "PROVIDER_NOT_CONFIGURED"
