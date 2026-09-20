"""Money entries against a case, in integer pence (docs/16/17, and
CostEntryModel's own docstring on why the unit is always pence). See
documents.py's module docstring for why request/response DTOs live locally
in this router rather than in app.schemas.

Cost totals -- defined precisely here so every screen that shows spend
agrees with every other:

  * quoted_pence      = sum(amount_pence) over this case's QUOTE entries.
  * invoiced_pence    = sum(amount_pence) over this case's INVOICE entries.
  * adjustments_pence = sum(amount_pence) over this case's ADJUSTMENT
    entries (signed -- a correction can be negative or positive).
  * net_pence         = invoiced_pence + adjustments_pence. The actual
    money figure: quotes are estimates and are never counted as spend.
  * committed_pence   = the best current estimate of what this case will
    cost. QUOTE/INVOICE entries are grouped by work_order_id (entries with
    no work_order_id all share one "case-level" group). Per group: if it
    has at least one INVOICE, that group contributes its invoice total
    (the real figure supersedes the estimate); otherwise it contributes its
    quote total. committed_pence is the sum of every group's contribution.
    ADJUSTMENT entries are not part of this figure -- they correct
    net_pence, not a commitment estimate.

This endpoint is already scoped to one case, so `items`/`totals` include
every cost row on that case, including any synthetic archival ones (each
row's `is_archived` says which) -- there is no narrower "operational
default" subset to exclude within a single case's own ledger. The house
rule to exclude archival rows "from operational defaults" applies to
cross-case/cross-subject aggregates (the case list, dashboard counts, the
messages thread list) rather than to a detail view already scoped to one
case; a case that is itself archival simply has every one of its cost rows
carry the same archive_batch_id, and totals here are honest about that via
is_archived, not silently zeroed.
"""
from __future__ import annotations

import collections
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.api.deps import get_session, require_operator
from app.domain.errors import ConflictError, DomainError, NotFoundError
from app.domain.services import load_case, load_work_order
from app.models import CostEntryModel, new_uuid, utcnow
from app.schemas import CostKind, ReadModel, StrictModel

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])


class CostEntryRecord(ReadModel):
    id: UUID
    case_id: UUID
    work_order_id: UUID | None = None
    kind: CostKind
    amount_pence: int
    description: str
    incurred_at: datetime
    recorded_by: str
    recorded_at: datetime
    is_archived: bool


class CostTotals(StrictModel):
    quoted_pence: int
    invoiced_pence: int
    adjustments_pence: int
    net_pence: int
    committed_pence: int


class CostListResponse(StrictModel):
    items: list[CostEntryRecord]
    totals: CostTotals


def _check_description(value: str | None) -> str | None:
    if value is not None and not value.strip():
        raise ValueError("description must not be empty")
    return value


class CostCreateRequest(StrictModel):
    work_order_id: str | None = None
    kind: CostKind
    amount_pence: int
    description: str
    incurred_at: datetime

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        return _check_description(value)


class CostUpdateRequest(StrictModel):
    work_order_id: str | None = None
    kind: CostKind | None = None
    amount_pence: int | None = None
    description: str | None = None
    incurred_at: datetime | None = None

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str | None) -> str | None:
        return _check_description(value)


def _to_record(cost: CostEntryModel) -> CostEntryRecord:
    return CostEntryRecord(
        id=cost.id, case_id=cost.case_id, work_order_id=cost.work_order_id, kind=cost.kind,
        amount_pence=cost.amount_pence, description=cost.description, incurred_at=cost.incurred_at,
        recorded_by=cost.recorded_by, recorded_at=cost.recorded_at, is_archived=cost.archive_batch_id is not None,
    )


