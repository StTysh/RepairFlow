"""Four independent backend correctness fixes, one test class each:

1. dispatcher.run_coordinate must not strand an OrchestrationRunModel row
   at RUNNING when admit_proposal raises something that is neither a
   StaleVersionError nor a DomainError (app/orchestration/dispatcher.py).
2. services.enqueue_job must survive a dedupe_key race (two concurrent
   callers both passing its existence check before either flushes) without
   poisoning the caller's ambient transaction (app/domain/services.py).
3. services.escalate_to_human must reject escalating a CANCELLED case
   instead of silently writing a phantom escalation onto it
   (app/domain/services.py).
4. app.legacy_demo_purge must count and delete NoteModel/DocumentModel rows
   attached to a scripted demo case, and unlink a document's file on disk
   (app/legacy_demo_purge.py).
5. GET /api/v1/contractors must paginate (LIMIT/OFFSET) and filter by trade
   in SQL, not by loading the whole table into Python
   (app/api/contractors.py).

Uses the same app_db/session_scope conventions and _seed_reference_data/uid
helpers as the rest of the suite (tests/test_hero_path.py,
tests/test_reliability_matrix.py).
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select

import app.db as db_module
import app.main as main_module
from app.config import get_settings
from app.db import session_scope
from app.domain import services
from app.domain.errors import PolicyRejectedError
from app.domain.services import ActorContext
from app.legacy_demo_purge import purge, scripted_case_ids
from app.models import (
    CommunicationModel,
    ContractorModel,
    DocumentModel,
    JobModel,
    NoteModel,
    OrchestrationRunModel,
    RepairCaseModel,
    new_uuid,
)
from app.orchestration import dispatcher
from app.orchestration.dispatcher import FixtureCoordinator
from app.schemas import (
    ActionProposal,
    ApplyTriage,
    CaseStatus,
    Escalate,
    IntakeSubmission,
    JobKind,
    JobStatus,
    RecordSubject,
    RiskAssessment,
    Trade,
)

from tests.test_hero_path import _seed_reference_data, uid

AUTH = ("operator", "repairflow-demo")


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=main_module.app), base_url="http://test")


async def _submit_case(property_id: str, tenant_id: str, description: str = "Roof leak.") -> tuple[str, str]:
    """Creates a real case via submit_intake and returns (case_id, trigger_event_id)."""
    comm_id = uid()
    async with session_scope() as session:
        session.add(
            CommunicationModel(
                id=comm_id, purpose="INTAKE", direction="BROWSER",
                correlation_token_hash=uid(), state="ACTIVE", provenance="FIXTURE",
            )
        )
    async with session_scope() as session:
        case_id, intake_result = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description=description, location="Attic", source_text="src",
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )
    return case_id, str(intake_result.event_ids[0])


# --------------------------------------------------------------------------
# 1. OrchestrationRun must not strand at RUNNING on an unexpected exception
#    (app/orchestration/dispatcher.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_coordinate_marks_run_failed_not_stuck_running_on_unexpected_error(app_db, monkeypatch):
    property_id, tenant_id, _roofer_id, _scaffolder_id = await _seed_reference_data()
    case_id, trigger_event_id = await _submit_case(property_id, tenant_id)

    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        case_version = case.version

    async def boom(*_args, **_kwargs):
        raise RuntimeError("simulated DB error inside admit_proposal")

    # admit_proposal is imported locally inside run_coordinate's Phase C
    # (`from app.orchestration.executor import admit_proposal`), so
    # patching the executor module's attribute is picked up at call time.
    monkeypatch.setattr("app.orchestration.executor.admit_proposal", boom)

    proposal = ActionProposal(
        case_id=case_id, expected_case_version=case_version, trigger_event_id=trigger_event_id,
        decision_summary="test", evidence_refs=[],
        action=ApplyTriage(
            risk=RiskAssessment(urgency="ROUTINE", gas="NO", fire="NO", water_near_electrics="NO", structural_danger="NO", uncontrolled_flood="NO", vulnerability_concern="NO"),
            issue_description="Roof leak.", suggested_trade=Trade.ROOFING, scope="Repair roof leak.",
        ),
    )
    coordinator = FixtureCoordinator([proposal])

    with pytest.raises(RuntimeError, match="simulated DB error"):
        await dispatcher.run_coordinate(case_id=case_id, trigger_event_id=trigger_event_id, coordinator=coordinator)

    async with session_scope() as session:
        runs = (
            await session.execute(select(OrchestrationRunModel).where(OrchestrationRunModel.case_id == case_id))
        ).scalars().all()
        assert len(runs) == 1
        assert runs[0].state != "RUNNING", "an unexpected exception must not leave the run stranded at RUNNING"
        assert runs[0].state == "FAILED"
        assert runs[0].error_code == "RuntimeError"
        assert runs[0].finished_at is not None


# --------------------------------------------------------------------------
# 2. enqueue_job must survive a dedupe_key race without poisoning the
#    caller's ambient transaction (app/domain/services.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_job_toctou_race_backs_off_without_poisoning_the_session(app_db):
    """Reproduces the SELECT-then-INSERT race described in the task:
    a second caller computing the same dedupe_key passes enqueue_job's
    existence check before the first caller's row has reached the
    database. `session.add()` without a flush is invisible to a later
    `session.execute(select(...))` on the same session (autoflush=False,
    db.py) -- that gap is exactly the TOCTOU window, reproduced here
    deterministically on a single session instead of via genuinely
    concurrent connections."""
    dedupe_key = f"race:{uid()}"

    async with session_scope() as session:
        rival = JobModel(
            id=new_uuid(), case_id=None, kind=JobKind.FOLLOW_UP, dedupe_key=dedupe_key,
            payload={}, run_at=services.utcnow(), status=JobStatus.PENDING,
        )
        session.add(rival)
        rival_id = rival.id

        result = await services.enqueue_job(
            session, case_id=None, kind=JobKind.FOLLOW_UP, dedupe_key=dedupe_key, payload={},
        )
        assert result is None, "the losing enqueue_job call must back off, not raise"

        # The caller's ambient transaction must still be usable after the
        # race -- an unhandled IntegrityError from the losing flush would
        # otherwise leave the session unable to run further statements,
        # including this unrelated second enqueue_job call and the
        # eventual commit on session_scope exit.
        other_key = f"other:{uid()}"
        other = await services.enqueue_job(
            session, case_id=None, kind=JobKind.FOLLOW_UP, dedupe_key=other_key, payload={},
        )
        assert other is not None

    async with session_scope() as session:
        jobs = (await session.execute(select(JobModel).where(JobModel.dedupe_key == dedupe_key))).scalars().all()
        assert len(jobs) == 1, "exactly one job for the contested key must survive"
        assert jobs[0].id == rival_id

        other_jobs = (await session.execute(select(JobModel).where(JobModel.dedupe_key == other_key))).scalars().all()
        assert len(other_jobs) == 1, "an unrelated enqueue_job after the race must still commit"


# --------------------------------------------------------------------------
# 3. escalate_to_human must reject a CANCELLED case, not silently mutate it
#    (app/domain/services.py)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalate_to_human_rejects_a_cancelled_case(app_db):
    property_id, tenant_id, _roofer_id, _scaffolder_id = await _seed_reference_data()
    case_id, trigger_event_id = await _submit_case(property_id, tenant_id)

    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        case.status = CaseStatus.CANCELLED
        version_before = case.version
        reason_before = case.escalation_reason

    async with session_scope() as session:
        with pytest.raises(PolicyRejectedError, match="cannot be escalated"):
            await services.escalate_to_human(
                session, case_id=case_id,
                action=Escalate(reason_code="HAZARD", operator_message="late hazard report", evidence_refs=[]),
                trigger_event_id=trigger_event_id, actor=ActorContext("SYSTEM", "test", trigger_event_id),
            )

    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        assert case.status == CaseStatus.CANCELLED, "status must stay CANCELLED"
        assert case.version == version_before, "a rejected escalation must not bump the case version"
        assert case.escalation_reason == reason_before, "a rejected escalation must not write a reason"

        events = (
            await session.execute(
                select(dispatcher.CaseEventModel).where(
                    dispatcher.CaseEventModel.case_id == case_id, dispatcher.CaseEventModel.type == "CASE_ESCALATED"
                )
            )
        ).scalars().all()
        assert events == [], "no CASE_ESCALATED event may be recorded against a rejected escalation"


# --------------------------------------------------------------------------
# 4. legacy_demo_purge must count and remove notes/documents on a scripted
#    demo case, including unlinking a document's file on disk
#    (app/legacy_demo_purge.py)
# --------------------------------------------------------------------------


@pytest.fixture
def documents_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "documents"))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_legacy_demo_purge_counts_and_removes_notes_and_documents(app_db, documents_dir):
    property_id, tenant_id, _roofer_id, _scaffolder_id = await _seed_reference_data()
    demo_case_id = scripted_case_ids()[0]

    settings = get_settings()
    settings.documents_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uid()}.txt"
    doc_path = settings.documents_dir / stored_name
    doc_path.write_bytes(b"legacy demo document contents")

    async with session_scope() as session:
        session.add(
            RepairCaseModel(
                id=demo_case_id, case_number=999001, property_id=property_id, tenant_id=tenant_id,
                status=CaseStatus.RESOLVED, version=1, title="Legacy demo case", risk={},
                owner_operator_id="operator",
            )
        )
        session.add(
            NoteModel(id=uid(), subject_type=RecordSubject.CASE, subject_id=demo_case_id, body="legacy note", author="demo")
        )
        session.add(
            DocumentModel(
                id=uid(), subject_type=RecordSubject.CASE, subject_id=demo_case_id, display_name="legacy.txt",
                stored_name=stored_name, content_type="text/plain", size_bytes=doc_path.stat().st_size,
                uploaded_by="demo",
            )
        )

    dry_run_counts = await purge(apply=False)
    assert dry_run_counts["cases_found"] == 1
    assert dry_run_counts["notes"] == 1, "a --dry-run must count the note, not undercount it"
    assert dry_run_counts["documents"] == 1, "a --dry-run must count the document, not undercount it"

    # dry-run must not have deleted anything
    async with session_scope() as session:
        assert (await session.execute(select(NoteModel).where(NoteModel.subject_id == demo_case_id))).scalars().first() is not None
        assert (await session.execute(select(DocumentModel).where(DocumentModel.subject_id == demo_case_id))).scalars().first() is not None
    assert doc_path.exists(), "dry-run must not touch the file on disk"

    apply_counts = await purge(apply=True)
    assert apply_counts["notes"] == 1
    assert apply_counts["documents"] == 1

    async with session_scope() as session:
        remaining_notes = (await session.execute(select(NoteModel).where(NoteModel.subject_id == demo_case_id))).scalars().all()
        remaining_docs = (await session.execute(select(DocumentModel).where(DocumentModel.subject_id == demo_case_id))).scalars().all()
        assert remaining_notes == [], "--apply must delete the note"
        assert remaining_docs == [], "--apply must delete the document row"
    assert not doc_path.exists(), "--apply must unlink the document's file on disk"


# --------------------------------------------------------------------------
# 5. GET /api/v1/contractors must paginate and filter by trade in SQL, not
#    in Python (app/api/contractors.py)
# --------------------------------------------------------------------------


async def _seed_contractor(*, trade: str, name: str) -> str:
    contractor_id = str(uuid.uuid4())
    async with session_scope() as session:
        session.add(
            ContractorModel(
                id=contractor_id, display_name=name, trades=[trade], service_postcodes=["BS1"],
                approval_status="APPROVED", connector="MOCK", provenance="SIMULATED",
            )
        )
    return contractor_id


@pytest.mark.asyncio
async def test_contractor_list_paginates_and_filters_by_trade_in_sql(app_db):
    """list_contractors used to `.scalars().all()` the whole contractors
    table with no SQL LIMIT, then apply the trade filter and slice
    `rows[offset:offset+limit]` in Python (api/contractors.py ~178-208) --
    unlike properties.py/tenants.py, which push LIMIT/OFFSET and a
    separate COUNT into SQL. For a small table both approaches return the
    same page, so a plain pagination assertion cannot tell them apart;
    this instruments the actual SQL sent to SQLite and asserts a LIMIT
    clause reaches the database for the contractor listing query, which
    only the fixed code emits."""
    for i in range(5):
        await _seed_contractor(trade="ROOFING", name=f"Roofer {i}")
    await _seed_contractor(trade="PLUMBING", name="Plumber Prime")

    engine = db_module.get_engine()
    captured: list[str] = []

    def _capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        captured.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    try:
        async with await _client() as client:
            r = await client.get(
                "/api/v1/contractors", params={"trade": "ROOFING", "limit": 2, "offset": 0}, auth=AUTH,
            )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _capture)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 5, "trade filter must exclude the PLUMBING contractor"
    assert len(body["items"]) == 2
    assert body["has_more"] is True

    listing_statements = [
        s for s in captured if "FROM contractors" in s and "count(" not in s.lower()
    ]
    assert listing_statements, f"no contractor listing SELECT observed: {captured}"
    assert any("LIMIT" in s.upper() for s in listing_statements), (
        "the contractor listing query never reached the database with a SQL LIMIT clause "
        f"-- pagination is still happening in Python: {listing_statements}"
    )
