"""Regression tests for the audit-sweep fixes (docs/audit/*). Each test
guards exactly one defect that shipped with no coverage; the docstring on
each test names the real symptom and where the fix lives. Style follows
tests/test_fixi_ui_support.py and tests/test_api.py: pytest.mark.asyncio,
the shared `app_db` fixture, session_scope() for direct inserts, and an
explicit `await session.flush()` at every FK boundary -- these models
declare raw FK columns with no relationship(), so SQLAlchemy has no
dependency graph to order INSERTs by, and PRAGMA foreign_keys=ON turns an
out-of-order insert into a hard IntegrityError.

Everything here runs in-process against app.main.app via httpx's
ASGITransport (never a real server) and an isolated, temp-file SQLite
database (never backend/data/repairflow.db) -- both supplied by the
`app_db` fixture in tests/conftest.py.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

import app.main as main_module
from app.config import get_settings
from app.db import session_scope
from app.domain import services
from app.domain.errors import ConflictError
from app.domain.services import ActorContext
from app.integrations.booking import mock_booking_connector
from app.models import (
    ActionRecordModel,
    AppointmentModel,
    ArchiveBatchModel,
    CaseEventModel,
    CommunicationModel,
    ContractorReportModel,
    DocumentModel,
    JobModel,
    PropertyModel,
    RepairCaseModel,
    RepairIssueModel,
    TenantModel,
    WorkOrderModel,
)
from app.orchestration import dispatcher, worker
from app.orchestration.dispatcher import FixtureCoordinator
from app.orchestration.executor import decide_approval
from app.schemas import ActionState, ApprovalDecision, CommandResult, Trade

from tests.test_hero_path import (
    _broad_tenant_window,
    _schedule_builder,
    _seed_reference_data,
    uid,
)

AUTH = ("operator", "repairflow-demo")


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=main_module.app), base_url="http://test")


def _case_number() -> int:
    # uq_case_number is a real UNIQUE constraint; a random int keeps
    # multiple cases within one test (or across tests, since some
    # concurrency tests may race) from colliding.
    return uuid.uuid4().int % 900_000 + 1


async def _seed_property_tenant() -> tuple[str, str]:
    property_id, tenant_id = uid(), uid()
    async with session_scope() as session:
        session.add(
            PropertyModel(
                id=property_id, address_line="1 Audit St", postcode="BS1 1AA",
                landlord_reference="LL-AUDIT", roof_responsibility="LANDLORD",
            )
        )
        session.add(
            TenantModel(
                id=tenant_id, property_id=property_id, display_name="Audit Tenant",
                preferred_channel="EMAIL", contact_allowed=True,
            )
        )
    return property_id, tenant_id


async def _seed_bare_case(
    property_id: str, tenant_id: str, *, status: str = "ACTIVE",
    risk: dict | None = None, archive_batch_id: str | None = None,
) -> str:
    """A RepairCaseModel row with no issue/work order -- enough for tests
    that only need a case to exist (lifecycle transitions, the dispatcher
    gate, direct ActionRecord/CaseEvent wiring)."""
    case_id = uid()
    async with session_scope() as session:
        session.add(
            RepairCaseModel(
                id=case_id, case_number=_case_number(), property_id=property_id, tenant_id=tenant_id,
                status=status, version=1, title="Audit test case", risk=risk or {},
                archive_batch_id=archive_batch_id,
            )
        )
    return case_id


async def _seed_case_created_event(case_id: str) -> str:
    event_id = uid()
    async with session_scope() as session:
        session.add(
            CaseEventModel(
                id=event_id, case_id=case_id, seq=1, type="CASE_CREATED", actor_type="SYSTEM", actor_id="test",
                source_event_key=f"seed:{case_id}", correlation_id=case_id,
            )
        )
    return event_id


class _NeverCalledCoordinator:
    """Spy coordinator: raises if decide() is ever invoked. Used to prove a
    frozen/gated case never reaches the model at all."""

    model_id = "never-called-coordinator"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, snapshot, trigger_event_id):
        self.calls += 1
        raise AssertionError("coordinator.decide() should never be called here")


# --------------------------------------------------------------------------
# 1. A frozen case is not coordinated (app/orchestration/dispatcher.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_frozen_case_not_coordinated(app_db):
    """run_coordinate used to have no guard at the top at all: a stale
    COORDINATE job left in the durable queue (e.g. enqueued just before a
    human escalated or cancelled the case) would wake the model and let the
    executor act -- including placing an outbound call -- on a case nobody
    expected movement on. Both ESCALATED and CANCELLED must short-circuit
    to None before the coordinator is ever invoked, with no new event or
    job appended."""
    property_id, tenant_id = await _seed_property_tenant()

    for status in ("ESCALATED", "CANCELLED"):
        case_id = await _seed_bare_case(property_id, tenant_id, status=status)
        event_id = await _seed_case_created_event(case_id)
        spy = _NeverCalledCoordinator()

        result = await dispatcher.run_coordinate(case_id=case_id, trigger_event_id=event_id, coordinator=spy)

        assert result is None
        assert spy.calls == 0, f"coordinator must never be invoked for a {status} case"

        async with session_scope() as session:
            events = (
                await session.execute(select(CaseEventModel).where(CaseEventModel.case_id == case_id))
            ).scalars().all()
            jobs = (
                await session.execute(select(JobModel).where(JobModel.case_id == case_id))
            ).scalars().all()
        assert len(events) == 1, f"no new event expected for a frozen {status} case"
        assert jobs == [], f"no job expected for a frozen {status} case"


# --------------------------------------------------------------------------
# 2. A hazard reported after resolution still escalates
#    (app/orchestration/dispatcher.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hazard_after_resolution_still_escalates(app_db):
    """A hazard fact recorded against an already-RESOLVED case used to be
    silently dropped: the deterministic hazard gate excluded RESOLVED
    alongside ESCALATED/CANCELLED, so "the gas smell came back" after
    sign-off never escalated anything -- even though RESOLVED -> ESCALATED
    has always been a legal transition (app/domain/transitions.py) and
    escalate_to_human has always been able to make it. The gate must
    escalate a RESOLVED case whose risk carries a hazard, never calling the
    coordinator to do so."""
    property_id, tenant_id = await _seed_property_tenant()
    hazard_risk = {
        "urgency": "EMERGENCY", "gas": "YES", "fire": "NO", "water_near_electrics": "NO",
        "structural_danger": "NO", "uncontrolled_flood": "NO", "vulnerability_concern": "NO",
    }
    case_id = await _seed_bare_case(property_id, tenant_id, status="RESOLVED", risk=hazard_risk)
    event_id = await _seed_case_created_event(case_id)
    spy = _NeverCalledCoordinator()

    result = await dispatcher.run_coordinate(case_id=case_id, trigger_event_id=event_id, coordinator=spy)

    assert result is None
    assert spy.calls == 0, "the hazard gate must divert before ever calling the model"

    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        escalated_events = (
            await session.execute(
                select(CaseEventModel).where(CaseEventModel.case_id == case_id, CaseEventModel.type == "CASE_ESCALATED")
            )
        ).scalars().all()
    assert case.status == "ESCALATED", "a hazard on a RESOLVED case must escalate it, not leave it RESOLVED"
    assert len(escalated_events) == 1


# --------------------------------------------------------------------------
# 3. Concurrent approvals (app/orchestration/executor.py's conditional
#    UPDATE claim)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_approvals_produce_clean_conflict_not_double_execution(app_db, monkeypatch):
    """Two operators approving the same AWAITING_APPROVAL action at once
    used to both pass the read-then-check and both proceed to act -- the
    only thing that had stopped a double-execution in production was an
    incidental UNIQUE constraint on case_events(case_id, source_event_key),
    which surfaced as an unhandled 500 rather than a clean conflict.
    decide_approval now claims the row with a conditional UPDATE (WHERE
    state='AWAITING_APPROVAL') before acting on it: the loser must get a
    clean ConflictError -- never a raw exception, never a second
    APPROVAL_DECIDED event.

    A plain asyncio.gather() of two decide_approval() calls is not
    reliably concurrent -- observed empirically: the whole first call
    (including its commit) can complete before the second's first `await`
    is even scheduled, in which case the second sees state=PENDING already
    and takes the *earlier* state-check branch (PolicyRejectedError), never
    reaching the conditional UPDATE this test exists to protect. A small
    barrier on AsyncSession.get forces both calls' initial read of the
    action row to happen before either proceeds, reproducing the genuine
    race the fix's own docstring describes ("both saw AWAITING_APPROVAL and
    both proceeded")."""
    from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession

    property_id, tenant_id = await _seed_property_tenant()
    case_id = await _seed_bare_case(property_id, tenant_id, status="ACTIVE")
    action_id = uid()
    async with session_scope() as session:
        session.add(
            ActionRecordModel(
                id=action_id, case_id=case_id, kind="APPLY_TRIAGE", target_id=None,
                idempotency_key=f"race:{action_id}", payload_hash="fixed-hash", proposal={},
                state=ActionState.AWAITING_APPROVAL.value,
            )
        )

    decision = ApprovalDecision(
        action_id=uuid.UUID(action_id), expected_case_version=1, approve=True,
        reason="approve", action_payload_hash="fixed-hash",
    )

    original_get = SAAsyncSession.get
    hits = 0
    release_event = asyncio.Event()

    async def _synced_get(self, entity, ident, *args, **kwargs):
        nonlocal hits
        row = await original_get(self, entity, ident, *args, **kwargs)
        # Only synchronize the specific "fetch the action being approved"
        # read both calls make first -- the later `load_case` get() for the
        # same case_id, and any other session's get() elsewhere, must not
        # be held up by this barrier.
        if entity is ActionRecordModel and str(ident) == action_id:
            hits += 1
            if hits == 1:
                await release_event.wait()
            else:
                release_event.set()
        return row

    monkeypatch.setattr(SAAsyncSession, "get", _synced_get)

    async def _attempt():
        async with session_scope() as session:
            return await decide_approval(session, decision, ActorContext("OPERATOR", "operator", uid()))

    results = await asyncio.gather(_attempt(), _attempt(), return_exceptions=True)

    successes = [r for r in results if isinstance(r, CommandResult)]
    conflicts = [r for r in results if isinstance(r, ConflictError)]
    other_errors = [r for r in results if isinstance(r, BaseException) and not isinstance(r, ConflictError)]

    assert not other_errors, f"expected only a clean ConflictError, got: {other_errors!r}"
    assert len(successes) == 1, f"expected exactly one winner, got {len(successes)}"
    assert len(conflicts) == 1, f"expected exactly one ConflictError, got {len(conflicts)}"

    async with session_scope() as session:
        events = (
            await session.execute(
                select(CaseEventModel).where(CaseEventModel.case_id == case_id, CaseEventModel.type == "APPROVAL_DECIDED")
            )
        ).scalars().all()
    assert len(events) == 1, "the action must never be double-executed"


