"""Free-text operator notes against a property, case, contractor or tenant
(docs/16 "Notes & documents" surface). See documents.py's module docstring
for why request/response DTOs live locally in each of this phase's routers
rather than in app.schemas.

Authoring is deliberately narrow: `author` always comes from the
`require_operator` dependency (the authenticated Basic-auth username),
never from the request body -- a client cannot forge who wrote a note.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.api.deps import get_session, require_operator
from app.api.documents import verify_subject_exists
from app.domain.errors import ConflictError, NotFoundError
from app.models import NoteModel, new_uuid, utcnow
from app.schemas import ReadModel, RecordSubject, StrictModel

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])

_MAX_BODY_CHARS = 5000


def _validate_body(value: str) -> str:
    if not value.strip():
        raise ValueError("body must not be empty")
    if len(value) > _MAX_BODY_CHARS:
        raise ValueError(f"body must be at most {_MAX_BODY_CHARS} characters")
    return value


class NoteCreateRequest(StrictModel):
    subject_type: RecordSubject
    subject_id: str
    body: str

    @field_validator("body")
    @classmethod
    def _check_body(cls, value: str) -> str:
        return _validate_body(value)


class NoteUpdateRequest(StrictModel):
    body: str

    @field_validator("body")
    @classmethod
    def _check_body(cls, value: str) -> str:
        return _validate_body(value)


class NoteRecord(ReadModel):
    id: UUID
    subject_type: RecordSubject
    subject_id: str
    body: str
    author: str
    created_at: datetime
    updated_at: datetime
    is_archived: bool


class NoteListResponse(StrictModel):
    items: list[NoteRecord]


def _to_record(note: NoteModel) -> NoteRecord:
    return NoteRecord(
        id=note.id, subject_type=note.subject_type, subject_id=note.subject_id, body=note.body,
        author=note.author, created_at=note.created_at, updated_at=note.updated_at,
        is_archived=note.archive_batch_id is not None,
    )


@router.get("/notes")
async def list_notes(
    subject_type: RecordSubject = Query(...), subject_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> NoteListResponse:
    rows = (
        await session.execute(
            select(NoteModel)
            .where(NoteModel.subject_type == subject_type, NoteModel.subject_id == subject_id)
            .order_by(NoteModel.created_at.desc())
        )
    ).scalars().all()
    return NoteListResponse(items=[_to_record(n) for n in rows])


@router.post("/notes", status_code=201)
async def create_note(
    request: NoteCreateRequest, operator: str = Depends(require_operator), session: AsyncSession = Depends(get_session),
) -> NoteRecord:
    await verify_subject_exists(session, request.subject_type, request.subject_id)
    note = NoteModel(
        id=new_uuid(), subject_type=request.subject_type, subject_id=request.subject_id,
        body=request.body, author=operator, created_at=utcnow(), updated_at=utcnow(),
    )
    session.add(note)
    await session.flush()
    return _to_record(note)


@router.patch("/notes/{note_id}")
async def update_note(note_id: str, request: NoteUpdateRequest, session: AsyncSession = Depends(get_session)) -> NoteRecord:
    note = await session.get(NoteModel, note_id)
    if note is None:
        raise NotFoundError(f"note {note_id} not found")
    if note.archive_batch_id is not None:
        raise ConflictError(f"note {note_id} is archival and cannot be edited")
    note.body = request.body
    note.updated_at = utcnow()
    await session.flush()
    return _to_record(note)


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: str, session: AsyncSession = Depends(get_session)) -> Response:
    note = await session.get(NoteModel, note_id)
    if note is None:
        raise NotFoundError(f"note {note_id} not found")
    if note.archive_batch_id is not None:
        raise ConflictError(f"note {note_id} is archival and cannot be deleted")
    await session.delete(note)
    await session.flush()
    return Response(status_code=204)
