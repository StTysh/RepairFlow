"""Checked domain transactions. Each function here is one "command" from
docs/10_TOOL_CATALOG.md: it mutates the session it is given and returns a
CommandResult, but does not itself commit — the caller (API route or
orchestration worker) owns the transaction boundary via db.session_scope().

Two-phase external actions (SCHEDULE_VISIT, DISCOVER_CONTRACTORS) are split
into a `prepare_*` (validates + reads, still local) and `apply_*_result`
(writes the provider outcome) pair; orchestration/executor.py calls the
provider between the two, outside any open transaction.
"""
from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import dependencies as dep_graph
from app.domain import policy
from app.domain.errors import ConflictError, NotFoundError, PolicyRejectedError
from app.domain.transitions import assert_case_transition, assert_work_order_transition
from app.models import (
    AppointmentModel,
    AvailabilityWindowModel,
    CaseEventModel,
    CommunicationModel,
    ContractorReportModel,
    DependencyModel,
    JobModel,
    RepairCaseModel,
    RepairIssueModel,
    WorkOrderModel,
    new_uuid,
)
from app.schemas import (
    AcceptReport,
    AddPrerequisite,
    ApplyTriage,
    AvailabilityInput,
    BookingOutcome,
    BookingStatus,
    CallOutcomeStatus,
    CaseStatus,
    CommandResult,
    CommandResultStatus,
    CommPurpose,
    Escalate,
    EvidenceRef,
    FactInput,
    IntakeSubmission,
    JobKind,
    JobStatus,
    ObservationSubmission,
    PersonType,
    Provenance,
    ReportSubmission,
    RequestConfirmation,
    RequestInformation,
    ResolveCase,
    RiskAssessment,
    SourceType,
    Trade,
    Wait,
    WorkOrderKind,
    WorkOrderStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclasses.dataclass(frozen=True)
class ActorContext:
    actor_type: str
    actor_id: str
    correlation_id: str


def evidence_ref_dict(source_type: SourceType, source_id: str, provenance: Provenance, locator: str | None = None, observed_at: datetime | None = None) -> dict:
    return EvidenceRef(
        source_type=source_type,
        source_id=source_id,
        locator=locator,
        observed_at=observed_at or utcnow(),
        provenance=provenance,
    ).model_dump(mode="json")


async def next_seq(session: AsyncSession, case_id: str) -> int:
    current_max = (
        await session.execute(select(func.max(CaseEventModel.seq)).where(CaseEventModel.case_id == case_id))
    ).scalar_one_or_none()
    return (current_max or 0) + 1


async def append_event(
    session: AsyncSession,
    *,
    case_id: str,
    event_type,
    payload: dict,
    actor: ActorContext,
    source_event_key: str,
    causation_event_id: str | None = None,
    provenance: Provenance = Provenance.LIVE,
    occurred_at: datetime | None = None,
) -> CaseEventModel:
    event = CaseEventModel(
        id=new_uuid(),
        case_id=case_id,
        seq=await next_seq(session, case_id),
        type=event_type.value if hasattr(event_type, "value") else event_type,
        occurred_at=occurred_at or utcnow(),
        received_at=utcnow(),
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_event_key=source_event_key,
        correlation_id=actor.correlation_id,
        causation_event_id=causation_event_id,
        payload=payload,
        provenance=provenance,
    )
    session.add(event)
    await session.flush()
    return event


def bump_version(case: RepairCaseModel) -> None:
    case.version += 1
    case.updated_at = utcnow()


async def enqueue_job(
    session: AsyncSession, *, case_id: str | None, kind: JobKind, dedupe_key: str, payload: dict, run_at: datetime | None = None
) -> JobModel | None:
    existing = (
        await session.execute(select(JobModel).where(JobModel.dedupe_key == dedupe_key))
    ).scalar_one_or_none()
    if existing is not None:
        return None
    job = JobModel(
        id=new_uuid(),
        case_id=case_id,
        kind=kind,
        dedupe_key=dedupe_key,
        payload=payload,
        run_at=run_at or utcnow(),
        status=JobStatus.PENDING,
    )
    try:
        # A SAVEPOINT (session.begin_nested), not the caller's own ambient
        # transaction, around the add+flush. This repo runs one worker
        # process (CLAUDE.md), but that only rules out worker-vs-worker
        # contention -- two concurrent API requests can still both compute
        # the same dedupe_key (e.g. two overlapping webhook deliveries
        # each calling enqueue_job with `coordinate:{case_id}:{version}`)
        # and both pass the SELECT above before either has committed.
        # jobs.dedupe_key is UNIQUE (models.py), so the loser's flush
        # trips that constraint. Without a savepoint, the failed INSERT
        # would leave the *caller's* whole session_scope transaction
        # unusable (SQLAlchemy requires a rollback before a session can be
        # used again after a failed flush) -- turning a benign dedupe race
        # into an unrelated 500 for whatever else that request's
        # transaction was doing.
        #
        # `job` is deliberately added to the session *inside* the nested
        # block, not before it: entering begin_nested() unconditionally
        # flushes whatever is already pending, to give the SAVEPOINT a
        # clean baseline (SQLAlchemy docs). Adding `job` first would put
        # its INSERT inside that pre-savepoint flush, which runs before
        # the SAVEPOINT actually exists at the database level -- a
        # conflict there fails outside of anything this function can roll
        # back, defeating the whole point of the savepoint.
        async with session.begin_nested():
            session.add(job)
            await session.flush()
    except IntegrityError:
        # Someone else's job for this key won the race and is already
        # committed (or about to be) -- exactly the "a job for this key
        # already exists" outcome this function promises its callers via
        # the SELECT above, just discovered the hard way. The failed
        # nested transaction already expires/evicts whatever it added on
        # rollback (SQLAlchemy's begin_nested() contract), so `job` is
        # typically gone from the session already; `in` (not a bare
        # expunge()) guards the case where it somehow is not, so a later
        # flush/commit on this same session never re-attempts its insert.
        if job in session:
            session.expunge(job)
        return None
    return job


async def next_case_number(session: AsyncSession) -> int:
    """Allocates the next human-readable case_number as
    SELECT COALESCE(MAX(case_number), 0) + 1 inside the caller's existing
    transaction, then relies on RepairCaseModel's `uq_case_number` UNIQUE
    constraint as the actual correctness guarantee.

    Why not a dedicated counter row with its own UPDATE statement: that
    still needs the same UNIQUE constraint as a backstop (demo_reset()
    deletes case rows, so a counter table would need its own reset-aware
    bookkeeping or it would hand out numbers a deleted case already used --
    MAX()+1 self-heals against that for free). Why not a retry loop: this
    function is called mid-way through a larger multi-statement transaction
    (submit_intake also creates the issue row, availability windows, etc.),
    and a failed flush here would poison that whole transaction, not just
    this statement.

    Concurrency note for SQLite: this repo runs one worker process, but two
    concurrent HTTP requests can still race between this SELECT and the
    caller's later INSERT while both are on separate connections/transactions
    (SQLite does not take a write lock on a plain SELECT, so there is a real
    TOCTOU window here, not just a theoretical one). Accepted tradeoff for a
    one-process SQLite MVP: the loser's INSERT trips the UNIQUE constraint
    and that single request fails with a clear DB error instead of silently
    handing out a duplicate case_number. If concurrent-create volume ever
    matters, replace this with an atomic single-statement counter row
    (UPDATE counter SET value = value + 1 ...), which SQLite does serialize
    correctly because the write lock is taken by that statement itself.
    """
    current_max = (
        await session.execute(select(func.max(RepairCaseModel.case_number)))
    ).scalar_one_or_none() or 0
    return current_max + 1


async def load_case(session: AsyncSession, case_id: str) -> RepairCaseModel:
    case = await session.get(RepairCaseModel, case_id)
    if case is None:
        raise NotFoundError(f"case {case_id} not found")
    return case


async def load_issue(session: AsyncSession, case_id: str) -> RepairIssueModel:
    issue = (
        await session.execute(select(RepairIssueModel).where(RepairIssueModel.case_id == case_id))
    ).scalar_one_or_none()
    if issue is None:
        raise NotFoundError(f"issue for case {case_id} not found")
    return issue


async def load_work_order(session: AsyncSession, case_id: str, work_order_id: str) -> WorkOrderModel:
    wo = await session.get(WorkOrderModel, work_order_id)
    if wo is None or wo.case_id != case_id:
        raise NotFoundError(f"work order {work_order_id} not in case {case_id}")
    return wo


async def load_report(session: AsyncSession, case_id: str, report_id: str) -> ContractorReportModel:
    report = await session.get(ContractorReportModel, report_id)
    if report is None or report.case_id != case_id:
        raise NotFoundError(f"report {report_id} not in case {case_id}")
    return report


# --------------------------------------------------------------------------
# Ingress commands
# --------------------------------------------------------------------------


async def submit_intake(
    session: AsyncSession, *, communication_id: str, submission: IntakeSubmission, actor: ActorContext
) -> tuple[str, CommandResult]:
    comm = await session.get(CommunicationModel, communication_id)
    if comm is None:
        raise NotFoundError(f"communication {communication_id} not found")
    if comm.case_id is not None:
        # Already bound: idempotent duplicate intake for the same communication.
        case = await load_case(session, comm.case_id)
        return comm.case_id, CommandResult(status=CommandResultStatus.NOOP, case_version=case.version)

    risk = RiskAssessment(
        urgency="UNKNOWN",
        gas=submission.safety_answers.gas,
        fire=submission.safety_answers.fire,
        water_near_electrics=submission.safety_answers.water_near_electrics,
        structural_danger=submission.safety_answers.structural_danger,
        uncontrolled_flood=submission.safety_answers.uncontrolled_flood,
        vulnerability_concern=submission.safety_answers.vulnerability_concern,
        evidence_refs=[evidence_ref_dict(SourceType.VOICE_TOOL, communication_id, Provenance.LIVE)],
    )

    case_id = new_uuid()
    case = RepairCaseModel(
        id=case_id,
        case_number=await next_case_number(session),
        property_id=str(submission.property_id),
        tenant_id=str(submission.tenant_id),
        status=CaseStatus.ACTIVE,
        version=1,
        title=submission.description[:255],
        risk=risk.model_dump(mode="json"),
        owner_operator_id="operator",
    )
    session.add(case)

    issue = RepairIssueModel(
        id=new_uuid(),
        case_id=case_id,
        description=submission.description,
        location=submission.location,
        started_at=submission.started_at,
        evidence_refs=[evidence_ref_dict(SourceType.VOICE_TOOL, communication_id, Provenance.LIVE)],
        unresolved_concerns=[],
    )
    session.add(issue)
    await session.flush()  # case/issue rows must exist before comm.case_id references them

    comm.case_id = case_id
    comm.tenant_id = str(submission.tenant_id)

    for window in submission.availability:
        await add_availability(session, case_id=case_id, person_type=PersonType.TENANT, person_id=str(submission.tenant_id), window=window, communication_id=communication_id)

    await session.flush()

    event = await append_event(
        session,
        case_id=case_id,
        event_type="CASE_CREATED",
        payload={"communication_id": communication_id},
        actor=actor,
        source_event_key=f"intake:{communication_id}",
    )
    await enqueue_job(
        session, case_id=case_id, kind=JobKind.COORDINATE, dedupe_key=f"coordinate:{case_id}:{case.version}",
        payload={"trigger_event_id": event.id},
    )

    return case_id, CommandResult(
        status=CommandResultStatus.APPLIED, case_version=case.version,
        event_ids=[event.id], resource_ids={"case_id": case_id, "issue_id": issue.id},
    )


async def add_availability(
    session: AsyncSession, *, case_id: str, person_type: PersonType, person_id: str, window: AvailabilityInput, communication_id: str
) -> AvailabilityWindowModel | None:
    existing = (
        await session.execute(
            select(AvailabilityWindowModel).where(
                AvailabilityWindowModel.case_id == case_id,
                AvailabilityWindowModel.person_id == person_id,
                AvailabilityWindowModel.start_at == window.start_at,
                AvailabilityWindowModel.end_at == window.end_at,
            )
        )
    ).scalars().first()
    if existing is not None:
        return None

    max_revision = (
        await session.execute(
            select(func.max(AvailabilityWindowModel.revision)).where(
                AvailabilityWindowModel.case_id == case_id, AvailabilityWindowModel.person_id == person_id
            )
        )
    ).scalar_one_or_none() or 0

    row = AvailabilityWindowModel(
        id=new_uuid(),
        case_id=case_id,
        person_type=person_type,
        person_id=person_id,
        start_at=window.start_at,
        end_at=window.end_at,
        timezone=window.timezone,
        confirmed_at=utcnow(),
        expires_at=window.end_at,
        source_ref=evidence_ref_dict(SourceType.VOICE_TOOL, communication_id, Provenance.LIVE, locator=window.spoken_text),
        revision=int(max_revision) + 1,
    )
    session.add(row)
    await session.flush()
    return row


async def record_observations(
    session: AsyncSession, *, case_id: str, communication_id: str, submission: ObservationSubmission, actor: ActorContext
) -> CommandResult:
    case = await load_case(session, case_id)
    issue = await load_issue(session, case_id)
    changed = False
    event_ids: list[str] = []

    risk = RiskAssessment.model_validate(case.risk)
    safety_fields = {
        "gas", "fire", "water_near_electrics", "structural_danger", "uncontrolled_flood", "vulnerability_concern",
    }

    for fact in submission.facts:
        if fact.field not in {
            "description", "location", "started_at", "unresolved_concern", *safety_fields,
        }:
            continue
        if fact.field == "description" and fact.value and fact.value != issue.description:
            issue.description = str(fact.value)
            changed = True
        elif fact.field == "location" and fact.value and fact.value != issue.location:
            issue.location = str(fact.value)
            changed = True
        elif fact.field == "started_at" and fact.value:
            try:
                parsed = datetime.fromisoformat(str(fact.value))
            except ValueError:
                pass
            else:
                if parsed.tzinfo is not None and parsed != issue.started_at:
                    issue.started_at = parsed
                    changed = True
        elif fact.field == "unresolved_concern" and fact.value:
            concern = str(fact.value)
            if concern not in issue.unresolved_concerns:
                issue.unresolved_concerns = [*issue.unresolved_concerns, concern]
                changed = True
        elif fact.field in safety_fields and fact.value is not None:
            current = getattr(risk, fact.field)
            if current.value != fact.value:
                setattr(risk, fact.field, fact.value)
                changed = True

    if changed:
        case.risk = risk.model_dump(mode="json")
        event = await append_event(
            session, case_id=case_id, event_type="INFORMATION_RECEIVED",
            payload={"communication_id": communication_id, "facts": [f.model_dump(mode="json") for f in submission.facts]},
            actor=actor, source_event_key=f"observations:{communication_id}:facts:{len(submission.facts)}:{utcnow().timestamp()}",
        )
        event_ids.append(event.id)

    availability_changed = False
    for window in submission.availability:
        created = await add_availability(
            session, case_id=case_id, person_type=PersonType.TENANT, person_id=case.tenant_id,
            window=window, communication_id=communication_id,
        )
        if created is not None:
            availability_changed = True
    if availability_changed:
        event = await append_event(
            session, case_id=case_id, event_type="AVAILABILITY_RECEIVED",
            payload={"communication_id": communication_id}, actor=actor,
            source_event_key=f"observations:{communication_id}:availability:{utcnow().timestamp()}",
        )
        event_ids.append(event.id)
        changed = True

    if submission.tenant_confirms_resolved is not None:
        if submission.tenant_confirms_resolved:
            issue.tenant_resolution_confirmed_at = utcnow()
        else:
            issue.tenant_resolution_confirmed_at = None
            if "tenant reports issue still unresolved" not in issue.unresolved_concerns:
                issue.unresolved_concerns = [*issue.unresolved_concerns, "tenant reports issue still unresolved"]
            if case.status == CaseStatus.AWAITING_CONFIRMATION:
                assert_case_transition(case.status, CaseStatus.ACTIVE)
                case.status = CaseStatus.ACTIVE
        event = await append_event(
            session, case_id=case_id, event_type="TENANT_CONFIRMATION_RECEIVED",
            payload={"communication_id": communication_id, "confirmed": submission.tenant_confirms_resolved},
            actor=actor, source_event_key=f"observations:{communication_id}:confirmation",
        )
        event_ids.append(event.id)
        changed = True

    if changed:
        bump_version(case)
        await enqueue_job(
            session, case_id=case_id, kind=JobKind.COORDINATE, dedupe_key=f"coordinate:{case_id}:{case.version}",
            payload={"trigger_event_id": event_ids[-1]},
        )

    return CommandResult(status=CommandResultStatus.APPLIED if changed else CommandResultStatus.NOOP, case_version=case.version, event_ids=event_ids)


async def record_contractor_report(
    session: AsyncSession, *, submission: ReportSubmission, source_ref: EvidenceRef, provenance: Provenance, actor: ActorContext
) -> tuple[str, CommandResult]:
    work_order = await session.get(WorkOrderModel, str(submission.work_order_id))
    if work_order is None:
        raise NotFoundError(f"work order {submission.work_order_id} not found")
    case_id = work_order.case_id
    appointment = await session.get(AppointmentModel, str(submission.appointment_id))
    if appointment is None or appointment.case_id != case_id:
        raise NotFoundError(f"appointment {submission.appointment_id} not in case {case_id}")

    existing = (
        await session.execute(
            select(ContractorReportModel).where(
                ContractorReportModel.appointment_id == str(submission.appointment_id),
                ContractorReportModel.text == submission.text,
                ContractorReportModel.observed_at == submission.observed_at,
            )
        )
    ).scalars().first()
    case = await load_case(session, case_id)
    if existing is not None:
        return existing.id, CommandResult(status=CommandResultStatus.NOOP, case_version=case.version, resource_ids={"report_id": existing.id})

    report = ContractorReportModel(
        id=new_uuid(),
        case_id=case_id,
        work_order_id=work_order.id,
        appointment_id=appointment.id,
        contractor_id=str(submission.contractor_id),
        text=submission.text,
        observed_at=submission.observed_at,
        source_ref=source_ref.model_dump(mode="json"),
        provenance=provenance,
    )
    session.add(report)
    await session.flush()

    # PENDING as well as CONFIRMED: a system-proposed booking is PENDING
    # (no contractor acknowledged it), and a report against it still
    # closes the visit. Only CONFIRMED used to qualify, which the mock
    # connector hid by always writing CONFIRMED.
    if appointment.status in ("CONFIRMED", "PENDING"):
        appointment.status = "FINISHED"
    if work_order.status in (WorkOrderStatus.SCHEDULED, WorkOrderStatus.IN_PROGRESS):
        assert_work_order_transition(work_order.status, WorkOrderStatus.AWAITING_REPORT)
        work_order.status = WorkOrderStatus.AWAITING_REPORT
        work_order.updated_at = utcnow()

    bump_version(case)
    event = await append_event(
        session, case_id=case_id, event_type="CONTRACTOR_REPORT_RECEIVED",
        payload={"report_id": report.id, "work_order_id": work_order.id},
        actor=actor, source_event_key=f"report:{report.id}",
    )
    await enqueue_job(
        session, case_id=case_id, kind=JobKind.COORDINATE, dedupe_key=f"coordinate:{case_id}:{case.version}",
        payload={"trigger_event_id": event.id},
    )
    return report.id, CommandResult(
        status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id],
        resource_ids={"report_id": report.id},
    )


