"""GET /search -- global search across cases, properties, tenants and
contractors. Read-only lookups, not aggregates, so this doesn't route
through app.analytics (there is no metric to keep consistent here) but it
stays behind the same operator auth and the same "thin router" discipline.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.models import ContractorModel, PropertyModel, RepairCaseModel, TenantModel

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])

MIN_QUERY_LENGTH = 2
GROUP_CAP = 8


class SearchResultItem(BaseModel):
    type: str
    id: str
    label: str
    sublabel: str
    route: str
    # Only ever true for a case/property row imported by the synthetic
    # archive batch (RepairCaseModel.archive_batch_id /
    # PropertyModel.archive_batch_id). Tenants and contractors carry no
    # archive_batch_id of their own (see PortfolioCounts in app/analytics.py
    # for the same distinction), so this is always False for those two
    # result types.
    is_archived: bool = False


class SearchGroup(BaseModel):
    type: str
    items: list[SearchResultItem]
    has_more: bool


class SearchResponse(BaseModel):
    query: str
    groups: list[SearchGroup]


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(default=""), session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    query_text = q.strip()
    if len(query_text) < MIN_QUERY_LENGTH:
        # Below the minimum length: return empty, not the whole dataset --
        # a stray keystroke must never dump every case/property/tenant.
        return SearchResponse(query=query_text, groups=[])

    like = f"%{query_text}%"
    groups: list[SearchGroup] = []

    case_filter = RepairCaseModel.title.like(like)
    if query_text.isdigit():
        case_filter = or_(case_filter, RepairCaseModel.case_number == int(query_text))
    else:
        case_filter = or_(case_filter, cast(RepairCaseModel.case_number, String).like(like))
    case_rows = (
        await session.execute(
            select(RepairCaseModel)
            .where(case_filter)
            .order_by(RepairCaseModel.updated_at.desc())
            .limit(GROUP_CAP + 1)
        )
    ).scalars().all()
    groups.append(
        SearchGroup(
            type="case",
            has_more=len(case_rows) > GROUP_CAP,
            items=[
                SearchResultItem(
                    type="case", id=c.id, label=f"#{c.case_number} {c.title}",
                    sublabel=c.status.value if hasattr(c.status, "value") else c.status,
                    route=f"/maintenance/tickets/{c.id}",
                    is_archived=c.archive_batch_id is not None,
                )
                for c in case_rows[:GROUP_CAP]
            ],
        )
    )

    property_rows = (
        await session.execute(
            select(PropertyModel)
            .where(or_(PropertyModel.address_line.like(like), PropertyModel.postcode.like(like)))
            .order_by(PropertyModel.address_line.asc())
            .limit(GROUP_CAP + 1)
        )
    ).scalars().all()
    groups.append(
        SearchGroup(
            type="property",
            has_more=len(property_rows) > GROUP_CAP,
            items=[
                SearchResultItem(
                    type="property", id=p.id, label=p.address_line, sublabel=p.postcode,
                    route=f"/properties/{p.id}/history",
                    is_archived=p.archive_batch_id is not None,
                )
                for p in property_rows[:GROUP_CAP]
            ],
        )
    )

    tenant_rows = (
        await session.execute(
            select(TenantModel, PropertyModel.address_line, PropertyModel.id)
            .join(PropertyModel, PropertyModel.id == TenantModel.property_id)
            .where(or_(TenantModel.display_name.like(like), TenantModel.email.like(like)))
            .order_by(TenantModel.display_name.asc())
            .limit(GROUP_CAP + 1)
        )
    ).all()
    groups.append(
        SearchGroup(
            type="tenant",
            has_more=len(tenant_rows) > GROUP_CAP,
            items=[
                SearchResultItem(
                    type="tenant", id=t.id, label=t.display_name, sublabel=t.email or address_line,
                    # No dedicated tenant-detail page exists yet -- link to
                    # the property's history view, the closest real record.
                    route=f"/properties/{property_id}/history",
                )
                for t, address_line, property_id in tenant_rows[:GROUP_CAP]
            ],
        )
    )

    contractor_rows = (
        await session.execute(
            select(ContractorModel)
            .where(ContractorModel.display_name.like(like))
            .order_by(ContractorModel.display_name.asc())
            .limit(GROUP_CAP + 1)
        )
    ).scalars().all()
    groups.append(
        SearchGroup(
            type="contractor",
            has_more=len(contractor_rows) > GROUP_CAP,
            items=[
                SearchResultItem(
                    type="contractor", id=c.id, label=c.display_name,
                    sublabel=", ".join(c.trades) if c.trades else c.approval_status.value if hasattr(c.approval_status, "value") else str(c.approval_status),
                    route=f"/contractors/{c.id}",
                )
                for c in contractor_rows[:GROUP_CAP]
            ],
        )
    )

    return SearchResponse(query=query_text, groups=groups)
