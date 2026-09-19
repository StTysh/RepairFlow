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
from app.models import CaseEventModel
from app.schemas import ActionProposal, CaseSnapshot, RiskAssessment

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


async def run_coordinate(session: AsyncSession, *, case_id: str, trigger_event_id: str, coordinator: Coordinator) -> ActionRecordModel | None:
    """One bounded reasoning run. Returns the admitted ActionRecord, or None
    if the run was diverted (hazard gate, loop budget) or the model's
    proposal was stale and needs to be retried at the current version."""
    case = await services.load_case(session, case_id)

    risk = RiskAssessment.model_validate(case.risk)
    if policy.is_hazard(risk) and case.status not in ("ESCALATED", "CANCELLED", "RESOLVED"):
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
    proposal = await coordinator.decide(snapshot, trigger_event_id)

    try:
        from app.orchestration.executor import admit_proposal

        action_record = await admit_proposal(session, proposal, ActorContext("COORDINATOR", coordinator.model_id, trigger_event_id))
        return action_record
    except StaleVersionError:
        await services.enqueue_job(
            session, case_id=case_id, kind="COORDINATE",
            dedupe_key=f"coordinate:{case_id}:{case.version}", payload={"trigger_event_id": trigger_event_id},
        )
        return None
    except DomainError:
        raise