# --------------------------------------------------------------------------
# Executor commands (local / atomic)
# --------------------------------------------------------------------------


async def apply_triage(session: AsyncSession, *, case_id: str, action: ApplyTriage, trigger_event_id: str, actor: ActorContext) -> CommandResult:
    case = await load_case(session, case_id)
    issue = await load_issue(session, case_id)

    if policy.is_hazard(action.risk):
        case.risk = action.risk.model_dump(mode="json")
        if case.status in (CaseStatus.ACTIVE, CaseStatus.AWAITING_CONFIRMATION):
            case.resume_status = case.status
            assert_case_transition(case.status, CaseStatus.ESCALATED)
            case.status = CaseStatus.ESCALATED
        case.escalation_reason = "Deterministic hazard gate: unsafe condition reported during triage."
        bump_version(case)
        event = await append_event(
            session, case_id=case_id, event_type="CASE_ESCALATED",
            payload={"reason": "hazard_in_triage", "risk": action.risk.model_dump(mode="json")},
            actor=actor, source_event_key=f"triage-hazard:{case_id}:{trigger_event_id}",
            causation_event_id=trigger_event_id,
        )
        return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id])

    case.risk = action.risk.model_dump(mode="json")
    if action.issue_description and action.issue_description != issue.description:
        issue.description = action.issue_description

    existing_wo = (
        await session.execute(
            select(WorkOrderModel).where(
                WorkOrderModel.issue_id == issue.id, WorkOrderModel.kind == WorkOrderKind.REPAIR,
            )
        )
    ).scalars().first()

    resource_ids: dict = {}
    if existing_wo is None:
        wo = WorkOrderModel(
            id=new_uuid(), case_id=case_id, issue_id=issue.id,
            kind=WorkOrderKind.REPAIR, trade=action.suggested_trade, scope=action.scope,
            status=WorkOrderStatus.READY, required_for_resolution=True,
            quote_pence=policy.default_quote_pence(WorkOrderKind.REPAIR),
            approved_limit_pence=policy.ORDINARY_AUTHORITY_LIMIT_PENCE,
        )
        session.add(wo)
        await session.flush()
        resource_ids["work_order_id"] = wo.id
        event_type = "WORK_ORDER_CREATED"
    elif existing_wo.trade != action.suggested_trade and existing_wo.status != WorkOrderStatus.READY:
        # Only record where to resume *to* if we are not already there.
        # Escalating an already-ESCALATED case used to set
        # resume_status = ESCALATED, so a later resume "succeeded" and
        # put the case straight back into escalation -- stranded, with a
        # success message. Keep the original pre-escalation status.
        if case.status != CaseStatus.ESCALATED:
            case.resume_status = case.status
        assert_case_transition(case.status, CaseStatus.ESCALATED)
        case.status = CaseStatus.ESCALATED
        case.escalation_reason = "Trade changed after dispatch; needs human review."
        bump_version(case)
        event = await append_event(
            session, case_id=case_id, event_type="CASE_ESCALATED",
            payload={"reason": "trade_changed_after_dispatch"}, actor=actor,
            source_event_key=f"triage-trade-change:{case_id}:{trigger_event_id}", causation_event_id=trigger_event_id,
        )
        return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id])
    else:
        existing_wo.trade = action.suggested_trade
        existing_wo.scope = action.scope
        resource_ids["work_order_id"] = existing_wo.id
        event_type = "INFORMATION_RECEIVED"

    bump_version(case)
    event = await append_event(
        session, case_id=case_id, event_type=event_type, payload={"scope": action.scope},
        actor=actor, source_event_key=f"triage:{case_id}:{trigger_event_id}", causation_event_id=trigger_event_id,
    )
    await enqueue_job(
        session, case_id=case_id, kind=JobKind.COORDINATE, dedupe_key=f"coordinate:{case_id}:{case.version}",
        payload={"trigger_event_id": event.id},
    )
    return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id], resource_ids=resource_ids)


