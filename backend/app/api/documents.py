"""File upload/storage endpoints for documents attached to a property,
case, contractor or tenant (docs/16 "Notes & documents" surface).

Request/response DTOs are defined locally in this router rather than in
app.schemas: this phase's ownership split gives schemas.py a single owner
and lets documents.py/notes.py/costs.py/messaging.py be built in parallel
without colliding edits. `SUBJECT_MODELS`/`verify_subject_exists` below are
shared with notes.py (both file things against the same four subject
kinds) -- imported from here rather than duplicated.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.api.deps import get_session, require_operator
from app.config import get_settings
from app.domain.errors import ConflictError, DomainError, NotFoundError, PayloadTooLargeError
from app.models import ContractorModel, DocumentModel, PropertyModel, RepairCaseModel, TenantModel, new_uuid, utcnow
from app.schemas import ReadModel, RecordSubject, StrictModel

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])

# Which ORM table a given RecordSubject resolves against, so an upload/note
# filed against a nonexistent property/case/contractor/tenant id is
# rejected with NotFoundError rather than silently attached to nothing.
SUBJECT_MODELS: dict[RecordSubject, type] = {
    RecordSubject.PROPERTY: PropertyModel,
    RecordSubject.CASE: RepairCaseModel,
    RecordSubject.CONTRACTOR: ContractorModel,
    RecordSubject.TENANT: TenantModel,
}


async def verify_subject_exists(session: AsyncSession, subject_type: RecordSubject, subject_id: str) -> None:
    model = SUBJECT_MODELS[subject_type]
    obj = await session.get(model, subject_id)
    if obj is None:
        raise NotFoundError(f"{subject_type.value.lower()} {subject_id} not found")


_SAFE_EXT_RE = re.compile(r"^[A-Za-z0-9]{1,10}$")

# Content types the browser can render inline instead of downloading.
_INLINE_CONTENT_TYPES = {"application/pdf"}

_UPLOAD_CHUNK_BYTES = 1024 * 1024


def _sanitized_suffix(filename: str | None) -> str:
    """Derives a safe `.ext` suffix from an untrusted upload filename.

    Used for nothing but that suffix: the file is always written to
    `uuid4().hex + suffix` under settings.documents_dir, so a
    traversal-shaped filename ("../../etc/passwd", "..\\..\\win.ini")
    cannot influence where bytes land -- at most it contributes a
    (separately validated) extension.
    """
    if not filename:
        return ""
    ext = Path(filename).suffix.lstrip(".")
    if not ext or not _SAFE_EXT_RE.match(ext):
        return ""
    return f".{ext.lower()}"


async def _read_capped(upload: UploadFile, max_bytes: int) -> bytes:
    """Reads the upload into memory, refusing before the cap is exceeded.
    Nothing is written to disk until this returns, so a rejected upload
    never leaves a partial file behind."""
    total = 0
    chunks: list[bytes] = []
    while True:
        chunk = await upload.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError(
                f"upload exceeds the maximum allowed size of {max_bytes} bytes"
            )
        chunks.append(chunk)
    return b"".join(chunks)


class DocumentRecord(ReadModel):
    id: UUID
    subject_type: RecordSubject
    subject_id: str
    display_name: str
    content_type: str
    size_bytes: int
    description: str | None = None
    uploaded_by: str
    uploaded_at: datetime
    is_archived: bool


class DocumentListResponse(StrictModel):
    items: list[DocumentRecord]


def _to_record(doc: DocumentModel) -> DocumentRecord:
    return DocumentRecord(
        id=doc.id, subject_type=doc.subject_type, subject_id=doc.subject_id,
        display_name=doc.display_name, content_type=doc.content_type, size_bytes=doc.size_bytes,
        description=doc.description, uploaded_by=doc.uploaded_by, uploaded_at=doc.uploaded_at,
        is_archived=doc.archive_batch_id is not None,
    )


@router.post("/documents", status_code=201)
async def upload_document(
    subject_type: RecordSubject = Form(...),
    subject_id: str = Form(...),
    description: str | None = Form(default=None),
    file: UploadFile = File(...),
    operator: str = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> DocumentRecord:
    await verify_subject_exists(session, subject_type, subject_id)

    settings = get_settings()
    body = await _read_capped(file, settings.max_document_bytes)
    if not body:
        raise DomainError("empty file rejected")

    stored_name = f"{uuid4().hex}{_sanitized_suffix(file.filename)}"
    path = settings.documents_dir / stored_name
    path.write_bytes(body)

    try:
        document = DocumentModel(
            id=new_uuid(), subject_type=subject_type, subject_id=subject_id,
            display_name=(file.filename or stored_name)[:255], stored_name=stored_name,
            content_type=file.content_type or "application/octet-stream", size_bytes=len(body),
            description=description, uploaded_by=operator, uploaded_at=utcnow(),
        )
        session.add(document)
        await session.flush()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return _to_record(document)


@router.get("/documents")
async def list_documents(
    subject_type: RecordSubject = Query(...), subject_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentListResponse:
    rows = (
        await session.execute(
            select(DocumentModel)
            .where(DocumentModel.subject_type == subject_type, DocumentModel.subject_id == subject_id)
            .order_by(DocumentModel.uploaded_at.desc())
        )
    ).scalars().all()
    return DocumentListResponse(items=[_to_record(d) for d in rows])


@router.get("/documents/{document_id}")
async def get_document(document_id: str, session: AsyncSession = Depends(get_session)) -> DocumentRecord:
    doc = await session.get(DocumentModel, document_id)
    if doc is None:
        raise NotFoundError(f"document {document_id} not found")
    return _to_record(doc)


@router.get("/documents/{document_id}/content")
async def get_document_content(
    document_id: str, download: bool = Query(default=False), session: AsyncSession = Depends(get_session),
) -> Response:
    doc = await session.get(DocumentModel, document_id)
    if doc is None:
        raise NotFoundError(f"document {document_id} not found")
    settings = get_settings()
    path = settings.documents_dir / doc.stored_name
    if not path.exists():
        raise NotFoundError(f"document {document_id} metadata exists but its file is missing from disk")

    is_previewable = doc.content_type.startswith("image/") or doc.content_type in _INLINE_CONTENT_TYPES
    disposition = "attachment" if (download or not is_previewable) else "inline"
    safe_name = doc.display_name.replace('"', "")
    headers = {"Content-Disposition": f'{disposition}; filename="{safe_name}"'}
    return Response(content=path.read_bytes(), media_type=doc.content_type, headers=headers)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, session: AsyncSession = Depends(get_session)) -> Response:
    doc = await session.get(DocumentModel, document_id)
    if doc is None:
        raise NotFoundError(f"document {document_id} not found")
    if doc.archive_batch_id is not None:
        raise ConflictError(f"document {document_id} is archival and cannot be deleted")
    settings = get_settings()
    path = settings.documents_dir / doc.stored_name
    await session.delete(doc)
    await session.flush()
    path.unlink(missing_ok=True)
    return Response(status_code=204)
