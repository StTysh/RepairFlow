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
from app.domain.errors import NotFoundError
from app.integrations.booking import mock_booking_connector
from app.models import (
    AvailabilityWindowModel,
    CaseEventModel,
    CommunicationModel,
    ContractorCandidateModel,
    ContractorReportModel,
    ResearchSnapshotModel,
)
from app.schemas import (
    AppointmentOptions,
    AppointmentQuery,
    CaseEvent,
    Communication,
    ContractorCandidate,
    ContractorReport,
    ContractorSearchResult,
    ReadEvents,
    RecordRef,
    ResearchSnapshot,
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


async def read_research(ctx: RunContext[CoordinatorDeps], ref: RecordRef) -> ContractorSearchResult:
    """Reads a completed DISCOVER_CONTRACTORS result: the ResearchSnapshot
    plus every UNVERIFIED ContractorCandidate it produced. A candidate here
    is web evidence, never an approved contractor -- the coordinator must
    not treat verification_status as anything other than UNVERIFIED from
    this tool alone (docs/12, CLAUDE.md)."""
    _check_scope(ctx.deps, ref.case_id)
    async with session_scope() as session:
        snapshot = await session.get(ResearchSnapshotModel, str(ref.record_id))
        if snapshot is None or snapshot.case_id != ctx.deps.case_id:
            raise ModelRetry(f"no research {ref.record_id} found in this case")
        candidates = (
            await session.execute(
                select(ContractorCandidateModel).where(ContractorCandidateModel.research_id == snapshot.id)
            )
        ).scalars().all()
        return ContractorSearchResult(
            research=ResearchSnapshot.model_validate(snapshot),
            candidates=[ContractorCandidate.model_validate(c) for c in candidates],
        )


async def find_appointment_options(ctx: RunContext[CoordinatorDeps], query: AppointmentQuery) -> AppointmentOptions:
    _check_scope(ctx.deps, query.case_id)
    async with session_scope() as session:
        # The other four tools all raise ModelRetry on not-found, which
        # pydantic_ai turns into a cheap in-run re-prompt. load_work_order
        # instead raises NotFoundError (a plain DomainError) -- uncaught,
        # that aborts the whole run and burns a full COORDINATE retry (a
        # fresh Gemini call) on what should just be a stale ID the model
        # can self-correct from. Same bug class as tonight's earlier
        # UsageLimits fix.
        try:
            work_order = await services.load_work_order(session, ctx.deps.case_id, str(query.work_order_id))
        except NotFoundError:
            raise ModelRetry(f"no work order {query.work_order_id} found in this case; use only IDs from the supplied case snapshot")

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