async def add_prerequisite(session: AsyncSession, *, case_id: str, action: AddPrerequisite, action_id: str, trigger_event_id: str, actor: ActorContext) -> CommandResult:
    case = await load_case(session, case_id)
    report = await load_report(session, case_id, str(action.report_id))
    blocked_wo = await load_work_order(session, case_id, str(action.blocked_work_order_id))

    if report.work_order_id != blocked_wo.id:
        raise PolicyRejectedError("report does not match the work order it is said to block")

    existing_dep = (
        await session.execute(
            select(DependencyModel).where(
                DependencyModel.case_id == case_id,
                DependencyModel.discovered_from_report_id == report.id,
            )
        )
    ).scalars().first()
    if existing_dep is not None:
        return CommandResult(
            status=CommandResultStatus.NOOP, case_version=case.version,
            resource_ids={
                "dependency_id": existing_dep.id,
                "prerequisite_work_order_id": existing_dep.prerequisite_work_order_id,
            },
        )

    if blocked_wo.status not in (
        WorkOrderStatus.READY, WorkOrderStatus.SCHEDULED, WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.AWAITING_REPORT,
    ):
        raise PolicyRejectedError(f"work order {blocked_wo.id} cannot be blocked from status {blocked_wo.status}")

    prerequisite_wo = WorkOrderModel(
        id=new_uuid(), case_id=case_id, issue_id=blocked_wo.issue_id,
        kind=action.prerequisite_kind, trade=action.prerequisite_trade, scope=action.prerequisite_scope,
        status=WorkOrderStatus.READY, required_for_resolution=True,
        quote_pence=policy.default_quote_pence(action.prerequisite_kind), approved_limit_pence=None,
    )
    session.add(prerequisite_wo)
    await session.flush()

    if await dep_graph.would_create_cycle(session, case_id, prerequisite_wo.id, blocked_wo.id):
        raise PolicyRejectedError("adding this prerequisite would create a dependency cycle")

    edge_install_to_blocked = DependencyModel(
        id=new_uuid(), case_id=case_id, prerequisite_work_order_id=prerequisite_wo.id,
        dependent_work_order_id=blocked_wo.id, status="OPEN", reason=action.reason,
        discovered_from_report_id=report.id,
    )
    session.add(edge_install_to_blocked)

    removal_wo_id = None
    if action.prerequisite_kind == WorkOrderKind.SCAFFOLD_INSTALL:
        removal_wo = WorkOrderModel(
            id=new_uuid(), case_id=case_id, issue_id=blocked_wo.issue_id,
            kind=WorkOrderKind.SCAFFOLD_REMOVE, trade=Trade.SCAFFOLDING,
            scope=f"Remove scaffold installed for: {action.prerequisite_scope}",
            status=WorkOrderStatus.BLOCKED, required_for_resolution=True,
            quote_pence=policy.default_quote_pence(WorkOrderKind.SCAFFOLD_REMOVE), approved_limit_pence=None,
        )
        session.add(removal_wo)
        await session.flush()
        if await dep_graph.would_create_cycle(session, case_id, blocked_wo.id, removal_wo.id):
            raise PolicyRejectedError("adding scaffold removal would create a dependency cycle")
        edge_blocked_to_removal = DependencyModel(
            id=new_uuid(), case_id=case_id, prerequisite_work_order_id=blocked_wo.id,
            dependent_work_order_id=removal_wo.id, status="OPEN",
            reason="Scaffold must be removed after the roof work it enabled is complete.",
            discovered_from_report_id=report.id,
        )
        session.add(edge_blocked_to_removal)
        removal_wo_id = removal_wo.id

    assert_work_order_transition(blocked_wo.status, WorkOrderStatus.BLOCKED)
    blocked_wo.status = WorkOrderStatus.BLOCKED
    blocked_wo.updated_at = utcnow()
    report.interpretation_status = "APPLIED"
    report.interpreted_action_id = action_id

    bump_version(case)
    event = await append_event(
        session, case_id=case_id, event_type="DEPENDENCY_DISCOVERED",
        payload={
            "report_id": report.id, "prerequisite_work_order_id": prerequisite_wo.id,
            "blocked_work_order_id": blocked_wo.id, "removal_work_order_id": removal_wo_id,
        },
        actor=actor, source_event_key=f"report:{report.id}:prerequisite", causation_event_id=trigger_event_id,
    )
    await enqueue_job(
        session, case_id=case_id, kind=JobKind.COORDINATE, dedupe_key=f"coordinate:{case_id}:{case.version}",
        payload={"trigger_event_id": event.id},
    )
    resource_ids = {"prerequisite_work_order_id": prerequisite_wo.id, "dependency_id": edge_install_to_blocked.id}
    if removal_wo_id:
        resource_ids["removal_work_order_id"] = removal_wo_id
    return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id], resource_ids=resource_ids)


