"""Dashboard summary counts for the operator UI (docs/16-adjacent; added for
the Fixi UI integration phase). Deliberately derived only from the 5 real
CaseStatus values and from CASE_RESOLVED CaseEvents -- no derived/richer
display-status taxonomy, per the project's status-simplification decision.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain import services
from app.models import CaseEventModel, JobModel, OrchestrationRunModel, RepairCaseModel
from app.schemas import CaseStatus, DashboardMetricsResponse

router = APIRouter(prefix="/api/v1/metrics", dependencies=[Depends(require_operator)])


@router.get("/dashboard")
async def dashboard_metrics(session: AsyncSession = Depends(get_session)) -> DashboardMetricsResponse:
    status_rows = (
        await session.execute(select(RepairCaseModel.status, func.count()).group_by(RepairCaseModel.status))
    ).all()
    counts: dict[str, int] = {status.value: 0 for status in CaseStatus}
    for status, count in status_rows:
        key = status.value if hasattr(status, "value") else status
        counts[key] = count

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    resolved_this_week = (
        await session.execute(
            select(func.count(func.distinct(CaseEventModel.case_id))).where(
                CaseEventModel.type == "CASE_RESOLVED", CaseEventModel.occurred_at >= week_ago,
            )
        )
    ).scalar_one()

    # Honest "is the agent doing anything right now" signal, not a fake
    # spinner: true if any job is due/leased (coordinate, place a call,
    # fetch a recording, ...) or a coordinator run is mid-flight.
    has_pending_job = (
        await session.execute(select(JobModel.id).where(JobModel.status.in_(["PENDING", "LEASED"])).limit(1))
    ).scalar_one_or_none()
    has_running_run = (
        await session.execute(select(OrchestrationRunModel.id).where(OrchestrationRunModel.state == "RUNNING").limit(1))
    ).scalar_one_or_none()

    avg_resolution_hours = await services.average_resolution_hours(session)

    # See services.reconstructed_status_counts for exactly what "7 days
    # ago" means (a documented simplification, not a literal replay).
    historical = await services.reconstructed_status_counts(session, week_ago)

    return DashboardMetricsResponse(
        active=counts[CaseStatus.ACTIVE.value],
        awaiting_confirmation=counts[CaseStatus.AWAITING_CONFIRMATION.value],
        resolved=counts[CaseStatus.RESOLVED.value],
        escalated=counts[CaseStatus.ESCALATED.value],
        cancelled=counts[CaseStatus.CANCELLED.value],
        total=sum(counts.values()),
        resolved_this_week=resolved_this_week,
        agent_active=bool(has_pending_job or has_running_run),
        avg_resolution_hours=avg_resolution_hours,
        active_delta_pct=services.delta_pct(counts[CaseStatus.ACTIVE.value], historical["ACTIVE"]),
        awaiting_confirmation_delta_pct=services.delta_pct(
            counts[CaseStatus.AWAITING_CONFIRMATION.value], historical["AWAITING_CONFIRMATION"]
        ),
        escalated_delta_pct=services.delta_pct(counts[CaseStatus.ESCALATED.value], historical["ESCALATED"]),
    )