# --------------------------------------------------------------------------
# 4. Archival cases are read-only for lifecycle actions (app/api/cases.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archival_case_lifecycle_actions_are_read_only(app_db):
    """resume/reopen/cancel on an archival sample case (archive_batch_id
    set) used to run the ordinary lifecycle transition like any real case
    -- a row that exists purely to populate charts could be silently
    mutated by an operator clicking a button meant for live casework. All
    three endpoints must 409, and status/version must be unchanged after
    all three."""
    property_id, tenant_id = await _seed_property_tenant()
    batch_id = uid()
    async with session_scope() as session:
        session.add(
            ArchiveBatchModel(id=batch_id, label=f"audit-batch-{batch_id}", generator_version="test", random_seed=1)
        )
    case_id = await _seed_bare_case(property_id, tenant_id, status="ESCALATED", archive_batch_id=batch_id)

    async with session_scope() as session:
        case_before = await services.load_case(session, case_id)
    version_before, status_before = case_before.version, case_before.status

    async with await _client() as client:
        r = await client.post(
            f"/api/v1/cases/{case_id}/resume",
            json={"version": version_before, "reason": "x", "resolved_hold_evidence": "y"}, auth=AUTH,
        )
        assert r.status_code == 409, r.text
        r = await client.post(
            f"/api/v1/cases/{case_id}/reopen", json={"version": version_before, "reason": "x"}, auth=AUTH,
        )
        assert r.status_code == 409, r.text
        r = await client.post(
            f"/api/v1/cases/{case_id}/cancel", json={"version": version_before, "reason": "x"}, auth=AUTH,
        )
        assert r.status_code == 409, r.text

    async with session_scope() as session:
        case_after = await services.load_case(session, case_id)
    assert case_after.status == status_before
    assert case_after.version == version_before