async def maybe_advance_to_awaiting_confirmation(session: AsyncSession, case: RepairCaseModel) -> None:
    if case.status != CaseStatus.ACTIVE:
        return
    required = (
        await session.execute(
            select(WorkOrderModel).where(WorkOrderModel.case_id == case.id, WorkOrderModel.required_for_resolution.is_(True))
        )
    ).scalars().all()
    if required and all(wo.status == WorkOrderStatus.COMPLETED for wo in required):
        assert_case_transition(case.status, CaseStatus.AWAITING_CONFIRMATION)
        case.status = CaseStatus.AWAITING_CONFIRMATION


async def accept_report(session: AsyncSession, *, case_id: str, action: AcceptReport, action_id: str, trigger_event_id: str, actor: ActorContext) -> CommandResult:
    case = await load_case(session, case_id)
    report = await load_report(session, case_id, str(action.report_id))
    work_order = await load_work_order(session, case_id, report.work_order_id)
    appointment = await session.get(AppointmentModel, report.appointment_id)

    if report.interpretation_status == "APPLIED" and work_order.completion_report_id == report.id:
        return CommandResult(status=CommandResultStatus.NOOP, case_version=case.version, resource_ids={"work_order_id": work_order.id})

    event_ids: list[str] = []
    resource_ids: dict = {"work_order_id": work_order.id}

    if action.outcome == "COMPLETED":
        assert_work_order_transition(work_order.status, WorkOrderStatus.COMPLETED)
        work_order.status = WorkOrderStatus.COMPLETED
        work_order.completion_report_id = report.id
        work_order.updated_at = utcnow()
        if appointment is not None:
            appointment.visit_outcome = "COMPLETED"

        satisfied_edges = (
            await session.execute(
                select(DependencyModel).where(
                    DependencyModel.case_id == case_id,
                    DependencyModel.prerequisite_work_order_id == work_order.id,
                    DependencyModel.status == "OPEN",
                )
            )
        ).scalars().all()

        completion_event = await append_event(
            session, case_id=case_id, event_type="WORK_ORDER_COMPLETED",
            payload={"work_order_id": work_order.id, "report_id": report.id},
            actor=actor, source_event_key=f"report:{report.id}:accept", causation_event_id=trigger_event_id,
        )
        event_ids.append(completion_event.id)

        newly_ready: list[str] = []
        for edge in satisfied_edges:
            edge.status = "SATISFIED"
            edge.satisfied_by_report_id = report.id
            edge.satisfied_at = utcnow()
            dependent = await load_work_order(session, case_id, edge.dependent_work_order_id)
            if await dep_graph.all_incoming_satisfied(session, case_id, dependent.id) and dependent.status == WorkOrderStatus.BLOCKED:
                assert_work_order_transition(dependent.status, WorkOrderStatus.READY)
                dependent.status = WorkOrderStatus.READY
                dependent.updated_at = utcnow()
                newly_ready.append(dependent.id)
                dep_event = await append_event(
                    session, case_id=case_id, event_type="DEPENDENCY_SATISFIED",
                    payload={"dependency_id": edge.id, "dependent_work_order_id": dependent.id},
                    actor=actor, source_event_key=f"dependency:{edge.id}:satisfied", causation_event_id=completion_event.id,
                )
                event_ids.append(dep_event.id)
        if newly_ready:
            resource_ids["first_newly_ready_work_order_id"] = newly_ready[0]

        await maybe_advance_to_awaiting_confirmation(session, case)
    else:
        assert_work_order_transition(work_order.status, WorkOrderStatus.READY)
        work_order.status = WorkOrderStatus.READY
        work_order.updated_at = utcnow()
        if appointment is not None:
            appointment.visit_outcome = action.outcome

    report.interpretation_status = "APPLIED"
    report.interpreted_action_id = action_id
    bump_version(case)
    await enqueue_job(
        session, case_id=case_id, kind=JobKind.COORDINATE, dedupe_key=f"coordinate:{case_id}:{case.version}",
        payload={"trigger_event_id": event_ids[-1] if event_ids else trigger_event_id},
    )
    return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=event_ids, resource_ids=resource_ids)


