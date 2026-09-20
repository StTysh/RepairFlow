"""GET /insights and GET /insights/cases -- portfolio analytics behind the
Insights screen. Thin router: filters are parsed here, every figure comes
from app.analytics, and the drill-down endpoint serves the exact
`app.analytics.case_detail_rows` rows so every chart element can link to
its supporting records.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from app import analytics
from app.api.deps import get_session, require_operator
from app.schemas import CaseStatus, Trade

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])

_DEFAULT_WINDOW_DAYS = 730  # ~24 months, per docs/16 filter default


def _window(date_from: date | None, date_to: date | None) -> tuple[datetime, datetime]:
    """Turns the (optional) inclusive calendar-date query params into a
    [start, end) UTC datetime window. Default: the last 24 months ending
    now. `date_to` is treated as inclusive of that whole calendar day."""
    now = datetime.now(timezone.utc)
    if date_from is None and date_to is None:
        return now - timedelta(days=_DEFAULT_WINDOW_DAYS), now
    end = (
        datetime.combine(date_to, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
        if date_to is not None else now
    )
    start = (
        datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
        if date_from is not None else end - timedelta(days=_DEFAULT_WINDOW_DAYS)
    )
    return start, end


class MonthVolumeResponse(BaseModel):
    year: int
    month: int
    count: int


class CategoryBreakdownResponse(BaseModel):
    category: Trade | None
    count: int
    percentage: int


class YearSpendResponse(BaseModel):
    year: int
    quoted_pence: int
    actual_pence: int


class ResolutionBucketResponse(BaseModel):
    label: str
    count: int


class ResolutionDistributionResponse(BaseModel):
    buckets: list[ResolutionBucketResponse]
    average_hours: float | None
    median_hours: float | None
    sample_count: int
    skipped_count: int


class RecurringIssueResponse(BaseModel):
    property_id: str
    property_address: str
    category: Trade
    count: int
    last_occurred_at: datetime
    case_ids: list[str]


class PeriodComparisonResponse(BaseModel):
    current: float
    previous: float
    change_pct: float | None
    is_new: bool


class InsightsResponse(BaseModel):
    date_from: datetime
    date_to: datetime
    includes_archived_history: bool
    archived_case_count: int
    case_volume_by_month: list[MonthVolumeResponse]
    category_breakdown: list[CategoryBreakdownResponse]
    spend_by_year: list[YearSpendResponse]
    resolution: ResolutionDistributionResponse
    recurring_issues: list[RecurringIssueResponse]
    # Case-volume comparison of the requested window against the
    # immediately preceding window of equal length (docs task spec).
    case_volume_comparison: PeriodComparisonResponse


@router.get("/insights", response_model=InsightsResponse)
async def get_insights(
    date_from: date | None = None,
    date_to: date | None = None,
    property_id: str | None = None,
    category: Trade | None = None,
    include_archived: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> InsightsResponse:
    start, end = _window(date_from, date_to)
    window_length = end - start
    previous_start, previous_end = start - window_length, start

    volume = await analytics.case_volume_by_month(
        session, property_id=property_id, category=category, date_from=start, date_to=end,
        include_archived=include_archived,
    )
    categories = await analytics.category_breakdown(
        session, property_id=property_id, date_from=start, date_to=end, include_archived=include_archived,
    )
    spend = await analytics.spend_by_year(
        session, property_id=property_id, category=category, date_from=start, date_to=end,
        include_archived=include_archived,
    )
    resolution = await analytics.resolution_time_distribution(
        session, property_id=property_id, category=category, date_from=start, date_to=end,
        include_archived=include_archived,
    )
    recurring = await analytics.recurring_issues(
        session, property_id=property_id, date_from=start, date_to=end, include_archived=include_archived,
    )
    archived_count = (
        await analytics.archived_case_count(session, property_id=property_id, category=category, date_from=start, date_to=end)
        if include_archived else 0
    )

    previous_volume = await analytics.case_volume_by_month(
        session, property_id=property_id, category=category, date_from=previous_start, date_to=previous_end,
        include_archived=include_archived,
    )
    current_total = sum(m.count for m in volume)
    previous_total = sum(m.count for m in previous_volume)
    comparison = analytics.period_comparison(current_total, previous_total)

    return InsightsResponse(
        date_from=start, date_to=end, includes_archived_history=include_archived,
        archived_case_count=archived_count,
        case_volume_by_month=[MonthVolumeResponse(**dataclasses.asdict(m)) for m in volume],
        category_breakdown=[CategoryBreakdownResponse(**dataclasses.asdict(c)) for c in categories],
        spend_by_year=[YearSpendResponse(**dataclasses.asdict(s)) for s in spend],
        resolution=ResolutionDistributionResponse(
            buckets=[ResolutionBucketResponse(label=label, count=count) for label, count in resolution.buckets],
            average_hours=resolution.average_hours, median_hours=resolution.median_hours,
            sample_count=resolution.sample_count, skipped_count=resolution.skipped_count,
        ),
        recurring_issues=[RecurringIssueResponse(**dataclasses.asdict(r)) for r in recurring],
        case_volume_comparison=PeriodComparisonResponse(
            current=comparison.current, previous=comparison.previous,
            change_pct=comparison.change_pct, is_new=comparison.is_new,
        ),
    )


class CaseDetailRowResponse(BaseModel):
    case_id: str
    case_number: int
    title: str
    status: CaseStatus
    category: Trade | None
    property_id: str
    property_address: str
    created_at: datetime
    closed_at: datetime | None
    resolution_hours: float | None
    quoted_pence: int
    invoiced_pence: int
    contractor_name: str | None
    is_archived: bool


class InsightsCasesResponse(BaseModel):
    date_from: datetime
    date_to: datetime
    total: int
    items: list[CaseDetailRowResponse]


@router.get("/insights/cases", response_model=InsightsCasesResponse)
async def get_insights_cases(
    date_from: date | None = None,
    date_to: date | None = None,
    property_id: str | None = None,
    category: Trade | None = None,
    status: CaseStatus | None = None,
    include_archived: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> InsightsCasesResponse:
    """Drill-down: the actual case rows behind any Insights filter
    combination, so a chart bar/slice/point can link straight to its
    supporting records. Same underlying query (`case_detail_rows`) as
    /reports/summary and /reports/export.csv."""
    start, end = _window(date_from, date_to)
    rows = await analytics.case_detail_rows(
        session, property_id=property_id, category=category, status=status, date_from=start, date_to=end,
        include_archived=include_archived, limit=limit,
    )
    items = [
        CaseDetailRowResponse(
            case_id=r.case_id, case_number=r.case_number, title=r.title, status=r.status, category=r.category,
            property_id=r.property_id, property_address=r.property_address, created_at=r.created_at,
            closed_at=r.closed_at, resolution_hours=r.resolution_hours, quoted_pence=r.quoted_pence,
            invoiced_pence=r.invoiced_pence, contractor_name=r.contractor_name, is_archived=r.is_archived,
        )
        for r in rows
    ]
    return InsightsCasesResponse(date_from=start, date_to=end, total=len(items), items=items)
