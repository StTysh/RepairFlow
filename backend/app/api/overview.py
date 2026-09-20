"""GET /overview -- portfolio landing data (docs/16-adjacent; added for the
analytics/reporting phase). Thin router: every number comes from
app.analytics; this file only parses query params and shapes the response.
Operational scope only (CLAUDE.md's archival-exclusion rule) -- there is no
include_archived parameter here, and every figure returned is honestly zero
when there is nothing operational to show.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import analytics
from app.api.deps import get_session, require_operator
from app.domain import services

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])


class AttentionItemResponse(BaseModel):
    case_id: str
    case_number: int
    case_title: str
    reason: str
    detail: str
    occurred_at: datetime


class ActivityItemResponse(BaseModel):
    event_id: str
    case_id: str
    case_number: int
    case_title: str
    event_type: str
    occurred_at: datetime


class OpenAgeBucketResponse(BaseModel):
    label: str
    count: int


class UpcomingAppointmentSummary(BaseModel):
    appointment_id: str
    case_id: str
    case_number: int
    case_title: str
    property_address: str
    contractor_id: str
    contractor_name: str
    start_at: datetime
    end_at: datetime


class StatusCountsResponse(BaseModel):
    active: int
    awaiting_confirmation: int
    resolved: int
    escalated: int
    cancelled: int
    total: int


class OverviewResponse(BaseModel):
    property_count: int
    tenant_count: int
    approved_contractor_count: int
    status_counts: StatusCountsResponse
    open_age_buckets: list[OpenAgeBucketResponse]
    needs_attention: list[AttentionItemResponse]
    upcoming_appointments: list[UpcomingAppointmentSummary]
    recent_activity: list[ActivityItemResponse]


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    attention_limit: int = Query(default=20, ge=1, le=100),
    upcoming_limit: int = Query(default=10, ge=1, le=50),
    activity_limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> OverviewResponse:
    portfolio = await analytics.portfolio_counts(session)
    status_counts = await analytics.operational_status_counts(session)
    age_buckets = await analytics.open_age_buckets(session)
    attention = await analytics.needs_attention(session, limit=attention_limit)
    activity = await analytics.recent_activity(session, limit=activity_limit)
    # Reuses the existing canonical "upcoming appointments" query
    # (domain/services.py, already the single source for this used by
    # GET /api/v1/appointments/upcoming) rather than re-deriving it here --
    # duplicating that join would risk the two views disagreeing about
    # which appointments qualify.
    upcoming = await services.load_upcoming_appointments(session, limit=upcoming_limit)

    return OverviewResponse(
        property_count=portfolio.property_count,
        tenant_count=portfolio.tenant_count,
        approved_contractor_count=portfolio.approved_contractor_count,
        status_counts=StatusCountsResponse(**dataclasses.asdict(status_counts)),
        open_age_buckets=[OpenAgeBucketResponse(**dataclasses.asdict(b)) for b in age_buckets],
        needs_attention=[
            AttentionItemResponse(
                case_id=a.case_id, case_number=a.case_number, case_title=a.case_title, reason=a.reason,
                detail=a.detail, occurred_at=a.occurred_at,
            )
            for a in attention
        ],
        upcoming_appointments=[
            UpcomingAppointmentSummary(
                appointment_id=str(a.appointment_id), case_id=str(a.case_id), case_number=a.case_number,
                case_title=a.case_title, property_address=a.property_address,
                contractor_id=str(a.contractor_id), contractor_name=a.contractor_name,
                start_at=a.start_at, end_at=a.end_at,
            )
            for a in upcoming
        ],
        recent_activity=[
            ActivityItemResponse(
                event_id=a.event_id, case_id=a.case_id, case_number=a.case_number, case_title=a.case_title,
                event_type=a.event_type, occurred_at=a.occurred_at,
            )
            for a in activity
        ],
    )