async def mark_attendance_window_ended(session: AsyncSession, *, case_id: str, appointment_id: str, actor: ActorContext) -> CommandResult:
    """docs/07: "SCHEDULED --> AWAITING_REPORT: Window ended" / "Request
    report; do not complete work." A real deployment would fire this from a
    due FOLLOW_UP job scheduled at the appointment's end time; the hero
    path itself never needs it (a report can normalize the same transition
    on arrival, docs/07), so it is reached only via demo simulation until a
    real timer is wired up."""
    from app.models import AppointmentModel

    case = await load_case(session, case_id)
    appointment = await session.get(AppointmentModel, appointment_id)
    if appointment is None or appointment.case_id != case_id:
        raise NotFoundError(f"appointment {appointment_id} not in case {case_id}")
    work_order = await load_work_order(session, case_id, appointment.work_order_id)

    if work_order.status not in (WorkOrderStatus.SCHEDULED, WorkOrderStatus.IN_PROGRESS):
        return CommandResult(status=CommandResultStatus.NOOP, case_version=case.version)

    assert_work_order_transition(work_order.status, WorkOrderStatus.AWAITING_REPORT)
    work_order.status = WorkOrderStatus.AWAITING_REPORT
    work_order.updated_at = utcnow()
    bump_version(case)
    event = await append_event(
        session, case_id=case_id, event_type="APPOINTMENT_WINDOW_ENDED",
        payload={"appointment_id": appointment_id, "work_order_id": work_order.id},
        actor=actor, source_event_key=f"window-ended:{appointment_id}",
    )
    await enqueue_job(
        session, case_id=case_id, kind=JobKind.COORDINATE, dedupe_key=f"coordinate:{case_id}:{case.version}",
        payload={"trigger_event_id": event.id},
    )
    return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id])


async def cancel_appointment(
    session: AsyncSession, *, appointment_id: str, reason: str, actor: ActorContext
) -> tuple[CancellationOutcome, int]:
    """Operator-initiated cancellation, used both standalone and as the
    first half of "reschedule" (decision: reschedule is never an in-place
    edit -- it's cancel, then a fresh ScheduleVisit proposal through the
    normal coordinator/policy/approval path, same as any other action).

    The work order that was SCHEDULED for this appointment goes back to
    READY ("cancellation confirmed" is a named edge in transitions.py's
    graph) and a COORDINATE job is enqueued, exactly like every other
    state-changing command in this module -- that enqueue *is* the "nudge"
    that lets the coordinator notice the work order is READY again with
    tenant availability still on file, and propose a new ScheduleVisit on
    its own. No separate "request reschedule" endpoint is needed; this
    function is what the previous version of the cancel route was missing.
    """
    from app.integrations.booking import mock_booking_connector
    from app.schemas import AppointmentStatus, CancellationOutcome, CancellationStatus

    appointment = await session.get(AppointmentModel, appointment_id)
    if appointment is None:
        raise NotFoundError(f"appointment {appointment_id} not found")
    case = await load_case(session, appointment.case_id)

    if appointment.status == AppointmentStatus.CANCELLED:
        outcome = CancellationOutcome(
            status=CancellationStatus.CANCELLED, provider_booking_id=appointment.provider_booking_id,
            provenance=appointment.provenance,
        )
        return outcome, case.version

    outcome = await mock_booking_connector.cancel(
        session, appointment.provider_booking_id or "", f"cancel:{appointment_id}"
    )
    if outcome.status == CancellationStatus.CANCELLED:
        appointment.status = AppointmentStatus.CANCELLED
        work_order = await session.get(WorkOrderModel, appointment.work_order_id)
        if work_order is not None and work_order.status == WorkOrderStatus.SCHEDULED:
            assert_work_order_transition(work_order.status, WorkOrderStatus.READY)
            work_order.status = WorkOrderStatus.READY
            # Nobody is currently committed to this work order once its
            # only visit is cancelled -- assigned_contractor is a "who's
            # attending" projection, not a history log (that's
            # PropertyHistoryItem.outcome's job). Clear it so the case list
            # and detail view stop showing a contractor for a visit that no
            # longer exists; a rebooking sets it again on confirmation.
            work_order.contractor_id = None
            work_order.updated_at = utcnow()
        bump_version(case)
        event = await append_event(
            session, case_id=case.id, event_type="APPOINTMENT_CANCELLED",
            payload={"appointment_id": appointment.id, "work_order_id": appointment.work_order_id, "reason": reason},
            actor=actor, source_event_key=f"appointment-cancel:{appointment.id}:{case.version}",
        )
        await enqueue_job(
            session, case_id=case.id, kind=JobKind.COORDINATE, dedupe_key=f"coordinate:{case.id}:{case.version}",
            payload={"trigger_event_id": event.id},
        )
    return outcome, case.version


async def request_information(session: AsyncSession, *, case_id: str, action: RequestInformation, elevenlabs_configured: bool, actor: ActorContext) -> CommandResult:
    case = await load_case(session, case_id)
    existing = (
        await session.execute(
            select(CommunicationModel).where(
                CommunicationModel.case_id == case_id, CommunicationModel.purpose == action.purpose,
                CommunicationModel.state.in_(["REQUESTED", "ACTIVE"]),
            )
        )
    ).scalars().first()
    if existing is not None:
        return CommandResult(status=CommandResultStatus.NOOP, case_version=case.version, resource_ids={"communication_id": existing.id})

    comm = CommunicationModel(
        id=new_uuid(), case_id=case_id, tenant_id=case.tenant_id if action.recipient == "TENANT" else None,
        purpose=action.purpose, direction="OUTBOUND" if action.recipient == "TENANT" else "BROWSER",
        correlation_token_hash=new_uuid(),
        state="REQUESTED", provenance=Provenance.LIVE if elevenlabs_configured else Provenance.FIXTURE,
    )
    session.add(comm)
    await session.flush()
    if action.recipient == "TENANT":
        await enqueue_job(
            session, case_id=case_id, kind="PLACE_CALL", dedupe_key=f"place-call:{comm.id}",
            payload={"communication_id": comm.id, "question": action.questions[0] if action.questions else ""},
        )
    else:
        # OPERATOR-directed requests place no call and enqueue no job, so
        # without a CaseEvent they were invisible on the Timeline -- the
        # only trace was a Communication row stuck at REQUESTED, which the
        # Calls tab rendered as a phantom "call in progress" that never
        # resolves. Log it as its own event instead.
        await append_event(
            session, case_id=case_id, event_type="OPERATOR_INFO_REQUESTED",
            payload={"communication_id": comm.id, "questions": action.questions},
            actor=actor, source_event_key=f"operator-info-requested:{comm.id}",
        )
    return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, resource_ids={"communication_id": comm.id})


async def request_confirmation(session: AsyncSession, *, case_id: str, action: RequestConfirmation, elevenlabs_configured: bool, actor: ActorContext) -> CommandResult:
    case = await load_case(session, case_id)
    existing = (
        await session.execute(
            select(CommunicationModel).where(
                CommunicationModel.case_id == case_id, CommunicationModel.purpose == CommPurpose.FOLLOW_UP,
                CommunicationModel.state.in_(["REQUESTED", "ACTIVE"]),
            )
        )
    ).scalars().first()
    if existing is not None:
        return CommandResult(status=CommandResultStatus.NOOP, case_version=case.version, resource_ids={"communication_id": existing.id})
    comm = CommunicationModel(
        id=new_uuid(), case_id=case_id, tenant_id=case.tenant_id, purpose=CommPurpose.FOLLOW_UP,
        direction="OUTBOUND", correlation_token_hash=new_uuid(), state="REQUESTED",
        provenance=Provenance.LIVE if elevenlabs_configured else Provenance.FIXTURE,
    )
    session.add(comm)
    await session.flush()
    await enqueue_job(
        session, case_id=case_id, kind="PLACE_CALL", dedupe_key=f"place-call:{comm.id}",
        payload={"communication_id": comm.id, "question": action.questions[0] if action.questions else ""},
    )
    return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, resource_ids={"communication_id": comm.id})