def _compute_totals(rows: list[CostEntryModel]) -> CostTotals:
    quoted = sum(r.amount_pence for r in rows if r.kind == CostKind.QUOTE)
    invoiced = sum(r.amount_pence for r in rows if r.kind == CostKind.INVOICE)
    adjustments = sum(r.amount_pence for r in rows if r.kind == CostKind.ADJUSTMENT)
    net = invoiced + adjustments

    groups: dict[str | None, dict[str, int]] = collections.defaultdict(lambda: {"quote": 0, "invoice": 0})
    for r in rows:
        if r.kind == CostKind.QUOTE:
            groups[r.work_order_id]["quote"] += r.amount_pence
        elif r.kind == CostKind.INVOICE:
            groups[r.work_order_id]["invoice"] += r.amount_pence
    committed = sum((g["invoice"] if g["invoice"] else g["quote"]) for g in groups.values())

    return CostTotals(
        quoted_pence=quoted, invoiced_pence=invoiced, adjustments_pence=adjustments,
        net_pence=net, committed_pence=committed,
    )


def _validate_amount(kind: CostKind, amount_pence: int) -> None:
    if amount_pence == 0:
        raise DomainError("amount_pence must be non-zero")
    if kind in (CostKind.QUOTE, CostKind.INVOICE) and amount_pence <= 0:
        raise DomainError(f"{kind.value} amount_pence must be positive")


def _validate_incurred_at(incurred_at: datetime) -> None:
    if incurred_at > datetime.now(timezone.utc):
        raise DomainError("incurred_at cannot be in the future")


@router.get("/cases/{case_id}/costs")
async def list_costs(case_id: str, session: AsyncSession = Depends(get_session)) -> CostListResponse:
    await load_case(session, case_id)
    rows = (
        await session.execute(
            select(CostEntryModel).where(CostEntryModel.case_id == case_id).order_by(CostEntryModel.incurred_at.desc())
        )
    ).scalars().all()
    return CostListResponse(items=[_to_record(r) for r in rows], totals=_compute_totals(rows))


@router.post("/cases/{case_id}/costs", status_code=201)
async def create_cost(
    case_id: str, request: CostCreateRequest, operator: str = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> CostEntryRecord:
    case = await load_case(session, case_id)
    if case.archive_batch_id is not None:
        raise ConflictError(f"case {case_id} is archival; costs cannot be added to it")
    if request.work_order_id is not None:
        await load_work_order(session, case_id, request.work_order_id)
    _validate_amount(request.kind, request.amount_pence)
    _validate_incurred_at(request.incurred_at)

    cost = CostEntryModel(
        id=new_uuid(), case_id=case_id, work_order_id=request.work_order_id, kind=request.kind,
        amount_pence=request.amount_pence, description=request.description, incurred_at=request.incurred_at,
        recorded_by=operator, recorded_at=utcnow(),
    )
    session.add(cost)
    await session.flush()
    return _to_record(cost)


@router.patch("/costs/{cost_id}")
async def update_cost(cost_id: str, request: CostUpdateRequest, session: AsyncSession = Depends(get_session)) -> CostEntryRecord:
    cost = await session.get(CostEntryModel, cost_id)
    if cost is None:
        raise NotFoundError(f"cost entry {cost_id} not found")
    if cost.archive_batch_id is not None:
        raise ConflictError(f"cost entry {cost_id} is archival and cannot be edited")

    new_kind = request.kind if request.kind is not None else cost.kind
    new_amount = request.amount_pence if request.amount_pence is not None else cost.amount_pence
    if request.kind is not None or request.amount_pence is not None:
        _validate_amount(new_kind, new_amount)
    if request.work_order_id is not None:
        await load_work_order(session, cost.case_id, request.work_order_id)
    new_incurred_at = request.incurred_at if request.incurred_at is not None else cost.incurred_at
    if request.incurred_at is not None:
        _validate_incurred_at(new_incurred_at)

    if request.work_order_id is not None:
        cost.work_order_id = request.work_order_id
    cost.kind = new_kind
    cost.amount_pence = new_amount
    if request.description is not None:
        cost.description = request.description
    cost.incurred_at = new_incurred_at
    await session.flush()
    return _to_record(cost)


@router.delete("/costs/{cost_id}", status_code=204)
async def delete_cost(cost_id: str, session: AsyncSession = Depends(get_session)) -> Response:
    cost = await session.get(CostEntryModel, cost_id)
    if cost is None:
        raise NotFoundError(f"cost entry {cost_id} not found")
    if cost.archive_batch_id is not None:
        raise ConflictError(f"cost entry {cost_id} is archival and cannot be deleted")
    await session.delete(cost)
    await session.flush()
    return Response(status_code=204)
