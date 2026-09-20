"""Turns a leased COORDINATE job into (at most) one admitted ActionProposal.

Runs the deterministic hazard gate and the root-loop budget check *before*
ever invoking a Coordinator implementation, per docs/13 ("the deterministic
safety gate runs before the call and before execution") and docs/07 ("a
root trigger may drive at most six consequential actions before pausing").
Phase 2 uses FixtureCoordinator; Phase 3 swaps in the real Pydantic AI
coordinator behind the same Protocol, so this module does not change.
"""
from __future__ import annotations

from typing import Callable, Protocol, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import policy, services
from app.domain.errors import DomainError, StaleVersionError
from app.domain.services import ActorContext
from app.models import ActionRecordModel, CaseEventModel, OrchestrationRunModel
from app.schemas import ActionProposal, CaseSnapshot, OrchestrationRunState, RiskAssessment, utcnow

ROOT_LOOP_BUDGET = 6


class Coordinator(Protocol):
    model_id: str

    async def decide(self, snapshot: CaseSnapshot, trigger_event_id: str) -> ActionProposal: ...


FixtureDecision = Union[ActionProposal, Callable[[CaseSnapshot, str], ActionProposal]]


class FixtureCoordinator:
    """Test/dev double: returns pre-scripted proposals in order. Each queued
    entry is either a fixed ActionProposal or a builder callable
    `(snapshot, trigger_event_id) -> ActionProposal` resolved lazily at
    decide()-time -- tests use builders so they don't have to hand-compute
    case versions or generated IDs ahead of time. A coordinator using this
    class never talks to a real model, so every decision it produces must
    be labelled FIXTURE by the caller."""

    model_id = "fixture-coordinator"

    def __init__(self, decisions: list[FixtureDecision] | None = None):
        self._queue: list[FixtureDecision] = list(decisions or [])

    def queue(self, decision: FixtureDecision) -> None:
        self._queue.append(decision)

    async def decide(self, snapshot: CaseSnapshot, trigger_event_id: str) -> ActionProposal:
        if not self._queue:
            from app.schemas import Wait

            return ActionProposal(
                case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version,
                trigger_event_id=trigger_event_id, decision_summary="Fixture coordinator has no queued decision; waiting.",
                evidence_refs=[], action=Wait(reason="no fixture proposal queued", waiting_for="test input"),
            )
        next_decision = self._queue.pop(0)
        if callable(next_decision):
            import inspect

            result = next_decision(snapshot, trigger_event_id)
            if inspect.isawaitable(result):
                result = await result
            return result
        return next_decision


async def _internal_chain_depth(session: AsyncSession, trigger_event_id: str) -> int:
    """How many hops back through unbroken causation links precede this
    trigger. A fresh external event (report, approval, observation, intake)
    always has causation_event_id=None, so the depth naturally resets there
    -- this measures a *pure internal cascade*, not the case's total
    lifetime action count (docs/07: "a root trigger may drive at most six
    consequential actions ... prevents an internal event feedback loop")."""
    depth = 0
    current_id: str | None = trigger_event_id
    seen: set[str] = set()
    while current_id and current_id not in seen and depth <= 20:
        seen.add(current_id)
        event = await session.get(CaseEventModel, current_id)
        if event is None or event.causation_event_id is None:
            break
        depth += 1
        current_id = event.causation_event_id
    return depth