# --------------------------------------------------------------------------
# 5. A report cannot be posted to the wrong case (app/api/cases.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_cannot_be_posted_to_wrong_case(app_db):
    """POST /cases/{A}/reports carrying a work_order_id (and a genuinely
    matching appointment_id) that actually belong to case B used to be
    accepted with a 202: record_contractor_report derives the case from
    the work order, not from the URL, so the report silently landed on
    case B. submit_report must 404 when the work order isn't in the case
    named in the path, and nothing must be created against either case.

    Both work_order_id and appointment_id must be real, case-B-consistent
    rows here -- record_contractor_report's own appointment check (`not in
    case {case_id}`) also 404s on a merely-nonexistent appointment_id, so a
    test using a random uuid there would pass whether or not the
    case-mismatch guard this test targets exists at all."""
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    case_a = await _seed_bare_case(property_id, tenant_id)
    case_b = await _seed_bare_case(property_id, tenant_id)

    issue_b_id, wo_b_id, action_b_id, appt_b_id = uid(), uid(), uid(), uid()
    async with session_scope() as session:
        session.add(RepairIssueModel(id=issue_b_id, case_id=case_b, description="Issue B", location="Kitchen"))
        await session.flush()
        session.add(
            WorkOrderModel(
                id=wo_b_id, case_id=case_b, issue_id=issue_b_id, kind="REPAIR", trade="ROOFING",
                scope="Fix the roof", status="SCHEDULED", contractor_id=roofer_id,
            )
        )
        session.add(
            ActionRecordModel(
                id=action_b_id, case_id=case_b, kind="SCHEDULE_VISIT", target_id=wo_b_id,
                idempotency_key=f"wrong-case-test:{action_b_id}", payload_hash="hash", proposal={},
                state=ActionState.SUCCEEDED.value,
            )
        )
        await session.flush()
        now = datetime.now(timezone.utc)
        session.add(
            AppointmentModel(
                id=appt_b_id, case_id=case_b, work_order_id=wo_b_id, contractor_id=roofer_id,
                slot_id=f"manual:{appt_b_id}", start_at=now + timedelta(days=1), end_at=now + timedelta(days=1, hours=3),
                status="CONFIRMED", connector="MOCK", provider_booking_id=f"wrong-case-test-{appt_b_id}",
                action_id=action_b_id, attempt_number=1, provenance="SIMULATED",
            )
        )

    async with await _client() as client:
        r = await client.post(
            f"/api/v1/cases/{case_a}/reports",
            json={
                "work_order_id": wo_b_id, "appointment_id": appt_b_id, "contractor_id": roofer_id,
                "text": "Report wrongly targeted at case A", "observed_at": datetime.now(timezone.utc).isoformat(),
            },
            auth=AUTH,
        )
    assert r.status_code == 404, r.text

    async with session_scope() as session:
        reports = (
            await session.execute(select(ContractorReportModel).where(ContractorReportModel.case_id.in_([case_a, case_b])))
        ).scalars().all()
    assert reports == [], "no report should have been created against either case"