async def resolve_case(session: AsyncSession, *, case_id: str, action: ResolveCase, trigger_event_id: str, actor: ActorContext) -> CommandResult:
    case = await load_case(session, case_id)
    issue = await load_issue(session, case_id)

    if case.status != CaseStatus.AWAITING_CONFIRMATION:
        raise PolicyRejectedError(f"case {case_id} is not awaiting confirmation (status={case.status})")
    if issue.tenant_resolution_confirmed_at is None:
        raise PolicyRejectedError("no affirmative tenant confirmation on record")
    if issue.unresolved_concerns:
        raise PolicyRejectedError(f"unresolved concerns remain: {issue.unresolved_concerns}")

    required = (
        await session.execute(
            select(WorkOrderModel).where(WorkOrderModel.case_id == case_id, WorkOrderModel.required_for_resolution.is_(True))
        )
    ).scalars().all()
    if not all(wo.status == WorkOrderStatus.COMPLETED for wo in required):
        raise PolicyRejectedError("required work is not all completed")

    open_edges = (
        await session.execute(
            select(DependencyModel).where(DependencyModel.case_id == case_id, DependencyModel.status != "SATISFIED")
        )
    ).scalars().all()
    if open_edges:
        raise PolicyRejectedError("unresolved or invalidated dependency edges remain")

    assert_case_transition(case.status, CaseStatus.RESOLVED)
    case.status = CaseStatus.RESOLVED
    bump_version(case)
    event = await append_event(
        session, case_id=case_id, event_type="CASE_RESOLVED",
        payload={"issue_id": issue.id}, actor=actor,
        source_event_key=f"resolve:{case_id}:{action.confirmation_event_id}", causation_event_id=trigger_event_id,
    )
    return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id])


_ESCALATION_SOURCE_STATUSES = (CaseStatus.ACTIVE, CaseStatus.AWAITING_CONFIRMATION, CaseStatus.RESOLVED)


async def escalate_to_human(session: AsyncSession, *, case_id: str, action: Escalate, trigger_event_id: str | None, actor: ActorContext) -> CommandResult:
    case = await load_case(session, case_id)
    # docs/07's state graph has exactly three edges into ESCALATED --
    # ACTIVE, AWAITING_CONFIRMATION and RESOLVED ("late contradictory
    # evidence") -- and none at all out of CANCELLED, which is terminal.
    # This used to only guard the *status write* on that same list,
    # leaving escalation_reason, bump_version and a CASE_ESCALATED event
    # applied unconditionally even when the case was CANCELLED (or already
    # ESCALATED): a phantom escalation and a version bump on a case
    # docs/07 treats as terminal (or as already handled). Every sibling
    # command (resolve_case, add_prerequisite, accept_report) raises
    # PolicyRejectedError for an invalid precondition instead of silently
    # no-oping past it -- do the same here, before any write.
    if case.status not in _ESCALATION_SOURCE_STATUSES:
        raise PolicyRejectedError(f"case {case_id} cannot be escalated from status {case.status}")
    case.resume_status = case.status
    assert_case_transition(case.status, CaseStatus.ESCALATED)
    case.status = CaseStatus.ESCALATED
    case.escalation_reason = action.operator_message
    bump_version(case)
    event = await append_event(
        session, case_id=case_id, event_type="CASE_ESCALATED",
        payload={"reason_code": action.reason_code, "message": action.operator_message},
        actor=actor, source_event_key=f"escalate:{case_id}:{trigger_event_id or new_uuid()}",
        causation_event_id=trigger_event_id,
    )
    return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id])


async def wait_for_event(session: AsyncSession, *, case_id: str, action: Wait, actor: ActorContext) -> CommandResult:
    case = await load_case(session, case_id)
    if action.follow_up_at is not None:
        case.next_follow_up_at = action.follow_up_at
        await enqueue_job(
            session, case_id=case_id, kind=JobKind.FOLLOW_UP,
            dedupe_key=f"followup:{case_id}:{action.follow_up_at.isoformat()}",
            payload={"reason": action.reason}, run_at=action.follow_up_at,
        )
    return CommandResult(status=CommandResultStatus.NOOP, case_version=case.version)


# --------------------------------------------------------------------------
# Read: composed case snapshot (used by the coordinator, API and UI)
# --------------------------------------------------------------------------

_PHONE_LIKE = re.compile(r"^\+?[0-9][0-9 ()-]{6,}$")


def _phone_like(value: str | None) -> str | None:
    """Only ever returns a value that actually looks like a phone number.
    Seed/demo contractor `contact_reference` values are placeholders like
    "mock:apex-roofing" -- those must surface as null, not a fabricated
    phone number (CLAUDE.md: no invented facts)."""
    if value and _PHONE_LIKE.match(value.strip()):
        return value
    return None


def _pick_assigned_work_order(work_orders: list[WorkOrderModel]) -> WorkOrderModel | None:
    """Single shared rule for "the" contractor shown for a case, used by
    both the case-list endpoint and the case-detail snapshot so the two
    views can never disagree. A case can have several work orders with
    different contractors at once (the hero path's roofer + scaffolder), so
    this is a deliberate, documented tie-break rather than an arbitrary
    pick: prefer a work order that still has an assigned contractor and
    isn't finished (COMPLETED/CANCELLED); among those, prefer the primary
    REPAIR work order over a prerequisite (scaffold) one; then prefer the
    most recently updated.
    """
    candidates = [wo for wo in work_orders if wo.contractor_id is not None]
    if not candidates:
        return None
    open_candidates = [
        wo for wo in candidates if wo.status not in (WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED)
    ]
    pool = open_candidates or candidates
    pool.sort(key=lambda wo: (0 if wo.kind == WorkOrderKind.REPAIR else 1, -wo.updated_at.timestamp()))
    return pool[0]


async def _work_orders_by_case_id(session: AsyncSession, case_ids: list[str]) -> dict[str, list[WorkOrderModel]]:
    """Shared batched fetch: every work order for a set of cases, grouped by
    case_id. Used anywhere that needs "this case's work orders" for more
    than one case at a time (contractor selection, property history/stats)
    so it isn't one query per row."""
    if not case_ids:
        return {}
    rows = (
        await session.execute(select(WorkOrderModel).where(WorkOrderModel.case_id.in_(case_ids)))
    ).scalars().all()
    by_case: dict[str, list[WorkOrderModel]] = {}
    for wo in rows:
        by_case.setdefault(wo.case_id, []).append(wo)
    return by_case


def _pick_primary_trade(work_orders: list[WorkOrderModel]) -> Trade | None:
    """Trade shown for a case in property-history/stats views -- "what kind
    of work is this", not "who is doing it" (that's
    _pick_assigned_work_order, a different rule that only considers work
    orders with a contractor already attached, so it can't answer this for
    a case nobody has been assigned to yet).

    Judgment call, not a documented product spec (CLAUDE.md docs/06 has no
    "primary trade" concept): a CANCELLED work order is excluded first --
    work that was called off is not what the case is "about" any more, and
    counting it would distort quoted_by_trade/recurring_issues with a
    trade nobody is actually doing. Among what's left, prefer the work
    order marked required_for_resolution=True (the primary repair, not a
    scaffold/access prerequisite discovered later); if several qualify, or
    none do, take the one created first. None if every work order on the
    case was cancelled (no active "primary trade" to report), not a
    fallback to the cancelled one.
    """
    live = [wo for wo in work_orders if wo.status != WorkOrderStatus.CANCELLED]
    if not live:
        return None
    required = [wo for wo in live if wo.required_for_resolution]
    pool = sorted(required or live, key=lambda wo: wo.created_at)
    return pool[0].trade


async def assigned_contractors_for_cases(session: AsyncSession, case_ids: list[str]) -> dict[str, "AssignedContractor"]:
    """Batched version of the same selection rule, for the case-list
    endpoint (avoids one query per row)."""
    from app.models import ContractorModel
    from app.schemas import AssignedContractor

    if not case_ids:
        return {}
    by_case = await _work_orders_by_case_id(session, case_ids)

    contractor_ids = {wo.contractor_id for wos in by_case.values() for wo in wos if wo.contractor_id}
    contractors_by_id: dict[str, ContractorModel] = {}
    if contractor_ids:
        contractor_rows = (
            await session.execute(select(ContractorModel).where(ContractorModel.id.in_(contractor_ids)))
        ).scalars().all()
        contractors_by_id = {c.id: c for c in contractor_rows}

    result: dict[str, AssignedContractor] = {}
    for case_id, wos in by_case.items():
        chosen = _pick_assigned_work_order(wos)
        if chosen is None:
            continue
        contractor = contractors_by_id.get(chosen.contractor_id)
        if contractor is None:
            continue
        result[case_id] = AssignedContractor(
            id=contractor.id, display_name=contractor.display_name, trade=chosen.trade,
            contact_reference=contractor.contact_reference, phone=_phone_like(contractor.contact_reference),
            provenance=contractor.provenance,
        )
    return result


