"""Tenant directory API (list/create/read/update).

Request/response Pydantic models live in this file rather than
app.schemas -- see the module docstring in app/api/properties.py for why.

Archival note: TenantModel has no `archive_batch_id` column of its own
(unlike PropertyModel/RepairCaseModel). A tenant's archival-ness is
derived transitively from the property it lives at: an archive-import
property's tenants are themselves synthetic sample data, so
`is_archived` here reads `PropertyModel.archive_batch_id` for the
tenant's `property_id`. This is a one-FK-hop derivation, not a new
signal -- see backend/app/api/NEEDS_FROM_ROOT_directories.md.
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain.errors import ConflictError, NotFoundError
from app.models import PropertyModel, RepairCaseModel, TenantModel, new_uuid
from app.schemas import CaseStatus

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])

_E164_RE = re.compile(r"^\+\d{8,15}$")
_OPEN_CASE_STATUSES = [CaseStatus.ACTIVE.value, CaseStatus.AWAITING_CONFIRMATION.value, CaseStatus.ESCALATED.value]


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)


class PropertySummary(_ResponseModel):
    id: str
    address_line: str
    postcode: str
    is_archived: bool


class TenantCaseSummary(_ResponseModel):
    id: str
    case_number: int
    title: str
    status: CaseStatus
    created_at: datetime
    # The profile's case list shows "Updated <when>"; without this it
    # rendered a permanent dash. created_at stays because "reported"
    # and "last touched" are different questions.
    updated_at: datetime
    is_archived: bool


class TenantListItem(_ResponseModel):
    id: str
    display_name: str
    property_id: str
    property_address: str
    phone_e164: str | None
    email: str | None
    preferred_channel: str
    contact_allowed: bool
    accessibility_notes: str | None
    open_case_count: int
    total_case_count: int
    is_archived: bool


class TenantListResponse(_ResponseModel):
    items: list[TenantListItem]
    limit: int
    offset: int
    total: int
    # Derived, not stored: the UI's pagination controls need to know
    # whether a Next button should exist, and computing offset+len(items)
    # < total in three separate screens is how they drift apart.
    has_more: bool


class TenantDetail(TenantListItem):
    property: PropertySummary
    cases: list[TenantCaseSummary]


class TenantCreateRequest(_RequestModel):
    property_id: str
    display_name: str = Field(min_length=1)
    phone_e164: str | None = None
    email: str | None = None
    preferred_channel: str = "VOICE"
    contact_allowed: bool = True
    accessibility_notes: str | None = None

    @field_validator("display_name")
    @classmethod
    def _display_name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("display_name cannot be blank")
        return v

    @field_validator("phone_e164")
    @classmethod
    def _phone_shape(cls, v: str | None) -> str | None:
        if v is not None and not _E164_RE.match(v):
            raise ValueError("phone_e164 must be E.164-shaped: '+' then 8-15 digits")
        return v


class TenantUpdateRequest(_RequestModel):
    display_name: str | None = None
    phone_e164: str | None = None
    email: str | None = None
    preferred_channel: str | None = None
    contact_allowed: bool | None = None
    accessibility_notes: str | None = None
    property_id: str | None = None

    @field_validator("display_name")
    @classmethod
    def _display_name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("display_name cannot be blank")
        return v

    @field_validator("phone_e164")
    @classmethod
    def _phone_shape(cls, v: str | None) -> str | None:
        if v is not None and not _E164_RE.match(v):
            raise ValueError("phone_e164 must be E.164-shaped: '+' then 8-15 digits")
        return v


def _list_item(tenant: TenantModel, property_address: str, property_archived: bool, open_count: int, total_count: int) -> TenantListItem:
    return TenantListItem(
        id=tenant.id, display_name=tenant.display_name, property_id=tenant.property_id,
        property_address=property_address, phone_e164=tenant.phone_e164, email=tenant.email,
        preferred_channel=tenant.preferred_channel, contact_allowed=tenant.contact_allowed,
        accessibility_notes=tenant.accessibility_notes, open_case_count=open_count,
        total_case_count=total_count, is_archived=property_archived,
    )


def _open_case_count_subquery():
    return (
        select(func.count(RepairCaseModel.id))
        .where(
            RepairCaseModel.tenant_id == TenantModel.id,
            RepairCaseModel.archive_batch_id.is_(None),
            RepairCaseModel.status.in_(_OPEN_CASE_STATUSES),
        )
        .correlate(TenantModel)
        .scalar_subquery()
    )


def _total_case_count_subquery():
    return (
        select(func.count(RepairCaseModel.id))
        .where(RepairCaseModel.tenant_id == TenantModel.id)
        .correlate(TenantModel)
        .scalar_subquery()
    )


async def _case_counts(session: AsyncSession, tenant_id: str) -> tuple[int, int]:
    open_count = (
        await session.execute(
            select(func.count(RepairCaseModel.id)).where(
                RepairCaseModel.tenant_id == tenant_id,
                RepairCaseModel.archive_batch_id.is_(None),
                RepairCaseModel.status.in_(_OPEN_CASE_STATUSES),
            )
        )
    ).scalar_one()
    total_count = (
        await session.execute(select(func.count(RepairCaseModel.id)).where(RepairCaseModel.tenant_id == tenant_id))
    ).scalar_one()
    return open_count, total_count


async def _tenant_detail(session: AsyncSession, tenant: TenantModel) -> TenantDetail:
    prop = await session.get(PropertyModel, tenant.property_id)
    property_archived = prop is not None and prop.archive_batch_id is not None
    open_count, total_count = await _case_counts(session, tenant.id)
    item = _list_item(tenant, prop.address_line if prop else "", property_archived, open_count, total_count)

    cases = (
        await session.execute(
            select(RepairCaseModel).where(RepairCaseModel.tenant_id == tenant.id).order_by(RepairCaseModel.created_at.desc())
        )
    ).scalars().all()
    case_summaries = [
        TenantCaseSummary(
            id=c.id, case_number=c.case_number, title=c.title, status=c.status,
            created_at=c.created_at, updated_at=c.updated_at,
            is_archived=c.archive_batch_id is not None,
        )
        for c in cases
    ]
    return TenantDetail(
        **item.model_dump(),
        property=PropertySummary(
            id=prop.id, address_line=prop.address_line, postcode=prop.postcode, is_archived=property_archived,
        ) if prop is not None else PropertySummary(id=tenant.property_id, address_line="", postcode="", is_archived=False),
        cases=case_summaries,
    )


@router.get("/tenants")
async def list_tenants(
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = None,
    property_id: str | None = None,
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> TenantListResponse:
    filters = []
    if property_id is not None:
        filters.append(TenantModel.property_id == property_id)
    if q:
        like = f"%{q}%"
        filters.append(or_(TenantModel.display_name.like(like), TenantModel.email.like(like)))
    if not include_archived:
        filters.append(PropertyModel.archive_batch_id.is_(None))

    total = (
        await session.execute(
            select(func.count()).select_from(
                select(TenantModel.id).join(PropertyModel, PropertyModel.id == TenantModel.property_id).where(*filters).subquery()
            )
        )
    ).scalar_one()

    query = (
        select(
            TenantModel, PropertyModel.address_line, PropertyModel.archive_batch_id,
            _open_case_count_subquery(), _total_case_count_subquery(),
        )
        .join(PropertyModel, PropertyModel.id == TenantModel.property_id)
        .where(*filters)
        .order_by(TenantModel.display_name, TenantModel.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(query)).all()

    items = [
        _list_item(tenant, address_line, prop_archive_batch_id is not None, open_n, total_n)
        for tenant, address_line, prop_archive_batch_id, open_n, total_n in rows
    ]
    return TenantListResponse(
        items=items, limit=limit, offset=offset, total=total,
        has_more=offset + len(items) < total,
    )


@router.post("/tenants", status_code=201)
async def create_tenant(request: TenantCreateRequest, session: AsyncSession = Depends(get_session)) -> TenantListItem:
    prop = await session.get(PropertyModel, request.property_id)
    if prop is None:
        raise NotFoundError(f"property {request.property_id} not found")

    tenant = TenantModel(
        id=new_uuid(), property_id=request.property_id, display_name=request.display_name,
        phone_e164=request.phone_e164, email=request.email, preferred_channel=request.preferred_channel,
        contact_allowed=request.contact_allowed, accessibility_notes=request.accessibility_notes,
    )
    session.add(tenant)
    await session.flush()
    return _list_item(tenant, prop.address_line, prop.archive_batch_id is not None, 0, 0)


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str, session: AsyncSession = Depends(get_session)) -> TenantDetail:
    tenant = await session.get(TenantModel, tenant_id)
    if tenant is None:
        raise NotFoundError(f"tenant {tenant_id} not found")
    return await _tenant_detail(session, tenant)


@router.patch("/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, request: TenantUpdateRequest, session: AsyncSession = Depends(get_session)) -> TenantDetail:
    tenant = await session.get(TenantModel, tenant_id)
    if tenant is None:
        raise NotFoundError(f"tenant {tenant_id} not found")
    current_property = await session.get(PropertyModel, tenant.property_id)
    if current_property is not None and current_property.archive_batch_id is not None:
        raise ConflictError("this tenant lives at an archival sample property and cannot be edited")

    updates = request.model_dump(exclude_unset=True)
    if "property_id" in updates:
        new_property = await session.get(PropertyModel, updates["property_id"])
        if new_property is None:
            raise NotFoundError(f"property {updates['property_id']} not found")
    for field, value in updates.items():
        setattr(tenant, field, value)
    await session.flush()
    return await _tenant_detail(session, tenant)
