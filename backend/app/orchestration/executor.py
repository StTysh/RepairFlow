"""Action ledger admission, approval and execution.

Two distinct version checks live here (see docs/10 idempotency section):
- admit_proposal compares a FRESH ActionProposal.expected_case_version
  against the current case version (rejects a stale semantic decision).
- decide_approval compares the OPERATOR's ApprovalDecision.expected_case_version
  (what they saw when they clicked approve) against the current case version.
Neither check is reused for the other, and EXECUTE_ACTION never compares a
stored version at all: it only re-validates current business predicates,
so an approval's own version bump can never invalidate the action it just
approved.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_scope
from app.domain import policy
from app.domain import services
from app.orchestration.dedupe import payload_hash
from app.domain.errors import ConflictError, DomainError, NotFoundError, PolicyRejectedError, StaleVersionError
from app.domain.services import ActorContext
from app.domain.transitions import assert_work_order_transition
from app.integrations.booking import mock_booking_connector
from app.models import (
    AppointmentModel,
    ContractorCandidateModel,
    ContractorReportModel,
    ResearchSnapshotModel,
    WorkOrderModel,
    new_uuid,
)
from app.schemas import (
    AcceptReport,
    ActionState,
    AddPrerequisite,
    Approval,
    ApplyTriage,
    ApprovalDecision,
    BookingRequest,
    BookingStatus,
    CommandResult,
    CommandResultStatus,
    ContractorSearchResult,
    DiscoverContractors,
    Escalate,
    NextAction,
    RequestConfirmation,
    RequestInformation,
    ResolveCase,
    ScheduleVisit,
    ToolError,
    ToolErrorCode,
    Wait,
    WorkOrderStatus,
)
from app.schemas import ActionProposal


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResearchAdapter(Protocol):
    async def search(self, case_id: str, trade, postcode: str) -> ContractorSearchResult: ...


class FixtureResearchAdapter:
    """No-network placeholder used until Phase 6 wires a real Tavily adapter."""

    async def search(self, case_id: str, trade, postcode: str) -> ContractorSearchResult:
        from app.schemas import Provenance, ResearchSnapshot

        now = utcnow()
        return ContractorSearchResult(
            research=ResearchSnapshot(
                id=new_uuid(), case_id=case_id, query=f"{trade.value} contractor {postcode}",
                provider="TAVILY", requested_at=now, completed_at=now,
                result_urls=[], results=[], provenance=Provenance.FIXTURE,
            ),
            candidates=[],
            warnings=["Tavily is not configured; research adapter running in FIXTURE mode with no results."],
        )


def _target_id(action: NextAction) -> str | None:
    if isinstance(action, ScheduleVisit):
        return str(action.work_order_id)
    if isinstance(action, AddPrerequisite):
        return str(action.blocked_work_order_id)
    if isinstance(action, AcceptReport):
        return str(action.report_id)
    if isinstance(action, ResolveCase):
        return str(action.issue_id)
    return None


async def _idempotency_key(session: AsyncSession, action: NextAction, case_id: str, trigger_event_id: str) -> str:
    if isinstance(action, ApplyTriage):
        return f"triage:{case_id}:{trigger_event_id}"
    if isinstance(action, RequestInformation):
        return f"request_info:{case_id}:{action.purpose.value}:{trigger_event_id}"
    if isinstance(action, DiscoverContractors):
        return f"discover:{case_id}:{action.trade.value}:{trigger_event_id}"
    if isinstance(action, ScheduleVisit):
        count = (
            await session.execute(
                select(func.count()).select_from(AppointmentModel).where(AppointmentModel.work_order_id == str(action.work_order_id))
            )
        ).scalar_one()
        return f"booking:{action.work_order_id}:{action.slot_id}:{count + 1}"
    if isinstance(action, AddPrerequisite):
        return f"report:{action.report_id}:prerequisite"
    if isinstance(action, AcceptReport):
        return f"report:{action.report_id}:accept"
    if isinstance(action, RequestConfirmation):
        return f"request_confirmation:{case_id}:{action.issue_id}:{trigger_event_id}"
    if isinstance(action, ResolveCase):
        return f"resolve:{case_id}:{action.confirmation_event_id}"
    if isinstance(action, Escalate):
        return f"escalate:{case_id}:{trigger_event_id}"
    if isinstance(action, Wait):
        return f"wait:{case_id}:{trigger_event_id}"
    raise ValueError(f"unhandled action for idempotency key: {action!r}")


async def _needs_approval(session: AsyncSession, action: NextAction) -> bool:
    if isinstance(action, ApplyTriage):
        return policy.triage_requires_approval(action.risk)
    if isinstance(action, ScheduleVisit):
        wo = await session.get(WorkOrderModel, str(action.work_order_id))
        if wo is None:
            return True
        return policy.work_order_requires_approval_to_schedule(wo.kind, wo.quote_pence, wo.approved_limit_pence)
    if isinstance(action, AcceptReport):
        if action.outcome != "COMPLETED":
            return False
        report = await session.get(ContractorReportModel, str(action.report_id))
        if report is None:
            return True
        wo = await session.get(WorkOrderModel, report.work_order_id)
        return policy.report_acceptance_requires_approval(wo.kind) if wo else True
    return False


async def admit_proposal(session: AsyncSession, proposal: ActionProposal, actor: ActorContext):
    from app.models import ActionRecordModel

    case = await services.load_case(session, str(proposal.case_id))
    if case.version != proposal.expected_case_version:
        raise StaleVersionError(
            f"proposal targeted version {proposal.expected_case_version}, case is at {case.version}",
            current_version=case.version,
        )

    idempotency_key = await _idempotency_key(session, proposal.action, str(proposal.case_id), str(proposal.trigger_event_id))
    proposal_hash = payload_hash(proposal.model_dump_json())

    existing = (
        await session.execute(select(ActionRecordModel).where(ActionRecordModel.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if existing is not None:
        if existing.payload_hash != proposal_hash:
            raise ConflictError(f"idempotency key {idempotency_key} reused with a different proposal payload")
        return existing

    needs_approval = await _needs_approval(session, proposal.action)
    action_record = ActionRecordModel(
        id=new_uuid(), case_id=str(proposal.case_id), kind=proposal.action.kind,
        target_id=_target_id(proposal.action), idempotency_key=idempotency_key, payload_hash=proposal_hash,
        proposal=proposal.model_dump(mode="json"),
        state=(ActionState.AWAITING_APPROVAL if needs_approval else ActionState.PENDING).value,
    )
    session.add(action_record)
    await session.flush()
    if not needs_approval:
        await services.enqueue_job(
            session, case_id=action_record.case_id, kind="EXECUTE_ACTION",
            dedupe_key=f"execute:{action_record.id}", payload={"action_id": action_record.id},
        )
    return action_record


async def decide_approval(session: AsyncSession, decision: ApprovalDecision, actor: ActorContext) -> CommandResult:
    from app.models import ActionRecordModel

    action_record = await session.get(ActionRecordModel, str(decision.action_id))
    if action_record is None:
        raise NotFoundError(f"action {decision.action_id} not found")
    case = await services.load_case(session, action_record.case_id)

    if action_record.state != ActionState.AWAITING_APPROVAL.value:
        raise PolicyRejectedError(f"action {action_record.id} is not awaiting approval (state={action_record.state})")
    if action_record.payload_hash != decision.action_payload_hash:
        raise ConflictError("approval targets a proposal payload that no longer matches the recorded action")
    if case.version != decision.expected_case_version:
        raise StaleVersionError("approval view is stale; refresh before deciding", current_version=case.version)

    if not decision.approve:
        action_record.state = ActionState.REJECTED.value
        action_record.updated_at = utcnow()
        services.bump_version(case)
        event = await services.append_event(
            session, case_id=case.id, event_type="APPROVAL_DECIDED",
            payload={"approved": False, "action_id": action_record.id, "reason": decision.reason},
            actor=actor, source_event_key=f"approval:{action_record.id}:rejected",
        )
        return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id])

    action_record.approval = Approval(
        operator_id=actor.actor_id, approved_at=utcnow(), action_payload_hash=decision.action_payload_hash,
        authorized_limit_pence=decision.authorized_limit_pence, reason=decision.reason,
    ).model_dump(mode="json")
    action_record.state = ActionState.PENDING.value
    action_record.updated_at = utcnow()
    services.bump_version(case)
    event = await services.append_event(
        session, case_id=case.id, event_type="APPROVAL_DECIDED",
        payload={"approved": True, "action_id": action_record.id}, actor=actor,
        source_event_key=f"approval:{action_record.id}:approved",
    )
    await services.enqueue_job(
        session, case_id=case.id, kind="EXECUTE_ACTION",
        dedupe_key=f"execute:{action_record.id}", payload={"action_id": action_record.id},
    )
    return CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id])


def _record_terminal(action_record, state: ActionState, result: CommandResult) -> None:
    action_record.state = state.value
    action_record.result = result.model_dump(mode="json")
    action_record.updated_at = utcnow()


async def _dispatch_local(session: AsyncSession, case_id: str, action_id: str, action: NextAction, trigger_event_id: str, actor: ActorContext, *, elevenlabs_configured: bool) -> CommandResult:
    if isinstance(action, ApplyTriage):
        return await services.apply_triage(session, case_id=case_id, action=action, trigger_event_id=trigger_event_id, actor=actor)
    if isinstance(action, AddPrerequisite):
        return await services.add_prerequisite(session, case_id=case_id, action=action, action_id=action_id, trigger_event_id=trigger_event_id, actor=actor)
    if isinstance(action, AcceptReport):
        return await services.accept_report(session, case_id=case_id, action=action, action_id=action_id, trigger_event_id=trigger_event_id, actor=actor)
    if isinstance(action, RequestInformation):
        return await services.request_information(session, case_id=case_id, action=action, elevenlabs_configured=elevenlabs_configured, actor=actor)
    if isinstance(action, RequestConfirmation):
        return await services.request_confirmation(session, case_id=case_id, action=action, elevenlabs_configured=elevenlabs_configured, actor=actor)
    if isinstance(action, ResolveCase):
        return await services.resolve_case(session, case_id=case_id, action=action, trigger_event_id=trigger_event_id, actor=actor)
    if isinstance(action, Escalate):
        return await services.escalate_to_human(session, case_id=case_id, action=action, trigger_event_id=trigger_event_id, actor=actor)
    if isinstance(action, Wait):
        return await services.wait_for_event(session, case_id=case_id, action=action, actor=actor)
    raise ValueError(f"no local dispatch for {action!r}")


async def execute_action(action_id: str, *, elevenlabs_configured: bool = False, research_adapter: ResearchAdapter | None = None) -> CommandResult:
    from app.models import ActionRecordModel

    research_adapter = research_adapter or FixtureResearchAdapter()
    external_kind: str | None = None
    external_payload = None

    async with session_scope() as session:
        action_record = await session.get(ActionRecordModel, action_id)
        if action_record is None:
            raise NotFoundError(f"action {action_id} not found")
        if action_record.state != ActionState.PENDING.value:
            if action_record.result:
                return CommandResult.model_validate(action_record.result)
            case = await services.load_case(session, action_record.case_id)
            return CommandResult(status=CommandResultStatus.NOOP, case_version=case.version)

        proposal = ActionProposal.model_validate(action_record.proposal)
        action = proposal.action
        case_id = action_record.case_id
        trigger_event_id = str(proposal.trigger_event_id)
        actor = ActorContext(actor_type="EXECUTOR", actor_id="executor", correlation_id=action_record.id)

        try:
            if isinstance(action, ScheduleVisit):
                from app.models import AvailabilityWindowModel, ContractorModel, MockSlotModel

                work_order = await session.get(WorkOrderModel, str(action.work_order_id))
                if work_order is None or work_order.case_id != case_id:
                    raise NotFoundError(f"work order {action.work_order_id} not in case {case_id}")
                if work_order.status != WorkOrderStatus.READY:
                    raise PolicyRejectedError(f"work order {work_order.id} is not READY (status={work_order.status})")

                contractor = await session.get(ContractorModel, str(action.contractor_id))
                if contractor is None or contractor.approval_status != "APPROVED":
                    raise PolicyRejectedError(f"contractor {action.contractor_id} is not an approved supplier")

                slot = await session.get(MockSlotModel, action.slot_id)
                if slot is None:
                    raise PolicyRejectedError(f"slot {action.slot_id} does not exist")
                if not action.tenant_availability_ids:
                    raise PolicyRejectedError("no tenant availability cited for this booking")
                windows = (
                    await session.execute(
                        select(AvailabilityWindowModel).where(
                            AvailabilityWindowModel.id.in_([str(i) for i in action.tenant_availability_ids]),
                            AvailabilityWindowModel.case_id == case_id,
                        )
                    )
                ).scalars().all()
                if len(windows) != len(action.tenant_availability_ids):
                    raise PolicyRejectedError("cited availability window not found in this case")
                covered = any(w.start_at <= slot.start_at and slot.end_at <= w.end_at for w in windows)
                if not covered:
                    raise PolicyRejectedError("proposed slot falls outside the cited tenant availability")

                attempt_number = (
                    await session.execute(
                        select(func.count()).select_from(AppointmentModel).where(AppointmentModel.work_order_id == work_order.id)
                    )
                ).scalar_one() + 1
                booking_request = BookingRequest(
                    case_id=case_id, work_order_id=action.work_order_id, contractor_id=action.contractor_id,
                    slot_id=action.slot_id, tenant_availability_ids=action.tenant_availability_ids,
                    access_confirmed=True, authorized_limit_pence=work_order.approved_limit_pence or 0,
                    idempotency_key=action_record.idempotency_key,
                )
                action_record.state = ActionState.RUNNING.value
                action_record.updated_at = utcnow()
                external_kind = "SCHEDULE_VISIT"
                external_payload = (booking_request, attempt_number, work_order.id)
            elif isinstance(action, DiscoverContractors):
                action_record.state = ActionState.RUNNING.value
                action_record.updated_at = utcnow()
                external_kind = "DISCOVER_CONTRACTORS"
                external_payload = action
            else:
                result = await _dispatch_local(session, case_id, action_record.id, action, trigger_event_id, actor, elevenlabs_configured=elevenlabs_configured)
                _record_terminal(action_record, ActionState.SUCCEEDED, result)
                return result
        except DomainError as exc:
            result = CommandResult(
                status=CommandResultStatus.REJECTED,
                case_version=(await services.load_case(session, case_id)).version,
                error=ToolError(code=exc.code, message=exc.message, retryable=exc.retryable, reconciliation_required=exc.reconciliation_required),
            )
            _record_terminal(action_record, ActionState.FAILED, result)
            return result

    # --- Phase B: outside any open transaction ---
    if external_kind == "SCHEDULE_VISIT":
        booking_request, attempt_number, work_order_id = external_payload
        async with session_scope() as booking_session:
            outcome = await mock_booking_connector.book(booking_session, booking_request, action_id=action_id)
        return await _apply_schedule_result(action_id, work_order_id, booking_request, attempt_number, outcome)

    if external_kind == "DISCOVER_CONTRACTORS":
        action = external_payload
        search_result = await research_adapter.search(case_id, action.trade, action.postcode)
        return await _apply_research_result(action_id, search_result)

    raise AssertionError("unreachable: no local result and no external kind selected")


async def _apply_schedule_result(action_id: str, work_order_id: str, booking_request: BookingRequest, attempt_number: int, outcome) -> CommandResult:
    from app.models import ActionRecordModel

    async with session_scope() as session:
        action_record = await session.get(ActionRecordModel, action_id)
        case = await services.load_case(session, action_record.case_id)
        work_order = await session.get(WorkOrderModel, work_order_id)

        if outcome.status == BookingStatus.CONFIRMED:
            appointment = AppointmentModel(
                id=new_uuid(), case_id=case.id, work_order_id=work_order.id,
                contractor_id=str(booking_request.contractor_id), slot_id=booking_request.slot_id,
                start_at=outcome.confirmed_start, end_at=outcome.confirmed_end, status="CONFIRMED",
                connector="MOCK", provider_booking_id=outcome.provider_booking_id, action_id=action_record.id,
                attempt_number=attempt_number, availability_revision=1, provenance=outcome.provenance,
            )
            session.add(appointment)
            assert_work_order_transition(work_order.status, WorkOrderStatus.SCHEDULED)
            work_order.status = WorkOrderStatus.SCHEDULED
            work_order.updated_at = utcnow()
            services.bump_version(case)
            event = await services.append_event(
                session, case_id=case.id, event_type="APPOINTMENT_CONFIRMED",
                payload={"appointment_id": appointment.id, "work_order_id": work_order.id},
                actor=ActorContext("EXECUTOR", "executor", action_record.id),
                source_event_key=f"booking:{action_record.idempotency_key}:confirmed",
            )
            result = CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id], resource_ids={"appointment_id": appointment.id})
            _record_terminal(action_record, ActionState.SUCCEEDED, result)
            return result

        if outcome.status in (BookingStatus.PENDING, BookingStatus.UNKNOWN):
            event = await services.append_event(
                session, case_id=case.id, event_type="ACTION_UNKNOWN",
                payload={"action_id": action_record.id, "reason": outcome.reason},
                actor=ActorContext("EXECUTOR", "executor", action_record.id),
                source_event_key=f"booking:{action_record.idempotency_key}:unknown",
            )
            result = CommandResult(status=CommandResultStatus.UNKNOWN, case_version=case.version, event_ids=[event.id], error=ToolError(code=ToolErrorCode.EXTERNAL_RESULT_UNKNOWN, message=outcome.reason or "booking outcome unknown", retryable=False, reconciliation_required=True))
            _record_terminal(action_record, ActionState.UNKNOWN, result)
            return result

        event = await services.append_event(
            session, case_id=case.id, event_type="ACTION_FAILED",
            payload={"action_id": action_record.id, "reason": outcome.reason},
            actor=ActorContext("EXECUTOR", "executor", action_record.id),
            source_event_key=f"booking:{action_record.idempotency_key}:failed",
        )
        result = CommandResult(status=CommandResultStatus.REJECTED, case_version=case.version, event_ids=[event.id], error=ToolError(code=ToolErrorCode.POLICY_REJECTED, message=outcome.reason or "booking rejected", retryable=False))
        _record_terminal(action_record, ActionState.FAILED, result)
        return result


async def _apply_research_result(action_id: str, search_result: ContractorSearchResult) -> CommandResult:
    from app.models import ActionRecordModel

    async with session_scope() as session:
        action_record = await session.get(ActionRecordModel, action_id)
        case = await services.load_case(session, action_record.case_id)

        snapshot = ResearchSnapshotModel(
            id=search_result.research.id, case_id=case.id, query=search_result.research.query,
            provider=search_result.research.provider, provider_request_id=search_result.research.provider_request_id,
            requested_at=search_result.research.requested_at, completed_at=search_result.research.completed_at,
            result_urls=search_result.research.result_urls,
            results=[r.model_dump(mode="json") for r in search_result.research.results],
            provenance=search_result.research.provenance,
        )
        session.add(snapshot)
        for candidate in search_result.candidates:
            session.add(
                ContractorCandidateModel(
                    id=candidate.id, case_id=case.id, research_id=snapshot.id, name=candidate.name,
                    trades=[t.value for t in candidate.trades], website=str(candidate.website) if candidate.website else None,
                    phone=candidate.phone, service_area=candidate.service_area,
                    claimed_emergency_service=candidate.claimed_emergency_service,
                    evidence=[e.model_dump(mode="json") for e in candidate.evidence],
                    verification_status=candidate.verification_status,
                )
            )
        event = await services.append_event(
            session, case_id=case.id, event_type="RESEARCH_COMPLETED",
            payload={"research_id": snapshot.id, "candidate_count": len(search_result.candidates)},
            actor=ActorContext("EXECUTOR", "executor", action_record.id),
            source_event_key=f"research:{snapshot.id}",
        )
        result = CommandResult(status=CommandResultStatus.APPLIED, case_version=case.version, event_ids=[event.id], resource_ids={"research_id": snapshot.id})
        _record_terminal(action_record, ActionState.SUCCEEDED, result)
        return result