_STATUS_EVENT_MAP: dict[str, CaseStatus] = {
    "CASE_CREATED": CaseStatus.ACTIVE,
    "CASE_RESUMED": CaseStatus.ACTIVE,
    "CASE_RESOLVED": CaseStatus.RESOLVED,
    "CASE_ESCALATED": CaseStatus.ESCALATED,
    "CASE_CANCELLED": CaseStatus.CANCELLED,
}


async def reconstructed_status_counts(session: AsyncSession, cutoff: datetime) -> dict[str, int]:
    """Approximate ACTIVE/AWAITING_CONFIRMATION/ESCALATED case counts as of
    `cutoff`. See the module-level comment above this function for what is
    and isn't reconstructable."""
    # Operational cases only. The synthetic archive is decades of closed
    # history dated in the past, so including it here makes the "as of a
    # week ago" baseline enormous and every comparison percentage on the
    # dashboard collapses towards -100% the moment the archive is
    # imported -- a number about sample data presented as a trend in the
    # operator's real workload.
    operational = RepairCaseModel.archive_batch_id.is_(None)
    cases = (
        await session.execute(
            select(RepairCaseModel.id, RepairCaseModel.created_at).where(operational)
        )
    ).all()
    events = (
        await session.execute(
            select(CaseEventModel.case_id, CaseEventModel.type)
            .join(RepairCaseModel, RepairCaseModel.id == CaseEventModel.case_id)
            .where(CaseEventModel.occurred_at <= cutoff, operational)
            .order_by(CaseEventModel.occurred_at, CaseEventModel.seq)
        )
    ).all()

    latest_status: dict[str, CaseStatus] = {}
    for case_id, event_type in events:
        mapped = _STATUS_EVENT_MAP.get(event_type)
        if mapped is not None:
            latest_status[case_id] = mapped

    counts = {"ACTIVE": 0, "AWAITING_CONFIRMATION": 0, "ESCALATED": 0}
    for case_id, created_at in cases:
        if created_at > cutoff:
            continue
        status = latest_status.get(case_id, CaseStatus.ACTIVE)
        if status.value in counts:
            counts[status.value] += 1
    return counts


def delta_pct(current: int, historical: int) -> float | None:
    """Percent change from `historical` to `current`. None (not a fake
    number) whenever that's mathematically undefined or would mislead:
    zero historical cases in that status means "no baseline to compare
    against", not "infinite growth"."""
    if historical == 0:
        return None
    return round((current - historical) / historical * 100, 1)


async def average_resolution_hours(session: AsyncSession, window_days: int = 30) -> float | None:
    """Mean hours between a case's created_at and its latest CASE_RESOLVED
    event's occurred_at, restricted to cases that resolved within the last
    `window_days` days. None when nothing resolved in that window -- never
    an average over zero samples."""
    cutoff = utcnow() - timedelta(days=window_days)
    resolved_rows = (
        await session.execute(
            select(CaseEventModel.case_id, func.max(CaseEventModel.occurred_at))
            .join(RepairCaseModel, RepairCaseModel.id == CaseEventModel.case_id)
            # Operational only, for the same reason as
            # reconstructed_status_counts above. The archive writes no
            # CaseEvents today, so this changes nothing now -- it is here
            # so the invariant survives an importer that someday does.
            .where(
                CaseEventModel.type == "CASE_RESOLVED",
                RepairCaseModel.archive_batch_id.is_(None),
            )
            .group_by(CaseEventModel.case_id)
        )
    ).all()
    recent = {case_id: resolved_at for case_id, resolved_at in resolved_rows if resolved_at is not None and resolved_at >= cutoff}
    if not recent:
        return None

    created_rows = (
        await session.execute(select(RepairCaseModel.id, RepairCaseModel.created_at).where(RepairCaseModel.id.in_(recent.keys())))
    ).all()
    durations = [(recent[case_id] - created_at).total_seconds() / 3600 for case_id, created_at in created_rows]
    if not durations:
        return None
    return round(sum(durations) / len(durations), 2)


async def load_upcoming_appointments(session: AsyncSession, limit: int = 100) -> list["UpcomingAppointmentItem"]:
    """Arranged appointments starting in the future, across every case --
    for a cross-case "upcoming visits" list. CONFIRMED *or* PENDING, with
    start_at in the future (a cancelled or finished attempt never appears
    here); ordered soonest first.

    PENDING counts because a visit the system arranged is still a visit
    someone must turn up to. It used to be CONFIRMED only, which was
    harmless while the mock connector wrote CONFIRMED for everything --
    but that status was asserting a contractor acknowledgment that never
    happened, and once it was corrected to PENDING an appointment-only
    filter would have emptied this list entirely.

    Deliberately `start_at >= now`, not `end_at >= now` like
    load_case_snapshot's `next_appointment` (which intentionally keeps
    showing a visit that's currently in progress). That means the two views
    can disagree about a visit happening right now: the case-detail card
    still shows it, this cross-case list has already dropped it. A "next
    visits" list not including one already underway is the intended
    behaviour here, not a bug -- flagged because it's easy to mistake for
    an inconsistency between the two endpoints.
    """
    from app.models import ContractorModel, PropertyModel
    from app.schemas import AppointmentStatus as AppointmentStatus_
    from app.schemas import UpcomingAppointmentItem

    # Operational only. An archival case is closed history; a future
    # appointment on one would be a fabricated commitment sitting in the
    # operator's "upcoming visits" list. Every sibling aggregate filters
    # this way and these two did not.
    now = utcnow()
    rows = (
        await session.execute(
            select(
                AppointmentModel, WorkOrderModel.trade, RepairCaseModel.case_number, RepairCaseModel.title,
                PropertyModel.address_line, ContractorModel.display_name,
            )
            .join(WorkOrderModel, WorkOrderModel.id == AppointmentModel.work_order_id)
            .join(RepairCaseModel, RepairCaseModel.id == AppointmentModel.case_id)
            .join(PropertyModel, PropertyModel.id == RepairCaseModel.property_id)
            .join(ContractorModel, ContractorModel.id == AppointmentModel.contractor_id)
            .where(
                AppointmentModel.status.in_(
                    (AppointmentStatus_.CONFIRMED, AppointmentStatus_.PENDING)
                ),
                AppointmentModel.start_at >= now,
                RepairCaseModel.archive_batch_id.is_(None),
            )
            .order_by(AppointmentModel.start_at.asc())
            .limit(limit)
        )
    ).all()
    return [
        UpcomingAppointmentItem(
            appointment_id=appt.id, case_id=appt.case_id, case_number=case_number, case_title=case_title,
            work_order_id=appt.work_order_id, trade=trade, start_at=appt.start_at, end_at=appt.end_at,
            status=appt.status, property_address=address_line, contractor_id=appt.contractor_id,
            contractor_name=contractor_name,
        )
        for appt, trade, case_number, case_title, address_line, contractor_name in rows
    ]


async def load_case_messages(session: AsyncSession, case_id: str) -> list["Message"]:
    """Display-only message thread for a case, oldest first. Never fed to
    the coordinator -- see MessageModel's docstring."""
    from app.models import MessageModel
    from app.schemas import Message

    rows = (
        await session.execute(
            select(MessageModel).where(MessageModel.case_id == case_id).order_by(MessageModel.created_at.asc())
        )
    ).scalars().all()
    return [Message.model_validate(m) for m in rows]


