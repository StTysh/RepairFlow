"""Contractor directory API (list/create/read/update).

Request/response Pydantic models live in this file rather than
app.schemas -- see the module docstring in app/api/properties.py for why.

Archival note: `ContractorModel.archive_batch_id` marks a row created by
the synthetic archive import. Such rows exist only to give historical
work orders a named contractor; they are never contactable, never
assignable, and read-only. They are excluded from the directory unless
`include_archived=true` is passed.

That is a different axis from `approval_status`. An un-APPROVED
contractor is a *research candidate* -- a real company someone found but
nobody has verified -- which is neither archival nor bookable. Both
distinctions have to survive into the UI, so both are exposed
separately.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain.errors import ConflictError, NotFoundError
from app.models import AppointmentModel, ContractorModel, RepairCaseModel, WorkOrderModel, new_uuid
from app.schemas import ConnectorType, ContractorApprovalStatus, Trade

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)


class ContractorListItem(_ResponseModel):
    id: str
    display_name: str
    trades: list[str]
    service_postcodes: list[str]
    approval_status: ContractorApprovalStatus
    connector: ConnectorType
    contact_reference: str | None
    verification_note: str | None
    provenance: str
    assigned_work_order_count: int
    completed_work_order_count: int
    is_archived: bool


class ContractorListResponse(_ResponseModel):
    items: list[ContractorListItem]
    limit: int
    offset: int
    total: int
    # Derived, not stored: the UI's pagination controls need to know
    # whether a Next button should exist, and computing offset+len(items)
    # < total in three separate screens is how they drift apart.
    has_more: bool


class ContractorWorkHistoryItem(_ResponseModel):
    id: str
    case_id: str
    case_number: int
    case_title: str
    trade: Trade
    status: str
    scope: str
    quote_pence: int | None
    created_at: datetime
    case_is_archived: bool


class ContractorDetail(ContractorListItem):
    work_history: list[ContractorWorkHistoryItem]
    appointment_count: int


class ContractorCreateRequest(_RequestModel):
    # Deliberately no `approval_status` field: a POST can never create an
    # already-APPROVED contractor (approval is a separate deliberate act
    # -- see PATCH below). Every new contractor starts PENDING.
    display_name: str = Field(min_length=1)
    trades: list[Trade] = Field(min_length=1)
    service_postcodes: list[str] = Field(default_factory=list)
    connector: ConnectorType = ConnectorType.MOCK
    contact_reference: str | None = None
    verification_note: str | None = None


class ContractorUpdateRequest(_RequestModel):
    display_name: str | None = None
    trades: list[Trade] | None = None
    service_postcodes: list[str] | None = None
    contact_reference: str | None = None
    verification_note: str | None = None
    approval_status: ContractorApprovalStatus | None = None

    @field_validator("trades")
    @classmethod
    def _trades_non_empty(cls, v: list[Trade] | None) -> list[Trade] | None:
        if v is not None and len(v) == 0:
            raise ValueError("trades must be a non-empty list when provided")
        return v


async def _work_order_counts(session: AsyncSession, contractor_ids: list[str]) -> dict[str, tuple[int, int]]:
    """Returns {contractor_id: (assigned_total, completed_total)} -- every
    work order the contractor has ever been tied to, and the subset of
    those that reached COMPLETED. Computed in Python rather than a SQL
    CASE/GROUP BY: this is an MVP-scale directory (docs/04), and the
    dataset per contractor is small."""
    if not contractor_ids:
        return {}
    rows = (
        await session.execute(
            select(WorkOrderModel.contractor_id, WorkOrderModel.status).where(
                WorkOrderModel.contractor_id.in_(contractor_ids)
            )
        )
    ).all()
    counts: dict[str, list[int]] = {cid: [0, 0] for cid in contractor_ids}
    for contractor_id, status in rows:
        bucket = counts.setdefault(contractor_id, [0, 0])
        bucket[0] += 1
        if status == "COMPLETED":
            bucket[1] += 1
    return {cid: (v[0], v[1]) for cid, v in counts.items()}


def _list_item(contractor: ContractorModel, assigned: int, completed: int) -> ContractorListItem:
    return ContractorListItem(
        id=contractor.id, display_name=contractor.display_name, trades=list(contractor.trades or []),
        service_postcodes=list(contractor.service_postcodes or []), approval_status=contractor.approval_status,
        connector=contractor.connector, contact_reference=contractor.contact_reference,
        verification_note=contractor.verification_note, provenance=contractor.provenance,
        assigned_work_order_count=assigned, completed_work_order_count=completed,
        is_archived=contractor.archive_batch_id is not None,
    )


async def _contractor_detail(session: AsyncSession, contractor: ContractorModel) -> ContractorDetail:
    counts = await _work_order_counts(session, [contractor.id])
    assigned, completed = counts.get(contractor.id, (0, 0))
    item = _list_item(contractor, assigned, completed)

    history_rows = (
        await session.execute(
            select(WorkOrderModel, RepairCaseModel.case_number, RepairCaseModel.title, RepairCaseModel.archive_batch_id)
            .join(RepairCaseModel, RepairCaseModel.id == WorkOrderModel.case_id)
            .where(WorkOrderModel.contractor_id == contractor.id)
            .order_by(WorkOrderModel.created_at.desc())
        )
    ).all()
    work_history = [
        ContractorWorkHistoryItem(
            id=wo.id, case_id=wo.case_id, case_number=case_number, case_title=case_title, trade=wo.trade,
            status=wo.status, scope=wo.scope, quote_pence=wo.quote_pence, created_at=wo.created_at,
            case_is_archived=archive_batch_id is not None,
        )
        for wo, case_number, case_title, archive_batch_id in history_rows
    ]
    appointment_count = (
        await session.execute(select(func.count(AppointmentModel.id)).where(AppointmentModel.contractor_id == contractor.id))
    ).scalar_one()

    return ContractorDetail(**item.model_dump(), work_history=work_history, appointment_count=appointment_count)


@router.get("/contractors")
async def list_contractors(
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = None,
    trade: Trade | None = None,
    approval_status: ContractorApprovalStatus | None = None,
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> ContractorListResponse:
    filters = []
    if not include_archived:
        filters.append(ContractorModel.archive_batch_id.is_(None))
    if q:
        filters.append(ContractorModel.display_name.like(f"%{q}%"))
    if approval_status is not None:
        filters.append(ContractorModel.approval_status == approval_status)
    if trade is not None:
        # `trades` is a JSON column (list[str]); the generic sa.JSON type
        # has no array-containment operator on SQLite the way
        # postgresql.JSONB does, but SQLite stores the column as its JSON
        # text encoding, so a LIKE against the quoted value is an exact
        # element match. Safe because Trade's five members (schemas.py)
        # are short and fixed and none is a substring of another's quoted
        # form, unlike the free-text `q` search above.
        filters.append(ContractorModel.trades.like(f'%"{trade.value}"%'))

    total = (
        await session.execute(
            select(func.count()).select_from(select(ContractorModel.id).where(*filters).subquery())
        )
    ).scalar_one()

    query = (
        select(ContractorModel)
        .where(*filters)
        .order_by(ContractorModel.display_name, ContractorModel.id)
        .limit(limit)
        .offset(offset)
    )
    page = (await session.execute(query)).scalars().all()
    counts = await _work_order_counts(session, [c.id for c in page])
    items = [_list_item(c, *counts.get(c.id, (0, 0))) for c in page]
    return ContractorListResponse(
        items=items, limit=limit, offset=offset, total=total,
        has_more=offset + len(items) < total,
    )


@router.post("/contractors", status_code=201)
async def create_contractor(request: ContractorCreateRequest, session: AsyncSession = Depends(get_session)) -> ContractorListItem:
    contractor = ContractorModel(
        id=new_uuid(), display_name=request.display_name, trades=[t.value for t in request.trades],
        service_postcodes=list(request.service_postcodes), approval_status=ContractorApprovalStatus.PENDING,
        connector=request.connector, contact_reference=request.contact_reference,
        verification_note=request.verification_note, provenance="SIMULATED",
    )
    session.add(contractor)
    await session.flush()
    return _list_item(contractor, 0, 0)


@router.get("/contractors/{contractor_id}")
async def get_contractor(contractor_id: str, session: AsyncSession = Depends(get_session)) -> ContractorDetail:
    contractor = await session.get(ContractorModel, contractor_id)
    if contractor is None:
        raise NotFoundError(f"contractor {contractor_id} not found")
    return await _contractor_detail(session, contractor)


@router.patch("/contractors/{contractor_id}")
async def update_contractor(
    contractor_id: str, request: ContractorUpdateRequest, session: AsyncSession = Depends(get_session)
) -> ContractorDetail:
    contractor = await session.get(ContractorModel, contractor_id)
    if contractor is None:
        raise NotFoundError(f"contractor {contractor_id} not found")
    if contractor.archive_batch_id is not None:
        raise ConflictError(
            "this contractor is an archival sample record; archival records are read-only"
        )

    updates = request.model_dump(exclude_unset=True)
    if updates.get("approval_status") == ContractorApprovalStatus.APPROVED:
        candidate_note = updates.get("verification_note", contractor.verification_note)
        if not candidate_note or not str(candidate_note).strip():
            raise ConflictError("a contractor cannot be approved without a recorded verification note")

    for field, value in updates.items():
        if field == "trades" and value is not None:
            value = [t.value for t in value]
        setattr(contractor, field, value)
    await session.flush()
    return await _contractor_detail(session, contractor)
