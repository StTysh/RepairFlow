"""Tenant/contractor/operator message threads -- one thread per case
(docs/16). See documents.py's module docstring for why request/response
DTOs live locally in this router rather than in app.schemas.

Nothing here may claim a message was sent because a row was saved
(CLAUDE.md: "Provider request acceptance is not booking confirmation" and
the broader honesty rule it generalizes). `channel=INTERNAL` is a real,
complete outcome on its own (an internal note that was never meant to
leave the system); any outward channel (EMAIL/SMS/VOICE) is persisted as a
DRAFT with a `delivery_detail` saying plainly that no transport is wired
up. No provider is ever called from this router, and
app.integrations.no_contact is never imported here -- there is simply
nothing outbound for it to guard.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain.errors import ConflictError, DomainError, NotFoundError
from app.domain.services import load_case
from app.models import DocumentModel, MessageModel, PropertyModel, RepairCaseModel, TenantModel, new_uuid, utcnow
from app.schemas import MessageChannel, MessageDeliveryState, MessageSenderType, ReadModel, StrictModel

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])

#: Sender types that represent someone outside the operator contacting in --
#: what "unread" means throughout this router. An operator's own message
#: is never "unread" by the operator.
INBOUND_SENDER_TYPES = (MessageSenderType.TENANT, MessageSenderType.CONTRACTOR)

_PREVIEW_MAX_CHARS = 160


def _preview(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _PREVIEW_MAX_CHARS:
        return stripped
    return stripped[:_PREVIEW_MAX_CHARS].rstrip() + "…"


class MessageRecord(ReadModel):
    id: UUID
    case_id: UUID
    sender_type: MessageSenderType
    sender_name: str
    text: str
    photo_url: str | None = None
    channel: MessageChannel
    delivery_state: MessageDeliveryState
    delivery_detail: str | None = None
    queued_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    attachments: list[dict] = Field(default_factory=list)
    communication_id: UUID | None = None
    created_at: datetime
    is_archived: bool


class ThreadListItem(StrictModel):
    case_id: UUID
    case_number: int
    case_title: str
    property_address: str
    tenant_name: str
    last_message_preview: str
    last_message_at: datetime
    last_message_sender_type: MessageSenderType
    unread_count: int
    total_count: int
    is_archived: bool


class ThreadListResponse(StrictModel):
    items: list[ThreadListItem]
    next_cursor: str | None = None


class ThreadDetailResponse(StrictModel):
    case_id: UUID
    items: list[MessageRecord]


class ComposeMessageRequest(StrictModel):
    text: str
    channel: MessageChannel
    attachments: list[UUID] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be empty")
        return value


class ThreadReadResponse(StrictModel):
    case_id: UUID
    unread_count: int


class MessageReadToggleResponse(StrictModel):
    message: MessageRecord


class UnreadCountResponse(StrictModel):
    unread_count: int


def _to_message_record(m: MessageModel) -> MessageRecord:
    return MessageRecord(
        id=m.id, case_id=m.case_id, sender_type=m.sender_type, sender_name=m.sender_name, text=m.text,
        photo_url=m.photo_url, channel=m.channel, delivery_state=m.delivery_state, delivery_detail=m.delivery_detail,
        queued_at=m.queued_at, delivered_at=m.delivered_at, read_at=m.read_at, attachments=m.attachments or [],
        communication_id=m.communication_id, created_at=m.created_at, is_archived=m.archive_batch_id is not None,
    )


async def unread_counts_by_case(session: AsyncSession) -> dict[str, int]:
    """Single source of truth for "how many unread inbound messages does
    this case have" -- used by both /messages/unread-count (summed across
    every case) and /messages/threads (per row), so a badge built from one
    can never disagree with a list built from the other. Archival cases are
    never counted here (house rule: excluded from operational defaults) --
    their history is display-only, so nothing in it is meaningfully
    "unread" for a live badge."""
    rows = (
        await session.execute(
            select(MessageModel.case_id, func.count(MessageModel.id))
            .join(RepairCaseModel, RepairCaseModel.id == MessageModel.case_id)
            .where(
                MessageModel.read_at.is_(None),
                MessageModel.sender_type.in_(INBOUND_SENDER_TYPES),
                RepairCaseModel.archive_batch_id.is_(None),
            )
            .group_by(MessageModel.case_id)
        )
    ).all()
    return {case_id: count for case_id, count in rows}


@router.get("/messages/unread-count")
async def get_unread_count(session: AsyncSession = Depends(get_session)) -> UnreadCountResponse:
    counts = await unread_counts_by_case(session)
    return UnreadCountResponse(unread_count=sum(counts.values()))


@router.get("/messages/threads")
async def list_threads(
    q: str | None = None,
    unread_only: bool = False,
    include_archived: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> ThreadListResponse:
    counts_by_case = await unread_counts_by_case(session)

    ranked = (
        select(
            MessageModel.case_id.label("case_id"),
            MessageModel.text.label("text"),
            MessageModel.sender_type.label("sender_type"),
            MessageModel.created_at.label("created_at"),
            func.row_number()
            .over(partition_by=MessageModel.case_id, order_by=MessageModel.created_at.desc())
            .label("rn"),
        )
    ).subquery()
    last_message = select(ranked).where(ranked.c.rn == 1).subquery()

    counts_sq = (
        select(MessageModel.case_id.label("case_id"), func.count(MessageModel.id).label("total_count"))
        .group_by(MessageModel.case_id)
        .subquery()
    )

    query = (
        select(
            RepairCaseModel, PropertyModel.address_line, TenantModel.display_name,
            last_message.c.text, last_message.c.sender_type, last_message.c.created_at,
            counts_sq.c.total_count,
        )
        .join(last_message, last_message.c.case_id == RepairCaseModel.id)
        .join(counts_sq, counts_sq.c.case_id == RepairCaseModel.id)
        .join(PropertyModel, PropertyModel.id == RepairCaseModel.property_id)
        .join(TenantModel, TenantModel.id == RepairCaseModel.tenant_id)
        .order_by(last_message.c.created_at.desc())
    )
    if not include_archived:
        query = query.where(RepairCaseModel.archive_batch_id.is_(None))
    if unread_only:
        query = query.where(RepairCaseModel.id.in_(list(counts_by_case.keys())))
    if q:
        like = f"%{q}%"
        text_match = (
            select(MessageModel.id)
            .where(MessageModel.case_id == RepairCaseModel.id, MessageModel.text.like(like))
            .exists()
        )
        query = query.where(or_(text_match, RepairCaseModel.title.like(like), TenantModel.display_name.like(like)))
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
        except ValueError:
            raise DomainError(f"cursor {cursor!r} is not a valid ISO-8601 timestamp")
        query = query.where(last_message.c.created_at < cursor_dt)

    rows = (await session.execute(query.limit(limit + 1))).all()
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1][5].isoformat()
        rows = rows[:limit]

    items = [
        ThreadListItem(
            case_id=case.id, case_number=case.case_number, case_title=case.title, property_address=address,
            tenant_name=tenant_name, last_message_preview=_preview(text), last_message_at=last_at,
            last_message_sender_type=sender_type, unread_count=counts_by_case.get(case.id, 0),
            total_count=total_count, is_archived=case.archive_batch_id is not None,
        )
        for case, address, tenant_name, text, sender_type, last_at, total_count in rows
    ]
    return ThreadListResponse(items=items, next_cursor=next_cursor)


@router.get("/messages/threads/{case_id}")
async def get_thread(case_id: str, session: AsyncSession = Depends(get_session)) -> ThreadDetailResponse:
    case = await load_case(session, case_id)
    rows = (
        await session.execute(
            select(MessageModel).where(MessageModel.case_id == case_id).order_by(MessageModel.created_at.asc())
        )
    ).scalars().all()
    return ThreadDetailResponse(case_id=case.id, items=[_to_message_record(m) for m in rows])


@router.post("/messages/threads/{case_id}", status_code=201)
async def compose_message(
    case_id: str, request: ComposeMessageRequest, operator: str = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> MessageRecord:
    case = await load_case(session, case_id)
    if case.archive_batch_id is not None:
        raise ConflictError(f"case {case_id} is archival; no new messages can be filed against it")

    attachment_payload: list[dict] = []
    for doc_id in request.attachments:
        doc = await session.get(DocumentModel, str(doc_id))
        if doc is None:
            raise NotFoundError(f"document {doc_id} not found")
        attachment_payload.append(
            {"document_id": str(doc_id), "display_name": doc.display_name, "content_type": doc.content_type}
        )

    if request.channel == MessageChannel.INTERNAL:
        delivery_state = MessageDeliveryState.INTERNAL_NOTE
        delivery_detail = None
    else:
        # No outbound transport is wired up for any channel here. This is a
        # real, honest terminal state for this composition -- not a queued
        # send -- so the row is saved as DRAFT and delivery_detail says so
        # plainly. Never SENT/DELIVERED, and no provider is ever called.
        delivery_state = MessageDeliveryState.DRAFT
        delivery_detail = (
            f"No delivery transport is configured for {request.channel.value}; "
            "this message has been saved as a draft only and has not been sent."
        )

    message = MessageModel(
        id=new_uuid(), case_id=case_id, sender_type=MessageSenderType.OPERATOR, sender_name=operator,
        text=request.text, created_at=utcnow(), channel=request.channel, delivery_state=delivery_state,
        delivery_detail=delivery_detail, attachments=attachment_payload,
    )
    session.add(message)
    await session.flush()
    return _to_message_record(message)


@router.post("/messages/threads/{case_id}/read")
async def mark_thread_read(case_id: str, session: AsyncSession = Depends(get_session)) -> ThreadReadResponse:
    case = await load_case(session, case_id)
    if case.archive_batch_id is not None:
        raise ConflictError(f"case {case_id} is archival; its messages cannot be mutated")
    now = utcnow()
    rows = (
        await session.execute(
            select(MessageModel).where(
                MessageModel.case_id == case_id,
                MessageModel.read_at.is_(None),
                MessageModel.sender_type.in_(INBOUND_SENDER_TYPES),
            )
        )
    ).scalars().all()
    for m in rows:
        m.read_at = now
    await session.flush()
    counts = await unread_counts_by_case(session)
    return ThreadReadResponse(case_id=case.id, unread_count=counts.get(case.id, 0))


@router.post("/messages/{message_id}/read")
async def mark_message_read(message_id: str, session: AsyncSession = Depends(get_session)) -> MessageReadToggleResponse:
    m = await session.get(MessageModel, message_id)
    if m is None:
        raise NotFoundError(f"message {message_id} not found")
    if m.archive_batch_id is not None:
        raise ConflictError(f"message {message_id} is archival and cannot be mutated")
    if m.read_at is None:
        m.read_at = utcnow()
        await session.flush()
    return MessageReadToggleResponse(message=_to_message_record(m))


@router.post("/messages/{message_id}/unread")
async def mark_message_unread(message_id: str, session: AsyncSession = Depends(get_session)) -> MessageReadToggleResponse:
    m = await session.get(MessageModel, message_id)
    if m is None:
        raise NotFoundError(f"message {message_id} not found")
    if m.archive_batch_id is not None:
        raise ConflictError(f"message {message_id} is archival and cannot be mutated")
    if m.read_at is not None:
        m.read_at = None
        await session.flush()
    return MessageReadToggleResponse(message=_to_message_record(m))