async def load_notifications(session: AsyncSession, limit: int = 50) -> list["NotificationItem"]:
    """Bell-icon feed, derived entirely from existing ActionRecord/CaseEvent
    rows -- no separate notification-authoring system, and (per the task
    that added this) no persisted read/unread-tracking table either, so
    `unread` has to be defined deterministically from data that already
    exists:

    - AWAITING_APPROVAL: this query only ever returns actions currently in
      that state, so every row here is, by construction, still awaiting an
      operator decision -- always unread=True. Once approved/rejected the
      action moves to a different `state` and simply stops appearing.
    - CASE_ESCALATED: the escalation CaseEvent itself is permanent (append-
      only log), but whether it still needs attention is not -- unread is
      True only while the case's *current* status is still ESCALATED right
      now; once resumed/resolved/cancelled, the same historical event stays
      visible (so the feed doesn't silently forget it happened) but flips
      to read.
    """
    from app.models import ActionRecordModel
    from app.schemas import NotificationItem, NotificationKind

    pending_actions = (
        await session.execute(
            select(ActionRecordModel, RepairCaseModel.case_number, RepairCaseModel.title)
            .join(RepairCaseModel, RepairCaseModel.id == ActionRecordModel.case_id)
            # Operational only: an archival case can never need a
            # decision, and one appearing in the bell would be a
            # fabricated task.
            .where(
                ActionRecordModel.state == "AWAITING_APPROVAL",
                RepairCaseModel.archive_batch_id.is_(None),
            )
            .order_by(ActionRecordModel.updated_at.desc())
            .limit(limit)
        )
    ).all()
    escalations = (
        await session.execute(
            select(CaseEventModel, RepairCaseModel.case_number, RepairCaseModel.title, RepairCaseModel.status)
            .join(RepairCaseModel, RepairCaseModel.id == CaseEventModel.case_id)
            .where(
                CaseEventModel.type == "CASE_ESCALATED",
                RepairCaseModel.archive_batch_id.is_(None),
            )
            .order_by(CaseEventModel.occurred_at.desc())
            .limit(limit)
        )
    ).all()

    items: list[NotificationItem] = []
    for action, case_number, title in pending_actions:
        proposal = action.proposal or {}
        message = proposal.get("decision_summary") or f"{action.kind} awaiting approval"
        items.append(
            NotificationItem(
                id=f"action:{action.id}", kind=NotificationKind.AWAITING_APPROVAL, case_id=action.case_id,
                case_number=case_number, case_title=title, occurred_at=action.updated_at,
                message=message, unread=True,
            )
        )
    for event, case_number, title, case_status in escalations:
        payload = event.payload or {}
        message = payload.get("reason") or "Case escalated"
        items.append(
            NotificationItem(
                id=f"event:{event.id}", kind=NotificationKind.CASE_ESCALATED, case_id=event.case_id,
                case_number=case_number, case_title=title, occurred_at=event.occurred_at,
                message=message, unread=(case_status == CaseStatus.ESCALATED),
            )
        )

    items.sort(key=lambda item: item.occurred_at, reverse=True)
    return items[:limit]


async def load_case_snapshot(session: AsyncSession, case_id: str):
    from app.models import (
        ActionRecordModel,
        AppointmentModel as AppointmentModel_,
        AvailabilityWindowModel as AvailabilityWindowModel_,
        CaseEventModel as CaseEventModel_,
        CommunicationModel as CommunicationModel_,
        ContractorModel,
        ContractorReportModel as ContractorReportModel_,
        DependencyModel as DependencyModel_,
        JobModel as JobModel_,
        OrchestrationRunModel as OrchestrationRunModel_,
        PropertyModel,
        TenantModel,
        WorkOrderModel as WorkOrderModel_,
    )
    from app.schemas import (
        ActionRecord,
        Appointment,
        AppointmentStatus as AppointmentStatus_,
        AvailabilityWindow,
        CaseEvent,
        CaseSnapshot,
        Communication,
        Contractor,
        ContractorReport,
        Dependency,
        Property as Property_,
        RepairCase,
        RepairIssue,
        Tenant as Tenant_,
        WorkOrder,
    )

    case = await load_case(session, case_id)
    issue = await load_issue(session, case_id)
    property_row = await session.get(PropertyModel, case.property_id)
    tenant_row = await session.get(TenantModel, case.tenant_id)
    if property_row is None:
        raise NotFoundError(f"property {case.property_id} not found")
    if tenant_row is None:
        raise NotFoundError(f"tenant {case.tenant_id} not found")

    work_orders = (await session.execute(select(WorkOrderModel_).where(WorkOrderModel_.case_id == case_id))).scalars().all()
    dependencies = (await session.execute(select(DependencyModel_).where(DependencyModel_.case_id == case_id))).scalars().all()
    appointments = (await session.execute(select(AppointmentModel_).where(AppointmentModel_.case_id == case_id))).scalars().all()
    reports = (
        await session.execute(
            select(ContractorReportModel_).where(ContractorReportModel_.case_id == case_id).order_by(ContractorReportModel_.received_at.desc()).limit(10)
        )
    ).scalars().all()
    communications = (await session.execute(select(CommunicationModel_).where(CommunicationModel_.case_id == case_id))).scalars().all()
    availability = (await session.execute(select(AvailabilityWindowModel_).where(AvailabilityWindowModel_.case_id == case_id))).scalars().all()
    approved_contractors = (
        await session.execute(select(ContractorModel).where(ContractorModel.approval_status == "APPROVED"))
    ).scalars().all()
    pending_actions = (
        await session.execute(
            select(ActionRecordModel).where(
                ActionRecordModel.case_id == case_id,
                ActionRecordModel.state.in_(["PROPOSED", "AWAITING_APPROVAL", "PENDING", "RUNNING", "UNKNOWN"]),
            )
        )
    ).scalars().all()
    recent_events = (
        await session.execute(
            select(CaseEventModel_).where(CaseEventModel_.case_id == case_id).order_by(CaseEventModel_.seq.desc()).limit(20)
        )
    ).scalars().all()

    assigned_contractor = (await assigned_contractors_for_cases(session, [case_id])).get(case_id)

    has_pending_job = (
        await session.execute(
            select(JobModel_.id).where(JobModel_.case_id == case_id, JobModel_.status.in_(["PENDING", "LEASED"])).limit(1)
        )
    ).scalar_one_or_none()
    has_running_run = (
        await session.execute(
            select(OrchestrationRunModel_.id).where(OrchestrationRunModel_.case_id == case_id, OrchestrationRunModel_.state == "RUNNING").limit(1)
        )
    ).scalar_one_or_none()

    now = utcnow()
    # "Not-yet-passed" means the visit window hasn't ended, not that it
    # hasn't started -- a visit currently in progress (start_at <= now <
    # end_at) still belongs on a "next appointment" card; only a window
    # that has fully ended should drop off.
    # PENDING as well as CONFIRMED -- see load_upcoming_appointments. A
    # visit the system arranged belongs on the "next appointment" card
    # whether or not a provider has acknowledged it; the card shows the
    # status, so the distinction is displayed rather than hidden.
    upcoming = [
        a for a in appointments
        if a.status in (AppointmentStatus_.CONFIRMED, AppointmentStatus_.PENDING) and a.end_at >= now
    ]
    next_appointment_row = min(upcoming, key=lambda a: a.start_at) if upcoming else None

    return CaseSnapshot(
        case=RepairCase.model_validate(case),
        issue=RepairIssue.model_validate(issue),
        property=Property_.model_validate(property_row),
        tenant=Tenant_.model_validate(tenant_row),
        assigned_contractor=assigned_contractor,
        next_appointment=Appointment.model_validate(next_appointment_row) if next_appointment_row else None,
        work_orders=[WorkOrder.model_validate(w) for w in work_orders],
        dependencies=[Dependency.model_validate(d) for d in dependencies],
        appointments=[Appointment.model_validate(a) for a in appointments],
        latest_reports=[ContractorReport.model_validate(r) for r in reports],
        communications=[Communication.model_validate(c) for c in communications],
        availability=[AvailabilityWindow.model_validate(a) for a in availability],
        approved_contractors=[Contractor.model_validate(c) for c in approved_contractors],
        pending_actions=[ActionRecord.model_validate(a) for a in pending_actions],
        recent_events=list(reversed([CaseEvent.model_validate(e) for e in recent_events])),
        policy_snapshot={"ordinary_authority_limit_pence": policy.ORDINARY_AUTHORITY_LIMIT_PENCE, "policy_version": 1},
        snapshot_version=case.version,
        agent_active=bool(has_pending_job or has_running_run),
    )