async def run_coordinate(*, case_id: str, trigger_event_id: str, coordinator: Coordinator) -> ActionRecordModel | None:
    """One bounded reasoning run. Returns the admitted ActionRecord, or None
    if the run was diverted (hazard gate, loop budget) or the model's
    proposal was stale and needs to be retried at the current version.

    Three phases, exactly like executor.execute_action's SCHEDULE_VISIT/
    DISCOVER_CONTRACTORS pattern: commit intent (creating the RUNNING
    OrchestrationRun row), call the model with no transaction open at all
    (this is the one call in the whole codebase that may be a real,
    multi-second network round trip to Gemini -- CLAUDE.md: "Do not hold a
    DB transaction across any network/model call"), then apply the result
    in a fresh transaction. Manages its own session boundaries rather than
    taking one from the caller for exactly this reason."""
    from app.db import session_scope

    async with session_scope() as session:
        case = await services.load_case(session, case_id)

        # A case that is escalated or cancelled is, by definition, not
        # being handled automatically any more: ESCALATED means a human
        # was asked to take it, CANCELLED means it is closed. Waking the
        # coordinator on either one would let the model propose — and the
        # executor then perform — work on a case nobody is expecting
        # movement on, including an outbound call. A stale COORDINATE job
        # left in the durable queue is enough to trigger it on the next
        # boot, with no fresh operator action anywhere in the chain.
        #
        # This sits above the hazard gate deliberately: escalating an
        # already-escalated case would append a second CASE_ESCALATED
        # event for the same standing reason.
        if case.status in ("ESCALATED", "CANCELLED", "RESOLVED"):  # TEMP: reintroduced bug for regression-test verification
            return None

        risk = RiskAssessment.model_validate(case.risk)
        # RESOLVED is NOT excluded. A hazard reported after a repair was
        # signed off is exactly the case that most needs escalating —
        # someone is telling you the property is unsafe *now*. Excluding
        # it here was the whole of the "RESOLVED -> ESCALATED is broken"
        # bug: the transition graph has always permitted that edge and
        # escalate_to_human has always been able to make it; this gate
        # simply never called it.
        if policy.is_hazard(risk):
            from app.schemas import Escalate

            await services.escalate_to_human(
                session, case_id=case_id,
                action=Escalate(reason_code="HAZARD", operator_message="Deterministic hazard gate: unsafe condition on record.", evidence_refs=[]),
                trigger_event_id=trigger_event_id, actor=ActorContext("SYSTEM", "hazard-gate", trigger_event_id),
            )
            return None

        if await _internal_chain_depth(session, trigger_event_id) >= ROOT_LOOP_BUDGET:
            from app.schemas import Escalate

            await services.escalate_to_human(
                session, case_id=case_id,
                action=Escalate(reason_code="ROOT_LOOP_BUDGET_EXCEEDED", operator_message="Too many automatic actions without a pause; needs human review.", evidence_refs=[]),
                trigger_event_id=trigger_event_id, actor=ActorContext("SYSTEM", "loop-budget", trigger_event_id),
            )
            return None

        snapshot = await services.load_case_snapshot(session, case_id)

        # docs/17: OrchestrationRun is the only auditable record of what the
        # model actually did on a given trigger -- persisted around the call
        # itself (not the hazard/loop-budget diversions above, which never
        # invoke a model at all) so GET /cases/{id}/runs has real content and
        # a failed/timed-out model call is visible rather than silently
        # swallowed into JobModel.last_error by the worker's error handling.
        run = OrchestrationRunModel(
            case_id=case_id, trigger_event_id=trigger_event_id, snapshot_version=snapshot.snapshot_version,
            model_id=coordinator.model_id, state=OrchestrationRunState.RUNNING,
        )
        session.add(run)
        await session.flush()
        run_id = run.id

    # --- Phase B: outside any open transaction ---
    try:
        proposal = await coordinator.decide(snapshot, trigger_event_id)
    except Exception as exc:
        async with session_scope() as session:
            run = await session.get(OrchestrationRunModel, run_id)
            run.state = OrchestrationRunState.FAILED
            run.finished_at = utcnow()
            run.error_code = type(exc).__name__
        raise

    # --- Phase C: apply the result in a fresh transaction ---
    async with session_scope() as session:
        run = await session.get(OrchestrationRunModel, run_id)
        run.proposal = proposal.model_dump(mode="json")
        run.finished_at = utcnow()

        try:
            from app.orchestration.executor import admit_proposal

            action_record = await admit_proposal(session, proposal, ActorContext("COORDINATOR", coordinator.model_id, trigger_event_id))
            run.state = OrchestrationRunState.SUCCEEDED
            run.policy_result = action_record.state
            return action_record
        except StaleVersionError:
            run.state = OrchestrationRunState.SUPERSEDED
            run.policy_result = "stale_version_requeued"
            current_case = await services.load_case(session, case_id)
            await services.enqueue_job(
                session, case_id=case_id, kind="COORDINATE",
                dedupe_key=f"coordinate:{case_id}:{current_case.version}", payload={"trigger_event_id": trigger_event_id},
            )
            return None
        except DomainError as exc:
            run.state = OrchestrationRunState.FAILED
            run.error_code = getattr(exc, "code", type(exc).__name__)
            raise
