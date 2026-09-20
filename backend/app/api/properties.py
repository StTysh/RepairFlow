"""Property directory API (list/create/read/update).

Request/response Pydantic models live in this file rather than
app.schemas: three agents are editing this codebase in parallel this
phase and schemas.py has a single owner (see CLAUDE.md's "Expected
structure" note), so each directory router keeps its own shapes.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain.errors import ConflictError, NotFoundError
from app.models import PropertyModel, RepairCaseModel, TenantModel, new_uuid
from app.schemas import CaseStatus, RoofResponsibility

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])

# Loose-but-not-blank UK postcode shape: 1-2 letters, a digit, an optional
# letter/digit, whitespace, a digit, two letters. Rejects obviously
# malformed input without pretending to validate against the real Royal
# Mail postcode file (out of scope for an MVP directory form).
_POSTCODE_RE = re.compile(r"^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$")

# A case counts toward a property's/tenant's *current workload* only if it
# is both non-archival and not in a terminal CaseStatus (docs/07's state
# machine: RESOLVED and CANCELLED have no further outgoing edges other
# than an explicit reopen, which is a deliberate separate action).
_OPEN_CASE_STATUSES = [CaseStatus.ACTIVE.value, CaseStatus.AWAITING_CONFIRMATION.value, CaseStatus.ESCALATED.value]


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)


class TenantSummary(_ResponseModel):
    id: str
    display_name: str
    contact_allowed: bool


class PropertyListItem(_ResponseModel):
    id: str
    address_line: str
    postcode: str
    landlord_reference: str
    property_type: str | None
    bedrooms: int | None
    build_year: int | None
    photo_key: str | None
    timezone: str
    roof_responsibility: RoofResponsibility
    access_notes: str | None
    is_archived: bool
    open_case_count: int
    total_case_count: int
    tenant_count: int


class PropertyListResponse(_ResponseModel):
    items: list[PropertyListItem]
    limit: int
    offset: int
    total: int
    # Derived, not stored: the UI's pagination controls need to know
    # whether a Next button should exist, and computing offset+len(items)
    # < total in three separate screens is how they drift apart.
    has_more: bool


class PropertyDetail(PropertyListItem):
    tenants: list[TenantSummary]


class PropertyCreateRequest(_RequestModel):
    address_line: str = Field(min_length=1)
    postcode: str
    landlord_reference: str = Field(min_length=1)
    timezone: str = "Europe/London"
    roof_responsibility: RoofResponsibility = RoofResponsibility.UNKNOWN
    access_notes: str | None = None
    build_year: int | None = None
    property_type: str | None = None
    bedrooms: int | None = None
    photo_key: str | None = None

    @field_validator("address_line")
    @classmethod
    def _address_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("address_line cannot be blank")
        return v

    @field_validator("postcode")
    @classmethod
    def _postcode_shape(cls, v: str) -> str:
        if not _POSTCODE_RE.match(v.strip()):
            raise ValueError("postcode is not a recognisable UK postcode shape")
        return v.strip().upper()

    @field_validator("bedrooms")
    @classmethod
    def _bedrooms_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("bedrooms must be >= 0")
        return v

    @field_validator("build_year")
    @classmethod
    def _build_year_plausible(cls, v: int | None) -> int | None:
        if v is not None and not (1000 <= v <= datetime.now(timezone.utc).year):
            raise ValueError("build_year is out of plausible range")
        return v


class PropertyUpdateRequest(_RequestModel):
    address_line: str | None = None
    postcode: str | None = None
    timezone: str | None = None
    landlord_reference: str | None = None
    roof_responsibility: RoofResponsibility | None = None
    access_notes: str | None = None
    build_year: int | None = None
    property_type: str | None = None
    bedrooms: int | None = None
    photo_key: str | None = None

    @field_validator("address_line")
    @classmethod
    def _address_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("address_line cannot be blank")
        return v

    @field_validator("postcode")
    @classmethod
    def _postcode_shape(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _POSTCODE_RE.match(v.strip()):
            raise ValueError("postcode is not a recognisable UK postcode shape")
        return v.strip().upper()

    @field_validator("bedrooms")
    @classmethod
    def _bedrooms_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("bedrooms must be >= 0")
        return v

    @field_validator("build_year")
    @classmethod
    def _build_year_plausible(cls, v: int | None) -> int | None:
        if v is not None and not (1000 <= v <= datetime.now(timezone.utc).year):
            raise ValueError("build_year is out of plausible range")
        return v


def _open_case_count_subquery():
    return (
        select(func.count(RepairCaseModel.id))
        .where(
            RepairCaseModel.property_id == PropertyModel.id,
            RepairCaseModel.archive_batch_id.is_(None),
            RepairCaseModel.status.in_(_OPEN_CASE_STATUSES),
        )
        .correlate(PropertyModel)
        .scalar_subquery()
    )


def _total_case_count_subquery():
    return (
        select(func.count(RepairCaseModel.id))
        .where(RepairCaseModel.property_id == PropertyModel.id)
        .correlate(PropertyModel)
        .scalar_subquery()
    )


def _tenant_count_subquery():
    return (
        select(func.count(TenantModel.id))
        .where(TenantModel.property_id == PropertyModel.id)
        .correlate(PropertyModel)
        .scalar_subquery()
    )


def _list_item(prop: PropertyModel, open_count: int, total_count: int, tenant_count: int) -> PropertyListItem:
    return PropertyListItem(
        id=prop.id, address_line=prop.address_line, postcode=prop.postcode,
        landlord_reference=prop.landlord_reference, property_type=prop.property_type,
        bedrooms=prop.bedrooms, build_year=prop.build_year, photo_key=prop.photo_key,
        timezone=prop.timezone, roof_responsibility=prop.roof_responsibility,
        access_notes=prop.access_notes, is_archived=prop.archive_batch_id is not None,
        open_case_count=open_count, total_case_count=total_count, tenant_count=tenant_count,
    )


async def _property_detail(session: AsyncSession, prop: PropertyModel) -> PropertyDetail:
    tenants = (
        await session.execute(
            select(TenantModel).where(TenantModel.property_id == prop.id).order_by(TenantModel.display_name)
        )
    ).scalars().all()
    open_count = (
        await session.execute(
            select(func.count(RepairCaseModel.id)).where(
                RepairCaseModel.property_id == prop.id,
                RepairCaseModel.archive_batch_id.is_(None),
                RepairCaseModel.status.in_(_OPEN_CASE_STATUSES),
            )
        )
    ).scalar_one()
    total_count = (
        await session.execute(
            select(func.count(RepairCaseModel.id)).where(RepairCaseModel.property_id == prop.id)
        )
    ).scalar_one()
    item = _list_item(prop, open_count, total_count, len(tenants))
    return PropertyDetail(
        **item.model_dump(),
        tenants=[TenantSummary(id=t.id, display_name=t.display_name, contact_allowed=t.contact_allowed) for t in tenants],
    )


@router.get("/properties")
async def list_properties(
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = None,
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> PropertyListResponse:
    filters = []
    if not include_archived:
        filters.append(PropertyModel.archive_batch_id.is_(None))
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                PropertyModel.address_line.like(like),
                PropertyModel.postcode.like(like),
                PropertyModel.landlord_reference.like(like),
            )
        )

    total = (
        await session.execute(
            select(func.count()).select_from(select(PropertyModel.id).where(*filters).subquery())
        )
    ).scalar_one()

    query = (
        select(PropertyModel, _open_case_count_subquery(), _total_case_count_subquery(), _tenant_count_subquery())
        .where(*filters)
        .order_by(PropertyModel.address_line, PropertyModel.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(query)).all()
    items = [_list_item(prop, open_n, total_n, tenant_n) for prop, open_n, total_n, tenant_n in rows]
    return PropertyListResponse(
        items=items, limit=limit, offset=offset, total=total,
        has_more=offset + len(items) < total,
    )


@router.post("/properties", status_code=201)
async def create_property(request: PropertyCreateRequest, session: AsyncSession = Depends(get_session)) -> PropertyListItem:
    prop = PropertyModel(
        id=new_uuid(), address_line=request.address_line, postcode=request.postcode,
        landlord_reference=request.landlord_reference, timezone=request.timezone,
        roof_responsibility=request.roof_responsibility, access_notes=request.access_notes,
        build_year=request.build_year, property_type=request.property_type,
        bedrooms=request.bedrooms, photo_key=request.photo_key,
    )
    session.add(prop)
    await session.flush()
    return _list_item(prop, 0, 0, 0)


@router.get("/properties/{property_id}")
async def get_property(property_id: str, session: AsyncSession = Depends(get_session)) -> PropertyDetail:
    prop = await session.get(PropertyModel, property_id)
    if prop is None:
        raise NotFoundError(f"property {property_id} not found")
    return await _property_detail(session, prop)


@router.patch("/properties/{property_id}")
async def update_property(
    property_id: str, request: PropertyUpdateRequest, session: AsyncSession = Depends(get_session)
) -> PropertyDetail:
    prop = await session.get(PropertyModel, property_id)
    if prop is None:
        raise NotFoundError(f"property {property_id} not found")
    if prop.archive_batch_id is not None:
        raise ConflictError("this property is an archival sample record and cannot be edited")

    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(prop, field, value)
    await session.flush()
    return await _property_detail(session, prop)
