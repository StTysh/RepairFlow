"""No-contact verification harness for the ElevenLabs/Twilio call path.

The live integration is real: `backend/.env` carries a working API key, a
Twilio-backed phone number id and an allowlisted personal number. The point
of this module is to prove the *downstream* handling works -- request
accepted, conversation retrieved, transcript parsed, outcome mapped, state
transitioned, recording stored -- **without a phone ever ringing**.

Two independent mechanisms make that safe, and both are asserted here:

1. `app.integrations.no_contact` refuses real outreach whenever
   `FIXI_NO_CONTACT` is set *or* the process is running under pytest. The
   guard sits inside `place_outbound_call()`, the single function in the
   codebase that dials, so it covers every caller including future ones.
2. A deterministic substitute is monkeypatched over that transport for the
   duration of a test, and `provider_substitute()` records that it exists
   so the job body is allowed to proceed past the skip.

The two are deliberately not the same switch. `test_transport_guard_*`
below proves the fail-closed property: arming the substitute flag *without*
patching the transport does not dial, it raises.

Everything written here is marked test data and lives in the per-test
temp database created by the `app_db` fixture. Transcript text is
synthetic and labelled as such; nothing claims a real conversation
occurred.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest

from app.config import get_settings
from app.db import session_scope
from app.integrations import elevenlabs as el
from app.integrations.no_contact import (
    NoContactViolation,
    no_contact_enabled,
    provider_substitute,
)
from app.models import CaseEventModel, CommunicationModel, JobModel
from app.schemas import CallOutcomeStatus, RecordingStatus

from tests.test_hero_path import _seed_reference_data, uid

# A number that is deliberately NOT the owner's. Even if every guard in
# this file failed simultaneously, this is what would be dialled -- and
# +44 7700 900xxx is Ofcom's reserved drama/test range, which never routes
# to a real subscriber.
TEST_NUMBER = "+447700900123"

SYNTHETIC_CONVERSATION_ID = "conv_TEST_synthetic_0001"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _configure_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test-only credentials. Real ones are never read here, and signature
    verification is never disabled -- only pointed at a test secret."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-a-real-credential")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_test")
    monkeypatch.setenv("ELEVENLABS_PHONE_NUMBER_ID", "phnum_test")
    monkeypatch.setenv("OUTBOUND_CALLS_ENABLED", "true")
    monkeypatch.setenv("OUTBOUND_CALL_ALLOWLIST", f'["{TEST_NUMBER}"]')
    get_settings.cache_clear()


def _synthetic_details(
    *,
    status: str = "done",
    termination_reason: str = "end_call_tool",
    with_user_turn: bool = True,
) -> dict:
    """A schema-valid conversation-details payload.

    Shaped to the contract `map_outcome`/`map_transcript` parse, so the
    real parsing, validation and persistence paths run unchanged. Marked
    as test content in the transcript text itself.
    """
    transcript = [
        {
            "role": "agent",
            "message": "[TEST FIXTURE] Hello, I'm calling about the reported repair.",
            "time_in_call_secs": 1.0,
            "turn_id": "t1",
        }
    ]
    if with_user_turn:
        transcript.append(
            {
                "role": "user",
                "message": "[TEST FIXTURE] Yes, Tuesday morning works for me.",
                "time_in_call_secs": 7.5,
                "turn_id": "t2",
            }
        )
    return {
        "conversation_id": SYNTHETIC_CONVERSATION_ID,
        "status": status,
        "metadata": {
            "termination_reason": termination_reason,
            "call_duration_secs": 24,
        },
        "transcript": transcript,
        "analysis": {
            "transcript_summary": "[TEST FIXTURE] Tenant available Tuesday morning.",
        },
    }


async def _make_communication(case_id: str, tenant_id: str) -> str:
    comm_id = uid()
    async with session_scope() as session:
        session.add(
            CommunicationModel(
                id=comm_id,
                case_id=case_id,
                tenant_id=tenant_id,
                purpose="FOLLOW_UP",
                direction="OUTBOUND",
                correlation_token_hash=uid(),
                state="REQUESTED",
            )
        )
    return comm_id


async def _case_with_tenant_phone(phone: str | None = TEST_NUMBER) -> tuple[str, str]:
    """A minimal case + tenant with a phone number, without driving the
    whole hero path (this module is about the transport, not triage)."""
    from app.models import RepairCaseModel, RepairIssueModel, TenantModel

    property_id, tenant_id, _roofer, _scaffolder = await _seed_reference_data()
    case_id = uid()
    async with session_scope() as session:
        tenant = await session.get(TenantModel, tenant_id)
        assert tenant is not None
        tenant.phone_e164 = phone
        session.add(
            RepairCaseModel(
                id=case_id,
                case_number=9001,
                property_id=property_id,
                tenant_id=tenant_id,
                status="ACTIVE",
                title="[TEST] Water ingress in the rear bedroom",
                risk={},
            )
        )
        await session.flush()
        session.add(
            RepairIssueModel(
                id=uid(),
                case_id=case_id,
                description="[TEST] Water ingress",
                location="Rear bedroom",
            )
        )
    return case_id, tenant_id


# ---------------------------------------------------------------------------
# 1. the guard itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_contact_is_on_by_default_under_pytest():
    """The whole suite is protected, not just this file. If this ever goes
    false, a stray test could dial a real number."""
    assert no_contact_enabled() is True


@pytest.mark.asyncio
async def test_real_transport_raises_instead_of_dialling():
    """`place_outbound_call` is the one function that makes a phone ring.
    Called for real under no-contact mode it must raise before any socket
    is opened -- not warn, not no-op."""
    with pytest.raises(NoContactViolation) as excinfo:
        await el.place_outbound_call(
            api_key="unused",
            agent_id="unused",
            agent_phone_number_id="unused",
            to_number=TEST_NUMBER,
            dynamic_variables={},
        )
    assert excinfo.value.channel == "voice_call"
    assert TEST_NUMBER in str(excinfo.value)


@pytest.mark.asyncio
async def test_transport_guard_fails_closed_when_substitute_is_missing(
    app_db, monkeypatch: pytest.MonkeyPatch
):
    """Arming the substitute flag without actually patching the transport
    must NOT fall through to the real client. This is the fail-closed
    property the whole design rests on."""
    _configure_provider(monkeypatch)
    case_id, tenant_id = await _case_with_tenant_phone()
    comm_id = await _make_communication(case_id, tenant_id)

    with provider_substitute():
        # No monkeypatch of place_outbound_call here -- on purpose.
        with pytest.raises(NoContactViolation):
            await el.place_call(comm_id, question="Are you free Tuesday?")


@pytest.mark.asyncio
async def test_place_call_skips_and_records_when_no_substitute_armed(
    app_db, monkeypatch: pytest.MonkeyPatch
):
    """Without a substitute the job body refuses -- and records a durable
    CALL_SKIPPED event rather than silently doing nothing, so the refusal
    is auditable."""
    _configure_provider(monkeypatch)
    case_id, tenant_id = await _case_with_tenant_phone()
    comm_id = await _make_communication(case_id, tenant_id)

    await el.place_call(comm_id, question="Are you free Tuesday?")

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert comm is not None
        # Terminal, not left dangling at REQUESTED where reconciliation
        # would never see it again.
        assert comm.state == "FAILED"
        assert comm.provider_conversation_id is None
        events = (
            await session.execute(
                CaseEventModel.__table__.select().where(CaseEventModel.case_id == case_id)
            )
        ).fetchall()
    skipped = [e for e in events if e.type == "CALL_SKIPPED"]
    assert len(skipped) == 1
    assert "no-contact" in skipped[0].payload["reason"]


# ---------------------------------------------------------------------------
# 2. downstream processing with a deterministic substitute
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_call_downstream_path(app_db, monkeypatch: pytest.MonkeyPatch):
    """Acceptance -> correlation -> retrieval -> transcript -> outcome.

    Models the real contract's separation between "the provider accepted
    the request" and "the call later completed": `place_call` only records
    acceptance, and nothing is known about how it went until
    `fetch_recording` retrieves the conversation.
    """
    _configure_provider(monkeypatch)
    case_id, tenant_id = await _case_with_tenant_phone()
    comm_id = await _make_communication(case_id, tenant_id)

    dialled: list[dict] = []

    async def fake_place(*, api_key, agent_id, agent_phone_number_id, to_number, dynamic_variables):
        dialled.append({"to": to_number, "vars": dynamic_variables})
        return {"conversation_id": SYNTHETIC_CONVERSATION_ID, "callSid": "CA_TEST_0001"}

    monkeypatch.setattr(el, "place_outbound_call", fake_place)

    with provider_substitute():
        await el.place_call(comm_id, question="Are you free Tuesday?")

    # Acceptance only: correlated, in flight, nothing concluded.
    assert len(dialled) == 1
    assert dialled[0]["to"] == TEST_NUMBER
    assert dialled[0]["vars"]["communication_id"] == comm_id
    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert comm is not None
        assert comm.provider_conversation_id == SYNTHETIC_CONVERSATION_ID
        assert not comm.transcript
        assert comm.outcome is None

    # Later completion, delivered through the normal retrieval path.
    monkeypatch.setattr(
        el,
        "fetch_conversation_details",
        lambda conversation_id, *, api_key: _coro(_synthetic_details()),
    )
    monkeypatch.setattr(
        el,
        "fetch_conversation_audio",
        lambda conversation_id, *, api_key: _coro(b"TEST-AUDIO-NOT-A-REAL-RECORDING"),
    )

    with provider_substitute():
        await el.fetch_recording(comm_id)

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert comm is not None
        assert comm.state == "ENDED"
        assert len(comm.transcript) == 2
        assert all("[TEST FIXTURE]" in turn["text"] for turn in comm.transcript)
        assert comm.outcome is not None
        assert comm.outcome["outcome"] == CallOutcomeStatus.ANSWERED.value
        assert comm.recording["status"] == RecordingStatus.AVAILABLE.value


@pytest.mark.asyncio
async def test_failed_call_is_reported_as_failed(app_db, monkeypatch: pytest.MonkeyPatch):
    _configure_provider(monkeypatch)
    case_id, tenant_id = await _case_with_tenant_phone()
    comm_id = await _make_communication(case_id, tenant_id)

    async def fake_place(**_kwargs):
        return {"conversation_id": SYNTHETIC_CONVERSATION_ID, "callSid": "CA_TEST_0002"}

    monkeypatch.setattr(el, "place_outbound_call", fake_place)
    monkeypatch.setattr(
        el,
        "fetch_conversation_details",
        lambda conversation_id, *, api_key: _coro(
            _synthetic_details(status="failed", termination_reason="error", with_user_turn=False)
        ),
    )
    monkeypatch.setattr(
        el, "fetch_conversation_audio", lambda conversation_id, *, api_key: _coro(b"")
    )

    with provider_substitute():
        await el.place_call(comm_id)
        await el.fetch_recording(comm_id)

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert comm is not None
        assert comm.outcome["outcome"] == CallOutcomeStatus.FAILED.value


@pytest.mark.asyncio
async def test_unanswered_call_is_not_reported_as_answered(
    app_db, monkeypatch: pytest.MonkeyPatch
):
    """No closure inferred from silence: a finished session with no USER
    turn is UNKNOWN, never ANSWERED."""
    _configure_provider(monkeypatch)
    case_id, tenant_id = await _case_with_tenant_phone()
    comm_id = await _make_communication(case_id, tenant_id)

    monkeypatch.setattr(
        el,
        "place_outbound_call",
        lambda **_kw: _coro({"conversation_id": SYNTHETIC_CONVERSATION_ID, "callSid": "CA_T3"}),
    )
    monkeypatch.setattr(
        el,
        "fetch_conversation_details",
        lambda conversation_id, *, api_key: _coro(
            _synthetic_details(termination_reason="agent_hangup", with_user_turn=False)
        ),
    )
    monkeypatch.setattr(
        el, "fetch_conversation_audio", lambda conversation_id, *, api_key: _coro(b"x")
    )

    with provider_substitute():
        await el.place_call(comm_id)
        await el.fetch_recording(comm_id)

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert comm is not None
        assert comm.outcome["outcome"] == CallOutcomeStatus.UNKNOWN.value


@pytest.mark.asyncio
async def test_duplicate_retrieval_is_idempotent(app_db, monkeypatch: pytest.MonkeyPatch):
    """Providers redeliver. A second retrieval of the same conversation
    must not duplicate transcript turns or re-append events."""
    _configure_provider(monkeypatch)
    case_id, tenant_id = await _case_with_tenant_phone()
    comm_id = await _make_communication(case_id, tenant_id)

    monkeypatch.setattr(
        el,
        "place_outbound_call",
        lambda **_kw: _coro({"conversation_id": SYNTHETIC_CONVERSATION_ID, "callSid": "CA_T4"}),
    )
    monkeypatch.setattr(
        el,
        "fetch_conversation_details",
        lambda conversation_id, *, api_key: _coro(_synthetic_details()),
    )
    monkeypatch.setattr(
        el, "fetch_conversation_audio", lambda conversation_id, *, api_key: _coro(b"audio")
    )

    with provider_substitute():
        await el.place_call(comm_id)
        await el.fetch_recording(comm_id)
        async with session_scope() as session:
            first = await session.get(CommunicationModel, comm_id)
            assert first is not None
            turns_after_first = len(first.transcript)
        await el.fetch_recording(comm_id)

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert comm is not None
        assert len(comm.transcript) == turns_after_first


@pytest.mark.asyncio
async def test_provider_http_failure_is_recorded_not_swallowed(
    app_db, monkeypatch: pytest.MonkeyPatch
):
    _configure_provider(monkeypatch)
    case_id, tenant_id = await _case_with_tenant_phone()
    comm_id = await _make_communication(case_id, tenant_id)

    async def boom(**_kwargs):
        raise httpx.ConnectError("simulated provider outage")

    monkeypatch.setattr(el, "place_outbound_call", boom)

    with provider_substitute():
        await el.place_call(comm_id)

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        assert comm is not None
        assert comm.state == "FAILED"
        events = (
            await session.execute(
                CaseEventModel.__table__.select().where(CaseEventModel.case_id == case_id)
            )
        ).fetchall()
    assert any(e.type == "CALL_FAILED" for e in events)


@pytest.mark.asyncio
async def test_harness_creates_no_outbound_jobs_for_other_cases(app_db, monkeypatch):
    """The harness must not leave work in the durable queue that a later
    process would pick up and act on."""
    _configure_provider(monkeypatch)
    case_id, tenant_id = await _case_with_tenant_phone()
    comm_id = await _make_communication(case_id, tenant_id)

    monkeypatch.setattr(
        el,
        "place_outbound_call",
        lambda **_kw: _coro({"conversation_id": SYNTHETIC_CONVERSATION_ID, "callSid": "CA_T5"}),
    )
    with provider_substitute():
        await el.place_call(comm_id)

    async with session_scope() as session:
        rows = (
            await session.execute(
                JobModel.__table__.select().where(JobModel.kind == "PLACE_CALL")
            )
        ).fetchall()
    assert rows == []


# ---------------------------------------------------------------------------


def _coro(value):
    """Wrap a plain value in an awaitable, so a lambda can stand in for an
    async function in `monkeypatch.setattr`."""

    async def _inner():
        return value

    return _inner()


__all__ = [
    "SYNTHETIC_CONVERSATION_ID",
    "TEST_NUMBER",
]

# Keep the imports the module genuinely uses visible to linters.
_ = (uuid, datetime, timezone)
