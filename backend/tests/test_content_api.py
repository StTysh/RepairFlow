"""Tests for the content-API phase: documents, notes, costs, messaging
threads (app/api/documents.py, notes.py, costs.py, messaging.py).

Built as a self-contained ASGI app hosting only these four routers plus the
shared error handlers -- app.main.app does not (yet) wire them in; that is
the root agent's job (see app/api/NEEDS_FROM_ROOT_content.md). Style
follows tests/test_api.py: real ASGI requests via httpx, and the shared
`app_db` fixture for an isolated file-backed SQLite database per test.
`content_dirs` additionally redirects settings.documents_dir at a tmp_path
so uploaded files never touch a developer's real data/documents.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api import costs, documents, messaging, notes
from app.api.errors import register_error_handlers
from app.config import get_settings
from app.db import session_scope
from app.models import (
    ArchiveBatchModel,
    CostEntryModel,
    MessageModel,
    PropertyModel,
    RepairCaseModel,
    RepairIssueModel,
    TenantModel,
    WorkOrderModel,
    new_uuid,
    utcnow,
)
from app.schemas import MessageSenderType, Trade, WorkOrderKind, WorkOrderStatus

AUTH = ("operator", "repairflow-demo")


def _build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(documents.router)
    app.include_router(notes.router)
    app.include_router(costs.router)
    app.include_router(messaging.router)
    return app


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test")


def _case_number() -> int:
    # uq_case_number is a real UNIQUE constraint -- a random int keeps
    # parallel/successive test cases from colliding.
    return uuid.uuid4().int % 900_000 + 1


async def _seed_case() -> tuple[str, str, str, str]:
    """A property + tenant + case (+ one READY repair work order), for
    tests that need a real case to file notes/documents/costs/messages
    against. Returns (property_id, tenant_id, case_id, work_order_id)."""
    property_id, tenant_id, case_id, issue_id, work_order_id = (
        new_uuid(), new_uuid(), new_uuid(), new_uuid(), new_uuid()
    )
    async with session_scope() as session:
        session.add(
            PropertyModel(
                id=property_id, address_line="1 Test St", postcode="BS1 1AA",
                landlord_reference="LL-1", roof_responsibility="LANDLORD",
            )
        )
        session.add(
            TenantModel(
                id=tenant_id, property_id=property_id, display_name="Jordan Hale",
                preferred_channel="VOICE", contact_allowed=True,
            )
        )
        # These models declare raw FK columns with no relationship(), so
        # SQLAlchemy's unit of work has no dependency graph to sort the
        # INSERTs by and will happily emit the case before its property.
        # PRAGMA foreign_keys=ON is on, so that is a hard IntegrityError.
        # One flush per FK boundary is what keeps the order honest.
        await session.flush()
        session.add(
            RepairCaseModel(
                id=case_id, case_number=_case_number(), property_id=property_id, tenant_id=tenant_id,
                title="Leaking roof", risk={},
            )
        )
        await session.flush()
        session.add(RepairIssueModel(id=issue_id, case_id=case_id, description="Water ingress", location="Bedroom"))
        await session.flush()
        session.add(
            WorkOrderModel(
                id=work_order_id, case_id=case_id, issue_id=issue_id, kind=WorkOrderKind.REPAIR,
                trade=Trade.ROOFING, scope="Fix roof", status=WorkOrderStatus.READY,
            )
        )
    return property_id, tenant_id, case_id, work_order_id


@pytest_asyncio.fixture
async def content_dirs(tmp_path, monkeypatch):
    """Redirects settings.documents_dir at an isolated tmp_path, following
    the app_db fixture's pattern of env-var override + get_settings cache
    clear (see tests/conftest.py)."""
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "documents"))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_document_upload_list_fetch_delete_round_trip(app_db, content_dirs):
    _, _, case_id, _ = await _seed_case()
    documents_dir = get_settings().documents_dir

    async with await _client() as client:
        r = await client.post(
            "/api/v1/documents",
            data={"subject_type": "CASE", "subject_id": case_id, "description": "roof photo"},
            files={"file": ("photo.txt", b"hello world", "text/plain")},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["display_name"] == "photo.txt"
        assert doc["size_bytes"] == len(b"hello world")
        assert doc["content_type"] == "text/plain"
        assert doc["is_archived"] is False
        document_id = doc["id"]

        # exactly one file actually landed on disk
        on_disk = list(documents_dir.iterdir())
        assert len(on_disk) == 1

        r = await client.get("/api/v1/documents", params={"subject_type": "CASE", "subject_id": case_id}, auth=AUTH)
        assert r.status_code == 200
        assert [i["id"] for i in r.json()["items"]] == [document_id]

        r = await client.get(f"/api/v1/documents/{document_id}/content", auth=AUTH)
        assert r.status_code == 200
        assert r.content == b"hello world"
        assert "attachment" in r.headers["content-disposition"]

        r = await client.delete(f"/api/v1/documents/{document_id}", auth=AUTH)
        assert r.status_code == 204

        assert list(documents_dir.iterdir()) == []
        r = await client.get(f"/api/v1/documents/{document_id}", auth=AUTH)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_document_upload_rejects_unknown_subject(app_db, content_dirs):
    async with await _client() as client:
        r = await client.post(
            "/api/v1/documents",
            data={"subject_type": "CASE", "subject_id": new_uuid()},
            files={"file": ("a.txt", b"x", "text/plain")},
            auth=AUTH,
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_document_oversize_rejected_and_leaves_no_file(app_db, content_dirs, monkeypatch):
    _, _, case_id, _ = await _seed_case()
    monkeypatch.setenv("MAX_DOCUMENT_BYTES", "10")
    get_settings.cache_clear()
    documents_dir = get_settings().documents_dir

    async with await _client() as client:
        r = await client.post(
            "/api/v1/documents",
            data={"subject_type": "CASE", "subject_id": case_id},
            files={"file": ("big.bin", b"x" * 11, "application/octet-stream")},
            auth=AUTH,
        )
        assert r.status_code == 413, r.text
    assert list(documents_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_document_empty_file_rejected(app_db, content_dirs):
    _, _, case_id, _ = await _seed_case()
    async with await _client() as client:
        r = await client.post(
            "/api/v1/documents",
            data={"subject_type": "CASE", "subject_id": case_id},
            files={"file": ("empty.txt", b"", "text/plain")},
            auth=AUTH,
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_document_traversal_filename_does_not_escape_documents_dir(app_db, content_dirs):
    _, _, case_id, _ = await _seed_case()
    documents_dir = get_settings().documents_dir

    async with await _client() as client:
        r = await client.post(
            "/api/v1/documents",
            data={"subject_type": "CASE", "subject_id": case_id},
            files={"file": ("../../../etc/passwd", b"payload", "text/plain")},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text

        r2 = await client.post(
            "/api/v1/documents",
            data={"subject_type": "CASE", "subject_id": case_id},
            files={"file": ("..\\..\\windows\\win.ini", b"payload2", "text/plain")},
            auth=AUTH,
        )
        assert r2.status_code == 201, r2.text

    # Both files landed directly inside documents_dir, nowhere else -- and
    # nothing escaped upward (the parent of documents_dir gained no files).
    on_disk = list(documents_dir.iterdir())
    assert len(on_disk) == 2
    for path in on_disk:
        assert path.parent == documents_dir
        assert "/" not in path.name and "\\" not in path.name
    parent_files_before_and_after = {p.name for p in documents_dir.parent.iterdir() if p.is_file()}
    assert "passwd" not in parent_files_before_and_after
    assert "win.ini" not in parent_files_before_and_after


# --------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_note_crud(app_db):
    _, _, case_id, _ = await _seed_case()
    async with await _client() as client:
        r = await client.post(
            "/api/v1/notes", json={"subject_type": "CASE", "subject_id": case_id, "body": "Called tenant, no answer."},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        note = r.json()
        assert note["author"] == "operator"
        assert note["is_archived"] is False
        note_id = note["id"]

        r = await client.get("/api/v1/notes", params={"subject_type": "CASE", "subject_id": case_id}, auth=AUTH)
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

        r = await client.patch(f"/api/v1/notes/{note_id}", json={"body": "Called tenant, left voicemail."}, auth=AUTH)
        assert r.status_code == 200
        assert r.json()["body"] == "Called tenant, left voicemail."

        r = await client.delete(f"/api/v1/notes/{note_id}", auth=AUTH)
        assert r.status_code == 204

        r = await client.get("/api/v1/notes", params={"subject_type": "CASE", "subject_id": case_id}, auth=AUTH)
        assert r.json()["items"] == []


@pytest.mark.asyncio
async def test_note_blank_body_rejected(app_db):
    _, _, case_id, _ = await _seed_case()
    async with await _client() as client:
        r = await client.post(
            "/api/v1/notes", json={"subject_type": "CASE", "subject_id": case_id, "body": "   "}, auth=AUTH,
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_note_unknown_subject_rejected(app_db):
    async with await _client() as client:
        r = await client.post(
            "/api/v1/notes", json={"subject_type": "CASE", "subject_id": new_uuid(), "body": "hi"}, auth=AUTH,
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_note_archival_refuses_edit_and_delete(app_db):
    _, _, case_id, _ = await _seed_case()
    async with session_scope() as session:
        batch = ArchiveBatchModel(id=new_uuid(), label=f"batch-{new_uuid()}", generator_version="1", random_seed=1)
        session.add(batch)
        await session.flush()
        from app.models import NoteModel

        note = NoteModel(
            id=new_uuid(), subject_type="CASE", subject_id=case_id, body="archival note",
            author="importer", created_at=utcnow(), updated_at=utcnow(), archive_batch_id=batch.id,
        )
        session.add(note)
        await session.flush()
        note_id = note.id

    async with await _client() as client:
        r = await client.patch(f"/api/v1/notes/{note_id}", json={"body": "edited"}, auth=AUTH)
        assert r.status_code == 409
        r = await client.delete(f"/api/v1/notes/{note_id}", auth=AUTH)
        assert r.status_code == 409


# --------------------------------------------------------------------------
# Costs
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_crud_and_totals_arithmetic(app_db):
    _, _, case_id, work_order_id = await _seed_case()
    async with await _client() as client:
        # work-order-scoped QUOTE + INVOICE (invoice supersedes quote for committed)
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={
                "work_order_id": work_order_id, "kind": "QUOTE", "amount_pence": 50000,
                "description": "Roofer quote", "incurred_at": utcnow().isoformat(),
            },
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={
                "work_order_id": work_order_id, "kind": "INVOICE", "amount_pence": 55000,
                "description": "Roofer invoice", "incurred_at": utcnow().isoformat(),
            },
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        cost_to_edit_id = r.json()["id"]

        # case-level (no work order) QUOTE with no matching invoice
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={"kind": "QUOTE", "amount_pence": 20000, "description": "Skip hire estimate", "incurred_at": utcnow().isoformat()},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text

        # signed adjustment
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={"kind": "ADJUSTMENT", "amount_pence": -1000, "description": "Goodwill discount", "incurred_at": utcnow().isoformat()},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text

        r = await client.get(f"/api/v1/cases/{case_id}/costs", auth=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 4
        totals = body["totals"]
        # quoted = 50000 (wo) + 20000 (case-level) = 70000
        assert totals["quoted_pence"] == 70000
        # invoiced = 55000
        assert totals["invoiced_pence"] == 55000
        # adjustments = -1000
        assert totals["adjustments_pence"] == -1000
        # net = invoiced + adjustments = 54000
        assert totals["net_pence"] == 54000
        # committed: wo-group has an invoice -> 55000; case-level group has
        # no invoice -> its quote, 20000. total = 75000.
        assert totals["committed_pence"] == 75000

        # PATCH the invoice amount and re-check totals shift correctly
        r = await client.patch(f"/api/v1/costs/{cost_to_edit_id}", json={"amount_pence": 60000}, auth=AUTH)
        assert r.status_code == 200, r.text

        r = await client.get(f"/api/v1/cases/{case_id}/costs", auth=AUTH)
        totals = r.json()["totals"]
        assert totals["invoiced_pence"] == 60000
        assert totals["net_pence"] == 59000
        assert totals["committed_pence"] == 80000  # 60000 + 20000

        r = await client.delete(f"/api/v1/costs/{cost_to_edit_id}", auth=AUTH)
        assert r.status_code == 204
        r = await client.get(f"/api/v1/cases/{case_id}/costs", auth=AUTH)
        assert len(r.json()["items"]) == 3


@pytest.mark.asyncio
async def test_cost_validation_rejections(app_db):
    _, _, case_id, work_order_id = await _seed_case()
    async with await _client() as client:
        # zero amount
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={"kind": "QUOTE", "amount_pence": 0, "description": "x", "incurred_at": utcnow().isoformat()},
            auth=AUTH,
        )
        assert r.status_code == 422

        # negative QUOTE
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={"kind": "QUOTE", "amount_pence": -500, "description": "x", "incurred_at": utcnow().isoformat()},
            auth=AUTH,
        )
        assert r.status_code == 422

        # negative INVOICE
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={"kind": "INVOICE", "amount_pence": -500, "description": "x", "incurred_at": utcnow().isoformat()},
            auth=AUTH,
        )
        assert r.status_code == 422

        # blank description
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={"kind": "QUOTE", "amount_pence": 100, "description": "   ", "incurred_at": utcnow().isoformat()},
            auth=AUTH,
        )
        assert r.status_code == 422

        # future incurred_at
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={"kind": "QUOTE", "amount_pence": 100, "description": "x", "incurred_at": future},
            auth=AUTH,
        )
        assert r.status_code == 422

        # work order from a different case
        _, _, other_case_id, other_wo_id = await _seed_case()
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={
                "work_order_id": other_wo_id, "kind": "QUOTE", "amount_pence": 100, "description": "x",
                "incurred_at": utcnow().isoformat(),
            },
            auth=AUTH,
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_cost_archival_refusals(app_db):
    _, _, case_id, _ = await _seed_case()
    async with session_scope() as session:
        batch = ArchiveBatchModel(id=new_uuid(), label=f"batch-{new_uuid()}", generator_version="1", random_seed=1)
        session.add(batch)
        await session.flush()
        case = await session.get(RepairCaseModel, case_id)
        case.archive_batch_id = batch.id
        archival_cost = CostEntryModel(
            id=new_uuid(), case_id=case_id, kind="QUOTE", amount_pence=1000, description="archival",
            incurred_at=utcnow(), recorded_by="importer", recorded_at=utcnow(), archive_batch_id=batch.id,
        )
        session.add(archival_cost)
        await session.flush()
        archival_cost_id = archival_cost.id

    async with await _client() as client:
        # creating against an archival case is refused
        r = await client.post(
            f"/api/v1/cases/{case_id}/costs",
            json={"kind": "QUOTE", "amount_pence": 100, "description": "x", "incurred_at": utcnow().isoformat()},
            auth=AUTH,
        )
        assert r.status_code == 409

        r = await client.patch(f"/api/v1/costs/{archival_cost_id}", json={"amount_pence": 2000}, auth=AUTH)
        assert r.status_code == 409

        r = await client.delete(f"/api/v1/costs/{archival_cost_id}", auth=AUTH)
        assert r.status_code == 409

        r = await client.get(f"/api/v1/cases/{case_id}/costs", auth=AUTH)
        assert r.json()["items"][0]["is_archived"] is True


# --------------------------------------------------------------------------
# Messaging
# --------------------------------------------------------------------------


async def _add_message(case_id: str, sender_type: str, text: str, *, read_at=None, channel="INTERNAL", delivery_state="INTERNAL_NOTE") -> str:
    async with session_scope() as session:
        message = MessageModel(
            id=new_uuid(), case_id=case_id, sender_type=sender_type, sender_name=sender_type.title(),
            text=text, created_at=utcnow(), channel=channel, delivery_state=delivery_state, read_at=read_at,
        )
        session.add(message)
        await session.flush()
        return message.id


@pytest.mark.asyncio
async def test_thread_list_and_detail(app_db):
    _, _, case_id, _ = await _seed_case()
    await _add_message(case_id, MessageSenderType.TENANT.value, "The leak is worse today")
    await _add_message(case_id, MessageSenderType.OPERATOR.value, "We've booked a roofer for Tuesday")

    async with await _client() as client:
        r = await client.get("/api/v1/messages/threads", auth=AUTH)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        thread = items[0]
        assert thread["case_id"] == case_id
        assert thread["total_count"] == 2
        assert thread["unread_count"] == 1  # the tenant message is unread
        assert thread["last_message_preview"] == "We've booked a roofer for Tuesday"

        r = await client.get(f"/api/v1/messages/threads/{case_id}", auth=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert body["items"][0]["text"] == "The leak is worse today"  # oldest first


@pytest.mark.asyncio
async def test_compose_outward_channel_persists_as_draft_never_sent(app_db):
    _, _, case_id, _ = await _seed_case()
    async with await _client() as client:
        r = await client.post(
            f"/api/v1/messages/threads/{case_id}", json={"text": "Reminder: visit tomorrow 9am", "channel": "EMAIL"},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["delivery_state"] == "DRAFT"
        assert body["delivery_state"] != "SENT"
        assert body["delivery_state"] != "DELIVERED"
        assert body["delivery_detail"] is not None and "EMAIL" in body["delivery_detail"]

        r = await client.post(
            f"/api/v1/messages/threads/{case_id}", json={"text": "Internal reminder", "channel": "INTERNAL"},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        assert r.json()["delivery_state"] == "INTERNAL_NOTE"

    async with session_scope() as session:
        rows = (await session.execute(select(MessageModel).where(MessageModel.case_id == case_id))).scalars().all()
        assert all(m.delivery_state not in ("SENT", "DELIVERED", "QUEUED") for m in rows)


@pytest.mark.asyncio
async def test_compose_blank_text_rejected(app_db):
    _, _, case_id, _ = await _seed_case()
    async with await _client() as client:
        r = await client.post(f"/api/v1/messages/threads/{case_id}", json={"text": "  ", "channel": "INTERNAL"}, auth=AUTH)
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_read_unread_toggling_and_unread_count_matches_thread_sum(app_db):
    _, _, case_id_a, _ = await _seed_case()
    _, _, case_id_b, _ = await _seed_case()
    await _add_message(case_id_a, MessageSenderType.TENANT.value, "msg 1")
    await _add_message(case_id_a, MessageSenderType.CONTRACTOR.value, "msg 2")
    await _add_message(case_id_b, MessageSenderType.TENANT.value, "msg 3")

    async with await _client() as client:
        r = await client.get("/api/v1/messages/unread-count", auth=AUTH)
        assert r.status_code == 200
        global_count = r.json()["unread_count"]
        assert global_count == 3

        r = await client.get("/api/v1/messages/threads", auth=AUTH)
        thread_sum = sum(item["unread_count"] for item in r.json()["items"])
        assert thread_sum == global_count

        r = await client.post(f"/api/v1/messages/threads/{case_id_a}/read", auth=AUTH)
        assert r.status_code == 200
        assert r.json()["unread_count"] == 0

        r = await client.get("/api/v1/messages/unread-count", auth=AUTH)
        assert r.json()["unread_count"] == 1  # only case_id_b's message remains unread

        # per-message toggle
        async with session_scope() as session:
            remaining = (
                await session.execute(
                    select(MessageModel).where(MessageModel.case_id == case_id_b, MessageModel.read_at.is_(None))
                )
            ).scalars().first()
        message_id = remaining.id

        r = await client.post(f"/api/v1/messages/{message_id}/read", auth=AUTH)
        assert r.status_code == 200
        assert r.json()["message"]["read_at"] is not None

        r = await client.get("/api/v1/messages/unread-count", auth=AUTH)
        assert r.json()["unread_count"] == 0

        r = await client.post(f"/api/v1/messages/{message_id}/unread", auth=AUTH)
        assert r.status_code == 200
        assert r.json()["message"]["read_at"] is None

        r = await client.get("/api/v1/messages/unread-count", auth=AUTH)
        assert r.json()["unread_count"] == 1


@pytest.mark.asyncio
async def test_requires_operator_auth(app_db):
    os.environ["OPERATOR_AUTH_ENABLED"] = "true"
    get_settings.cache_clear()
    try:
        async with await _client() as client:
            r = await client.get("/api/v1/messages/unread-count")
            assert r.status_code == 401
            r = await client.get("/api/v1/messages/unread-count", auth=AUTH)
            assert r.status_code == 200
    finally:
        os.environ.pop("OPERATOR_AUTH_ENABLED", None)
        get_settings.cache_clear()