# --------------------------------------------------------------------------
# 6 & 7. Document content-type/filename hardening (app/api/documents.py)
# --------------------------------------------------------------------------


@pytest.fixture
def documents_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "documents"))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_uploaded_svg_never_served_inline(app_db, documents_dir):
    """`content_type.startswith("image/")` used to gate what the browser
    may render inline; image/svg+xml passes that test, and an SVG is a
    document that can execute script -- so an uploaded SVG came back
    inline from this app's own origin with its <script> intact (a
    same-origin XSS against the operator's session). Only an explicit
    allowlist may render inline now, and SVG is deliberately excluded;
    genuine raster images must still come back inline."""
    property_id, tenant_id = await _seed_property_tenant()
    case_id = await _seed_bare_case(property_id, tenant_id)

    async with await _client() as client:
        r = await client.post(
            "/api/v1/documents",
            data={"subject_type": "CASE", "subject_id": case_id},
            files={
                "file": (
                    "evil.svg",
                    b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                    "image/svg+xml",
                )
            },
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        svg_id = r.json()["id"]

        r = await client.get(f"/api/v1/documents/{svg_id}/content", auth=AUTH)
        assert r.status_code == 200
        assert r.headers["content-disposition"].startswith("attachment"), (
            "an SVG must never be served inline"
        )
        assert r.headers["content-type"].split(";")[0] != "image/svg+xml"
        assert r.headers["x-content-type-options"] == "nosniff"

        r = await client.post(
            "/api/v1/documents",
            data={"subject_type": "CASE", "subject_id": case_id},
            files={"file": ("photo.png", b"\x89PNG\r\n\x1a\nfake-but-declared-png-bytes", "image/png")},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        png_id = r.json()["id"]

        r = await client.get(f"/api/v1/documents/{png_id}/content", auth=AUTH)
        assert r.status_code == 200
        assert r.headers["content-disposition"].startswith("inline"), (
            "a genuine raster image must still be served inline"
        )


@pytest.mark.asyncio
async def test_document_filename_cannot_inject_response_header(app_db, documents_dir):
    """display_name flows straight into the Content-Disposition header. A
    filename containing a quote and a CRLF used to be echoed back
    verbatim -- a response-header-injection primitive from an untrusted
    upload name. The served header must contain neither character,
    whatever display_name holds. Written straight onto the row (rather
    than relying on a transport-level multipart filename, which a
    conformant parser won't reliably carry a raw CRLF through) so this
    exercises exactly the sanitization get_document_content applies,
    independent of how display_name got set."""
    property_id, tenant_id = await _seed_property_tenant()
    case_id = await _seed_bare_case(property_id, tenant_id)

    async with await _client() as client:
        r = await client.post(
            "/api/v1/documents",
            data={"subject_type": "CASE", "subject_id": case_id},
            files={"file": ("normal.txt", b"hello", "text/plain")},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        doc_id = r.json()["id"]

    malicious = 'evil".pdf\r\nX-Injected: true'
    async with session_scope() as session:
        doc = await session.get(DocumentModel, doc_id)
        doc.display_name = malicious

    async with await _client() as client:
        r = await client.get(f"/api/v1/documents/{doc_id}/content", auth=AUTH)
        assert r.status_code == 200
        disposition = r.headers["content-disposition"]

    assert "\r" not in disposition and "\n" not in disposition
    # Only the two legitimate wrapping quotes around filename="...", never
    # a third one smuggled in from the malicious display_name. Stripping
    # CR/LF/quote character-by-character (rather than rejecting the whole
    # value) is the actual contract here -- the remaining text is inert
    # without a raw CRLF to start a new header line with, which is exactly
    # what's asserted above.
    assert disposition.count('"') == 2


# --------------------------------------------------------------------------
# 8. Voice session failure is not a 202 (app/api/voice.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_session_creation_failure_is_503_not_202(app_db, monkeypatch):
    """A failure to obtain a signed ElevenLabs session used to raise
    ExternalResultUnknownError, which the error handler maps to **202
    Accepted** -- the client was told its request had been accepted for a
    session that had definitively failed to be created. It must surface as
    a provider failure (503), and the Communication row committed before
    the network call must be left FAILED, not stuck at REQUESTED forever."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "test-agent")
    get_settings.cache_clear()

    from app.integrations import elevenlabs as elevenlabs_integration

    async def _raise_connect_error(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(elevenlabs_integration, "create_signed_session", _raise_connect_error)

    try:
        async with await _client() as client:
            r = await client.post(
                "/api/v1/voice/sessions",
                json={"purpose": "INTAKE", "disclosure_accepted": True, "channel": "BROWSER"},
                auth=AUTH,
            )
        assert r.status_code == 503, r.text

        async with session_scope() as session:
            comms = (await session.execute(select(CommunicationModel))).scalars().all()
        assert len(comms) == 1
        assert comms[0].state == "FAILED", "the pre-committed Communication row must be left FAILED, not REQUESTED"
    finally:
        get_settings.cache_clear()


# --------------------------------------------------------------------------
# 9. Archival rows stay out of the feeds (app/domain/services.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archival_rows_excluded_from_upcoming_and_notifications(app_db):
    """load_upcoming_appointments and load_notifications used to carry no
    archive_batch_id filter at all -- a future CONFIRMED appointment or an
    AWAITING_APPROVAL action against a synthetic archival case (imported
    purely to populate charts) showed up in the operator's live "upcoming
    visits" list and bell-icon feed as if it were real, actionable work.
    An equivalent operational case must still appear in both."""

    async def _build(*, archived: bool) -> tuple[str, str]:
        property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
        batch_id = None
        case_id, issue_id, wo_id, action_id, appt_id = uid(), uid(), uid(), uid(), uid()
        async with session_scope() as session:
            if archived:
                batch_id = uid()
                session.add(
                    ArchiveBatchModel(id=batch_id, label=f"feed-test-{batch_id}", generator_version="test", random_seed=1)
                )
                await session.flush()
            session.add(
                RepairCaseModel(
                    id=case_id, case_number=_case_number(), property_id=property_id, tenant_id=tenant_id,
                    status="ACTIVE", version=1, title="Feed exclusion case", risk={}, archive_batch_id=batch_id,
                )
            )
            await session.flush()
            session.add(RepairIssueModel(id=issue_id, case_id=case_id, description="Issue", location="Somewhere"))
            await session.flush()
            session.add(
                WorkOrderModel(
                    id=wo_id, case_id=case_id, issue_id=issue_id, kind="REPAIR", trade="ROOFING",
                    scope="Fix", status="SCHEDULED", contractor_id=roofer_id,
                )
            )
            session.add(
                ActionRecordModel(
                    id=action_id, case_id=case_id, kind="APPLY_TRIAGE", target_id=None,
                    idempotency_key=f"feed-test:{action_id}", payload_hash="hash", proposal={},
                    state=ActionState.AWAITING_APPROVAL.value,
                )
            )
            await session.flush()
            now = datetime.now(timezone.utc)
            session.add(
                AppointmentModel(
                    id=appt_id, case_id=case_id, work_order_id=wo_id, contractor_id=roofer_id,
                    slot_id=f"manual:{appt_id}", start_at=now + timedelta(days=2), end_at=now + timedelta(days=2, hours=3),
                    status="CONFIRMED", connector="MOCK", provider_booking_id=f"feed-test-{appt_id}",
                    action_id=action_id, attempt_number=1, provenance="SIMULATED",
                )
            )
        return case_id, appt_id

    archived_case_id, archived_appt_id = await _build(archived=True)
    operational_case_id, operational_appt_id = await _build(archived=False)

    async with await _client() as client:
        r = await client.get("/api/v1/appointments/upcoming", auth=AUTH)
        assert r.status_code == 200
        appt_ids = {i["appointment_id"] for i in r.json()["items"]}

        r = await client.get("/api/v1/notifications", auth=AUTH)
        assert r.status_code == 200
        notif_case_ids = {i["case_id"] for i in r.json()["items"]}

    assert archived_appt_id not in appt_ids
    assert operational_appt_id in appt_ids
    assert archived_case_id not in notif_case_ids
    assert operational_case_id in notif_case_ids


# --------------------------------------------------------------------------
# 10. The reconciliation sweep gives up (app/orchestration/worker.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconciliation_sweep_gives_up_after_max_attempts(app_db):
    """sweep_stale_live_calls used to enqueue a fresh FETCH_RECORDING job
    every sweep interval forever, for as long as a real call's provider
    lookup kept failing -- the actual production database accumulated
    5,601 such rows from two calls whose lookup failed with a DNS error,
    retried for hours, each attempt "succeeding" as a job so the storm was
    invisible to every failure metric. Pre-inserts RECONCILE_MAX_ATTEMPTS
    prior attempt rows rather than looping in real time: the sweep must
    mark the communication FAILED, append one RECORDING_FAILED event, and
    -- critically -- enqueue no further FETCH_RECORDING job, on this sweep
    or the next."""
    property_id, tenant_id = await _seed_property_tenant()
    case_id = await _seed_bare_case(property_id, tenant_id)
    comm_id = uid()
    started = datetime.now(timezone.utc) - timedelta(seconds=worker.RECONCILE_MIN_CALL_AGE_SECONDS + 30)
    async with session_scope() as session:
        session.add(
            CommunicationModel(
                id=comm_id, case_id=case_id, purpose="FOLLOW_UP", direction="OUTBOUND", provider="ELEVENLABS",
                provider_conversation_id=f"conv-{comm_id}", correlation_token_hash=uid(), state="ACTIVE",
                started_at=started, provenance="LIVE",
            )
        )
        await session.flush()
        for i in range(worker.RECONCILE_MAX_ATTEMPTS):
            session.add(
                JobModel(
                    id=uid(), case_id=case_id, kind="FETCH_RECORDING",
                    dedupe_key=f"recording:sweep:{comm_id}:{1_000_000 + i}",
                    payload={"communication_id": comm_id}, status="DONE",
                )
            )

    async def _job_count() -> int:
        async with session_scope() as session:
            return (
                await session.execute(
                    select(func.count()).select_from(JobModel).where(JobModel.kind == "FETCH_RECORDING", JobModel.case_id == case_id)
                )
            ).scalar_one()

    await worker.sweep_stale_live_calls()

    async with session_scope() as session:
        comm = await session.get(CommunicationModel, comm_id)
        events = (
            await session.execute(
                select(CaseEventModel).where(CaseEventModel.case_id == case_id, CaseEventModel.type == "RECORDING_FAILED")
            )
        ).scalars().all()
    assert comm.state == "FAILED"
    assert comm.recording.get("status") == "FAILED"
    assert len(events) == 1
    assert await _job_count() == worker.RECONCILE_MAX_ATTEMPTS, "no new FETCH_RECORDING job may be enqueued once abandoned"

    # A second sweep must be a pure no-op for this communication.
    await worker.sweep_stale_live_calls()
    async with session_scope() as session:
        comm_again = await session.get(CommunicationModel, comm_id)
        events_again = (
            await session.execute(
                select(CaseEventModel).where(CaseEventModel.case_id == case_id, CaseEventModel.type == "RECORDING_FAILED")
            )
        ).scalars().all()
    assert comm_again.state == "FAILED"
    assert len(events_again) == 1, "the abandonment event must not be appended twice"
    assert await _job_count() == worker.RECONCILE_MAX_ATTEMPTS


# --------------------------------------------------------------------------
# 11. The worker loop survives a failing tick (app/orchestration/worker.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_loop_survives_a_failing_tick(app_db):
    """run_worker_loop's claim query and sweep call used to sit outside any
    try/except -- a single SQLite lock contention or dedupe-race
    IntegrityError killed the asyncio.create_task() loop outright, silently
    and totally: every job kind simply stopped, with nothing visible on any
    case and no restart. The loop must catch a failing tick, back off, and
    keep processing subsequent jobs rather than dying."""
    calls: list[int] = []

    async def fake_process_one_job(coordinator, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("simulated tick failure")
        if len(calls) == 2:
            return True
        return False

    import app.orchestration.worker as worker_module

    original = worker_module.process_one_job
    worker_module.process_one_job = fake_process_one_job
    try:
        stop_event = asyncio.Event()
        task = asyncio.create_task(
            worker_module.run_worker_loop(_NeverCalledCoordinator(), stop_event=stop_event, poll_interval=0.02)
        )
        for _ in range(50):
            if len(calls) >= 3:
                break
            await asyncio.sleep(0.05)
        stop_event.set()
        await asyncio.wait_for(task, timeout=5)
    finally:
        worker_module.process_one_job = original

    assert len(calls) >= 3, "the loop must keep calling process_one_job after a tick raised"
    assert not task.cancelled()
    assert task.exception() is None, "the loop task itself must never die with an exception"


# --------------------------------------------------------------------------
# 12. An external action never strands at RUNNING
#     (app/orchestration/executor.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_external_action_never_strands_at_running(app_db, monkeypatch):
    """execute_action commits the ActionRecord as RUNNING, then calls the
    booking connector with no transaction open. If that call raises (a real
    network failure raises; it doesn't politely return a BookingOutcome),
    the exception propagates straight out of execute_action with nothing
    ever moving the row on from RUNNING -- indistinguishable forever from a
    booking that is still genuinely in flight, with no reconciliation
    path. It must land at UNKNOWN, carry reconciliation_required, and
    append an ACTION_UNKNOWN event, exactly like the already-handled
    PENDING/UNKNOWN BookingOutcome case."""
    from tests.test_fixi_ui_support import _intake, _triage_builder

    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    case_id = await _intake(property_id, tenant_id, "Water ingress near the roofline.")
    await _broad_tenant_window(case_id, tenant_id)

    coordinator = FixtureCoordinator()
    coordinator.queue(_triage_builder("Water ingress near the roofline."))
    coordinator.queue(_schedule_builder(Trade.ROOFING, roofer_id, "REPAIR"))

    async def _raise_mid_flight(*args, **kwargs):
        raise RuntimeError("simulated network failure mid-booking")

    monkeypatch.setattr(mock_booking_connector, "book", _raise_mid_flight)

    await worker.drain_due_jobs(coordinator, raise_on_error=False)

    async with session_scope() as session:
        action = (
            await session.execute(
                select(ActionRecordModel).where(ActionRecordModel.case_id == case_id, ActionRecordModel.kind == "SCHEDULE_VISIT")
            )
        ).scalars().first()
        assert action is not None, "expected a SCHEDULE_VISIT action to have been admitted"
        events = (
            await session.execute(
                select(CaseEventModel).where(CaseEventModel.case_id == case_id, CaseEventModel.type == "ACTION_UNKNOWN")
            )
        ).scalars().all()

    assert action.state == ActionState.UNKNOWN.value, (
        f"action ended at {action.state!r}, expected UNKNOWN -- stranded at RUNNING with no "
        "reconciliation path is the exact defect this test guards"
    )
    result = CommandResult.model_validate(action.result) if action.result else None
    assert result is not None and result.error is not None and result.error.reconciliation_required is True
    assert len(events) == 1, "expected exactly one ACTION_UNKNOWN event"


# --------------------------------------------------------------------------
# 13. The case-transition graph is enforced (app/domain/transitions.py)
# --------------------------------------------------------------------------


def test_case_transition_graph_is_enforced():
    """assert_case_transition is the sole guard against illegal case-status
    transitions. Mutation-tested by disabling it (reduced to a no-op): the
    entire suite still passed with nothing catching an illegal transition
    like CANCELLED -> ACTIVE. Table-driven over every (current, target)
    pair in CaseStatus, not a handful of hand-picked ones -- the property
    being protected is that the guard *exists* at all, not that one
    particular pair behaves. No app_db/DB needed: this is a pure function
    over the in-memory _CASE_EDGES graph."""
    from app.domain.errors import PolicyRejectedError
    from app.domain.transitions import _CASE_EDGES, assert_case_transition
    from app.schemas import CaseStatus

    for current in CaseStatus:
        for target in CaseStatus:
            if current == target:
                assert_case_transition(current, target)  # self-loop: always a permitted no-op
                continue
            if target in _CASE_EDGES.get(current, set()):
                assert_case_transition(current, target)  # legal edge: must not raise
            else:
                with pytest.raises(PolicyRejectedError):
                    assert_case_transition(current, target)  # illegal edge: must raise


# --------------------------------------------------------------------------
# 14. decide_approval rejects a stale expected_case_version
#     (app/orchestration/executor.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decide_approval_rejects_stale_expected_version(app_db):
    """decide_approval's `case.version != decision.expected_case_version`
    check is the guard that stops two operators overwriting each other on
    a spend/scheduling decision -- an operator approving against a version
    they saw before someone else already changed the case. Mutation-tested
    by disabling this check: the entire suite still passed. Approving with
    an expected_case_version one behind the case's real version must 409
    (StaleVersionError), leave the action AWAITING_APPROVAL, and append no
    APPROVAL_DECIDED event."""
    property_id, tenant_id = await _seed_property_tenant()
    case_id = await _seed_bare_case(property_id, tenant_id, status="ACTIVE")
    action_id = uid()
    async with session_scope() as session:
        session.add(
            ActionRecordModel(
                id=action_id, case_id=case_id, kind="APPLY_TRIAGE", target_id=None,
                idempotency_key=f"stale:{action_id}", payload_hash="fixed-hash", proposal={},
                state=ActionState.AWAITING_APPROVAL.value,
            )
        )
        # Simulate the case having moved on since the operator loaded it
        # (e.g. a concurrent edit elsewhere) -- the DB's real version is
        # now ahead of what the approval body claims to have seen.
        case = await session.get(RepairCaseModel, case_id)
        case.version = 2

    async with await _client() as client:
        r = await client.post(
            f"/api/v1/actions/{action_id}/approval",
            json={
                "action_id": action_id, "expected_case_version": 1, "approve": True,
                "reason": "approve", "action_payload_hash": "fixed-hash",
            },
            auth=AUTH,
        )
    assert r.status_code == 409, r.text

    async with session_scope() as session:
        action = await session.get(ActionRecordModel, action_id)
        events = (
            await session.execute(
                select(CaseEventModel).where(CaseEventModel.case_id == case_id, CaseEventModel.type == "APPROVAL_DECIDED")
            )
        ).scalars().all()
    assert action.state == ActionState.AWAITING_APPROVAL.value, "a rejected-as-stale approval must not move the action"
    assert events == [], "a rejected-as-stale approval must append no APPROVAL_DECIDED event"


# --------------------------------------------------------------------------
# 15. Archival cases are excluded from GET /cases by default
#     (app/api/cases.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_list_excludes_archival_by_default(app_db):
    """Every sibling list endpoint (/properties, /contractors, /tenants)
    already has an archival-exclusion test; GET /api/v1/cases -- the
    most-used endpoint in the whole app -- did not. An archival case must
    be absent from the default list, present when include_archived=true is
    passed, and carry is_archived: true when it is returned."""
    property_id, tenant_id = await _seed_property_tenant()
    batch_id = uid()
    async with session_scope() as session:
        session.add(
            ArchiveBatchModel(id=batch_id, label=f"list-test-{batch_id}", generator_version="test", random_seed=1)
        )
    archived_case_id = await _seed_bare_case(property_id, tenant_id, archive_batch_id=batch_id)
    operational_case_id = await _seed_bare_case(property_id, tenant_id)

    async with await _client() as client:
        r = await client.get("/api/v1/cases", auth=AUTH)
        assert r.status_code == 200
        default_ids = {i["id"] for i in r.json()["items"]}

        r = await client.get("/api/v1/cases", params={"include_archived": "true"}, auth=AUTH)
        assert r.status_code == 200
        by_id = {i["id"]: i for i in r.json()["items"]}

    assert archived_case_id not in default_ids, "an archival case must not appear in the default case list"
    assert operational_case_id in default_ids

    assert archived_case_id in by_id, "include_archived=true must still surface the archival case"
    assert by_id[archived_case_id]["is_archived"] is True
    assert by_id[operational_case_id]["is_archived"] is False


# --------------------------------------------------------------------------
# 16. The SPA deep-link fallback stands alone, and never swallows a 404
#     from the API (app/main.py)
# --------------------------------------------------------------------------


def _spa_app(tmp_path):
    """A minimal app mounting SpaStaticFiles over a dist dir that has
    index.html and NO 404.html -- the shape `npm run build` produces
    before flatten-dist.mjs copies the extra file."""
    from fastapi import FastAPI

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>shell</title>", encoding="utf-8")
    (dist / "assets" / "real.js").write_text("export const x = 1;\n", encoding="utf-8")

    probe = FastAPI()

    @probe.get("/api/v1/real")
    async def _real() -> dict:
        return {"ok": True}

    probe.mount("/", main_module.SpaStaticFiles(directory=str(dist), html=True), name="frontend")
    return probe


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/maintenance", "/insights", "/properties/abc/history", "/tenants/xyz", "/deep/link/never/built"],
)
async def test_deep_link_falls_back_without_a_404_html_on_disk(tmp_path, path):
    """The fallback used to depend on dist/404.html existing without
    saying so. Starlette's html=True *returns* 404.html when present but
    *raises* HTTPException(404) when absent, and only the returned form
    was handled -- so deleting the copy flatten-dist.mjs makes (whose own
    comment called it redundant) would 404 every deep-linked reload."""
    transport = ASGITransport(app=_spa_app(tmp_path))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(path)
    assert r.status_code == 200, f"{path} must serve the SPA shell with no 404.html on disk"
    assert "<title>shell</title>" in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/api/v1/nope", "/api/v1/cases/not-a-case/bogus", "/webhooks/nope", "/integrations/nope", "/assets/missing.js"],
)
async def test_missing_api_path_is_404_not_the_spa_shell(tmp_path, path):
    """Far worse than a broken deep link: a genuine 404 answered 200 with
    an HTML body, so a client parses markup as JSON and sees success.
    That is exactly what happened on Windows, because Starlette hands
    get_response a path already through os.path.normpath -- backslash-
    separated on Windows, which no startswith("api/") test matches."""
    transport = ASGITransport(app=_spa_app(tmp_path))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(path)
    assert r.status_code == 404, f"{path} must report itself missing, not return the SPA shell"
    assert "<title>shell</title>" not in r.text


def test_passthrough_prefixes_survive_windows_path_separators(tmp_path):
    """Platform-independent guard for the separator bug above: on POSIX
    the end-to-end test cannot reproduce it, because normpath leaves the
    forward slashes alone. Assert the classifier directly."""
    spa = main_module.SpaStaticFiles(directory=str(tmp_path), html=True)
    windows_normalised = ("api\\v1\\nope", "webhooks\\x", "integrations\\x", "assets\\missing.js")
    for path in windows_normalised + ("api/v1/nope", "/api/v1/nope"):
        assert spa._is_app_route(path) is False, f"{path!r} must be left to report its own 404"
    for path in ("maintenance", "properties\\abc\\history", "/insights", "apixel", "assetsy/thing"):
        assert spa._is_app_route(path) is True, f"{path!r} must fall back to the SPA shell"


@pytest.mark.asyncio
async def test_real_routes_still_win_over_the_fallback(tmp_path):
    """The fallback must not shadow anything that genuinely exists."""
    transport = ASGITransport(app=_spa_app(tmp_path))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        api = await client.get("/api/v1/real")
        asset = await client.get("/assets/real.js")
    assert api.status_code == 200 and api.json() == {"ok": True}
    assert asset.status_code == 200 and "export const x" in asset.text
