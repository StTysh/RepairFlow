"""Scoped read tools exposed to the coordinator agent (docs/10).

Every tool re-validates that the requested record belongs to the case in
`RunContext.deps` -- dependency injection supplies scope, it does not by
itself enforce it (docs/09). `get_case_snapshot` is not registered: the
full snapshot is already the run's prompt content (docs/10).
"""
from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext
from sqlalchemy import select

from app.agents.dependencies import CoordinatorDeps
from app.db import session_scope
from app.domain import services
from app.integrations.booking import mock_booking_connector
from app.models import AvailabilityWindowModel, CaseEventModel, CommunicationModel, ContractorReportModel
from app.schemas import (
    AppointmentOptions,
    AppointmentQuery,
    CaseEvent,
    Communication,
    ContractorReport,
    ReadEvents,
    RecordRef,
)


def _check_scope(deps: CoordinatorDeps, case_id) -> None:
    if str(case_id) != deps.case_id:
        raise ModelRetry("that record is not part of the current case; use only IDs from the supplied case snapshot")


async def read_report(ctx: RunContext[CoordinatorDeps], ref: RecordRef) -> ContractorReport:
    _check_scope(ctx.deps, ref.case_id)
    async with session_scope() as session:
        report = await session.get(ContractorReportModel, str(ref.record_id))
        if report is None or report.case_id != ctx.deps.case_id:
            raise ModelRetry(f"no report {ref.record_id} found in this case")
        return ContractorReport.model_validate(report)


async def read_communication(ctx: RunContext[CoordinatorDeps], ref: RecordRef) -> Communication:
    _check_scope(ctx.deps, ref.case_id)
    async with session_scope() as session:
        comm = await session.get(CommunicationModel, str(ref.record_id))
        if comm is None or comm.case_id != ctx.deps.case_id:
            raise ModelRetry(f"no communication {ref.record_id} found in this case")
        model = Communication.model_validate(comm)
        model.recording.media_path = None  # never expose the audio file path to the model
        return model


async def list_case_events(ctx: RunContext[CoordinatorDeps], query: ReadEvents) -> list[CaseEvent]:
    _check_scope(ctx.deps, query.case_id)
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(CaseEventModel)
                .where(CaseEventModel.case_id == ctx.deps.case_id, CaseEventModel.seq > query.after_seq)
                .order_by(CaseEventModel.seq)
                .limit(min(query.limit, 100))
            )
        ).scalars().all()
        return [CaseEvent.model_validate(e) for e in rows]


async def find_appointment_options(ctx: RunContext[CoordinatorDeps], query: AppointmentQuery) -> AppointmentOptions:
    _check_scope(ctx.deps, query.case_id)
    async with session_scope() as session:
        work_order = await services.load_work_order(session, ctx.deps.case_id, str(query.work_order_id))

        windows = (
            await session.execute(
                select(AvailabilityWindowModel).where(
                    AvailabilityWindowModel.case_id == ctx.deps.case_id,
                    AvailabilityWindowModel.id.in_([str(i) for i in query.tenant_availability_ids]),
                )
            )
        ).scalars().all()
        if not windows:
            return AppointmentOptions(slots=[], reason_if_empty="no matching tenant availability window in this case")

        slots = await mock_booking_connector.list_slots(session, query, trade=work_order.trade)

    valid = [
        s for s in slots
        if any(w.start_at <= s.start_at and s.end_at <= w.end_at for w in windows)
    ]
    if not valid:
        return AppointmentOptions(slots=[], reason_if_empty="no contractor slot intersects the cited availability")
    return AppointmentOptions(slots=valid)
