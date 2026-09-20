"""GET /reports/summary and GET /reports/export.csv.

Both build from the exact same `app.analytics.case_detail_rows` call (via
`_load_report`) for their row-level detail, and the same aggregate
app.analytics functions for their totals -- that shared code path is what
guarantees the CSV export and the summary endpoint can never disagree for
the same filters (see test_analytics_api.py's export/summary reconciliation
test). GET /reports/print is rendered by the frontend and does not belong
here.
"""
from __future__ import annotations

import csv
import dataclasses
import io
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from app import analytics
from app.api.deps import get_session, require_operator
from app.schemas import Trade

router = APIRouter(prefix="/api/v1/reports", dependencies=[Depends(require_operator)])

_DEFAULT_WINDOW_DAYS = 730


def _window(date_from: date | None, date_to: date | None) -> tuple[datetime, datetime]:
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


@dataclasses.dataclass(frozen=True)
class _ReportData:
    date_from: datetime
    date_to: datetime
    include_archived: bool
    archived_case_count: int
    rows: list["analytics.CaseDetailRow"]
    category_breakdown: list["analytics.CategoryCount"]
    spend_by_year: list["analytics.YearSpend"]
    resolution: "analytics.ResolutionTimeDistribution"
    recurring: list["analytics.RecurringIssueGroup"]


async def _load_report(
    session: AsyncSession, *, date_from: date | None, date_to: date | None, property_id: str | None,
    category: Trade | None, include_archived: bool,
) -> _ReportData:
    """The one query set behind both /reports/summary and
    /reports/export.csv -- see this module's docstring."""
    start, end = _window(date_from, date_to)
    rows = await analytics.case_detail_rows(
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
    return _ReportData(
        date_from=start, date_to=end, include_archived=include_archived, archived_case_count=archived_count,
        rows=rows, category_breakdown=categories, spend_by_year=spend, resolution=resolution, recurring=recurring,
    )


class CaseDetailRowResponse(BaseModel):
    case_id: str
    case_number: int
    title: str
    status: str
    category: str | None
    property_address: str
    created_at: datetime
    closed_at: datetime | None
    resolution_hours: float | None
    quoted_pence: int
    invoiced_pence: int
    contractor_name: str | None
    record_source: str


def _row_response(row: "analytics.CaseDetailRow") -> CaseDetailRowResponse:
    return CaseDetailRowResponse(
        case_id=row.case_id, case_number=row.case_number, title=row.title,
        status=row.status.value if hasattr(row.status, "value") else row.status,
        category=(row.category.value if row.category else None),
        property_address=row.property_address, created_at=row.created_at, closed_at=row.closed_at,
        resolution_hours=row.resolution_hours, quoted_pence=row.quoted_pence, invoiced_pence=row.invoiced_pence,
        contractor_name=row.contractor_name,
        record_source="archival-sample" if row.is_archived else "operational",
    )


class MaintenanceSummary(BaseModel):
    total_cases: int
    resolved_cases: int
    open_cases: int
    category_breakdown: list[dict]


class SpendSummary(BaseModel):
    quoted_pence: int
    actual_pence: int
    by_year: list[dict]


class ResolutionSummary(BaseModel):
    average_hours: float | None
    median_hours: float | None
    sample_count: int
    skipped_count: int
    buckets: list[dict]


class RecurringSummary(BaseModel):
    groups: list[dict]


class ReportsSummaryResponse(BaseModel):
    date_from: datetime
    date_to: datetime
    includes_archived_history: bool
    archived_case_count: int
    maintenance: MaintenanceSummary
    spend: SpendSummary
    resolution: ResolutionSummary
    recurring: RecurringSummary
    rows: list[CaseDetailRowResponse]


@router.get("/summary", response_model=ReportsSummaryResponse)
async def reports_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    property_id: str | None = None,
    category: Trade | None = None,
    include_archived: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> ReportsSummaryResponse:
    data = await _load_report(
        session, date_from=date_from, date_to=date_to, property_id=property_id, category=category,
        include_archived=include_archived,
    )
    total_cases = len(data.rows)
    resolved_cases = sum(1 for r in data.rows if analytics.case_is_resolved(r.status))
    open_cases = sum(1 for r in data.rows if not r.is_archived and analytics.case_is_open(r.status))
    quoted_total = sum(s.quoted_pence for s in data.spend_by_year)
    actual_total = sum(s.actual_pence for s in data.spend_by_year)

    return ReportsSummaryResponse(
        date_from=data.date_from, date_to=data.date_to, includes_archived_history=data.include_archived,
        archived_case_count=data.archived_case_count,
        maintenance=MaintenanceSummary(
            total_cases=total_cases, resolved_cases=resolved_cases, open_cases=open_cases,
            category_breakdown=[dataclasses.asdict(c) for c in data.category_breakdown],
        ),
        spend=SpendSummary(
            quoted_pence=quoted_total, actual_pence=actual_total,
            by_year=[dataclasses.asdict(s) for s in data.spend_by_year],
        ),
        resolution=ResolutionSummary(
            average_hours=data.resolution.average_hours, median_hours=data.resolution.median_hours,
            sample_count=data.resolution.sample_count, skipped_count=data.resolution.skipped_count,
            buckets=[{"label": label, "count": count} for label, count in data.resolution.buckets],
        ),
        recurring=RecurringSummary(groups=[dataclasses.asdict(r) for r in data.recurring]),
        rows=[_row_response(r) for r in data.rows],
    )


@router.get("/export.csv")
async def reports_export_csv(
    date_from: date | None = None,
    date_to: date | None = None,
    property_id: str | None = None,
    category: Trade | None = None,
    include_archived: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    data = await _load_report(
        session, date_from=date_from, date_to=date_to, property_id=property_id, category=category,
        include_archived=include_archived,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "case_number", "property", "category", "status", "created_at", "closed_at",
        "resolution_hours", "quoted_pence", "invoiced_pence", "contractor", "record_source",
    ])
    for row in data.rows:
        writer.writerow([
            row.case_number,
            row.property_address,
            row.category.value if row.category else "",
            row.status.value if hasattr(row.status, "value") else row.status,
            row.created_at.isoformat(),
            row.closed_at.isoformat() if row.closed_at else "",
            row.resolution_hours if row.resolution_hours is not None else "",
            row.quoted_pence,
            row.invoiced_pence,
            row.contractor_name or "",
            "archival-sample" if row.is_archived else "operational",
        ])
    csv_text = buffer.getvalue()
    filename = f"repairflow-report_{data.date_from.date().isoformat()}_to_{data.date_to.date().isoformat()}.csv"
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
