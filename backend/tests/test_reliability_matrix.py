"""docs/22's broader reliability matrix, beyond Phase 2's own duplicate-
report/restart gate (test_phase2_reliability.py) and the hero path itself
(test_hero_path.py). Each test here targets one specific architectural
invariant CLAUDE.md states explicitly, using the same app_db/session_scope
conventions as the rest of the suite.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db import session_scope
from app.domain import dependencies as dep_graph
from app.domain import services
from app.domain.errors import PolicyRejectedError
from app.domain.services import ActorContext
from app.models import (
    CommunicationModel,
    JobModel,
    OrchestrationRunModel,
)
from app.orchestration import dispatcher, worker
from app.orchestration.dispatcher import FixtureCoordinator
from app.orchestration.executor import _apply_schedule_result
from app.schemas import (
    ActionProposal,
    ApplyTriage,
    BookingOutcome,
    BookingRequest,
    BookingStatus,
    CaseStatus,
    IntakeSubmission,
    ObservationSubmission,
    Provenance,
    RiskAssessment,
    Trade,
    WorkOrderStatus,
)

from tests.test_hero_path import _seed_reference_data, _work_order, uid
from tests.test_phase2_reliability import _drive_to_blocked_repair


# --------------------------------------------------------------------------
# Cyclic dependency rejection (docs/07: the dependency graph is a DAG)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_would_create_cycle_detects_a_real_cycle_and_rejects_it(app_db):
    """add_prerequisite itself always creates a brand-new prerequisite work
    order, so a cycle can never actually form through its exact call
    pattern (a fresh node cannot already be reachable from anything) --
    the cycle check it calls is still real, load-bearing code, so this
    exercises it against a genuine FK-compliant graph (the real
    install -> repair -> removal chain the hero path produces) rather than
    hand-rolling synthetic rows through four levels of foreign keys just
    to satisfy the schema."""
    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    case_id, _report_id, _coordinator = await _drive_to_blocked_repair(uid(), property_id, tenant_id, roofer_id, scaffolder_id)

    install_wo = await _work_order(case_id, "SCAFFOLD_INSTALL")
    repair_wo = await _work_order(case_id, "REPAIR")
    removal_wo = await _work_order(case_id, "SCAFFOLD_REMOVE")
    # Real graph on record: install -> repair -> removal

    async with session_scope() as session:
        # removal as a prerequisite of install would close install -> repair
        # -> removal -> install into a loop
        assert await dep_graph.would_create_cycle(session, case_id, removal_wo.id, install_wo.id) is True
        # install as a prerequisite of a brand-new, unconnected node is a
        # legitimate new branch, not a cycle
        assert await dep_graph.would_create_cycle(session, case_id, install_wo.id, uid()) is False
        # a self-loop is always rejected outright, independent of the graph
        assert await dep_graph.would_create_cycle(session, case_id, install_wo.id, install_wo.id) is True


# --------------------------------------------------------------------------
# Expired lease reclaim (docs/17: a crashed/hung worker must not strand a job)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_lease_is_reclaimed_by_a_new_worker(app_db):
    job_id = uid()
    past = datetime.now(timezone.utc) - timedelta(seconds=5)
    async with session_scope() as session:
        session.add(JobModel(
            id=job_id, case_id=None, kind="FOLLOW_UP", dedupe_key=f"stale:{job_id}",
            payload={}, run_at=past - timedelta(seconds=120), status="LEASED",
            attempts=1, lease_until=past,  # lease already expired
        ))

    async with session_scope() as session:
        claimed = await worker.claim_job(session)
        assert claimed is not None and claimed.id == job_id
        assert claimed.status == "LEASED"
        assert claimed.attempts == 2, "a reclaim counts as a new attempt"
        assert claimed.lease_until > past, "the lease must be extended, not left in the past"


# --------------------------------------------------------------------------
# Negative/absent tenant confirmation must never be inferred as resolution
# (CLAUDE.md non-negotiable: "no closure inferred from silence")
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_negative_tenant_confirmation_blocks_resolution(app_db):
    property_id, tenant_id, _roofer_id, _scaffolder_id = await _seed_reference_data()
    comm_id = uid()
    async with session_scope() as session:
        session.add(CommunicationModel(id=comm_id, purpose="INTAKE", direction="BROWSER", correlation_token_hash=uid(), state="ACTIVE", provenance="FIXTURE"))
    async with session_scope() as session:
        case_id, _ = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description="Minor issue, no repair work required.", location="Hallway", source_text="src",
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )

    # Force the case into AWAITING_CONFIRMATION directly (bypassing the
    # normal all-required-work-completed path) so this test isolates the
    # tenant-confirmation handling. No required work orders exist, so that
    # part of resolve_case's precondition passes vacuously either way.
    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        case.status = CaseStatus.AWAITING_CONFIRMATION

    feedback_comm_id = uid()
    async with session_scope() as session:
        session.add(CommunicationModel(
            id=feedback_comm_id, case_id=case_id, tenant_id=tenant_id, purpose="FOLLOW_UP", direction="BROWSER",
            correlation_token_hash=uid(), state="ENDED", provenance="SIMULATED",
        ))
        await services.record_observations(
            session, case_id=case_id, communication_id=feedback_comm_id,
            submission=ObservationSubmission(communication_id=uuid.UUID(feedback_comm_id), tenant_confirms_resolved=False, source_text="No, it's still leaking."),
            actor=ActorContext("VOICE_TOOL", feedback_comm_id, feedback_comm_id),
        )

    # record_observations itself already reverts AWAITING_CONFIRMATION back
    # to ACTIVE on a negative confirmation (services.py line ~385) -- a
    # stronger safety property than "resolve_case alone rejects it": the
    # case is proactively reopened rather than left sitting in a state
    # where a later resolve attempt is the only thing standing between a
    # negative confirmation and a wrongly-closed case.
    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        issue = await services.load_issue(session, case_id)
        assert case.status == CaseStatus.ACTIVE, "a negative confirmation must reopen the case, not leave it awaiting"
        assert issue.tenant_resolution_confirmed_at is None
        assert "tenant reports issue still unresolved" in issue.unresolved_concerns

        from app.schemas import ResolveCase

        with pytest.raises(PolicyRejectedError, match="not awaiting confirmation"):
            await services.resolve_case(
                session, case_id=case_id, action=ResolveCase(issue_id=uuid.UUID(issue.id), confirmation_event_id=uuid.uuid4()),
                trigger_event_id=uid(), actor=ActorContext("COORDINATOR", "test", uid()),
            )

    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        assert case.status == CaseStatus.ACTIVE, "a rejected resolve attempt must not silently change case status"


# --------------------------------------------------------------------------
# Stale model proposal: re-enqueued at the current version, never silently
# dropped and never applied against outdated state (docs/10's version-check
# paragraph)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_proposal_version_is_superseded_and_requeued(app_db):
    property_id, tenant_id, _roofer_id, _scaffolder_id = await _seed_reference_data()
    comm_id = uid()
    async with session_scope() as session:
        session.add(CommunicationModel(id=comm_id, purpose="INTAKE", direction="BROWSER", correlation_token_hash=uid(), state="ACTIVE", provenance="FIXTURE"))
    async with session_scope() as session:
        case_id, intake_result = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description="Roof leak.", location="Attic", source_text="src",
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )
    trigger_event_id = str(intake_result.event_ids[0])

    async with session_scope() as session:
        case_before = await services.load_case(session, case_id)
        stale_version = case_before.version
        # Bump the case version out from under the coordinator, simulating
        # a second actor (approval, another job) racing ahead first.
        services.bump_version(case_before)

    stale_proposal = ActionProposal(
        case_id=case_id, expected_case_version=stale_version, trigger_event_id=trigger_event_id,
        decision_summary="Stale decision computed against an old snapshot.", evidence_refs=[],
        action=ApplyTriage(
            risk=RiskAssessment(urgency="ROUTINE", gas="NO", fire="NO", water_near_electrics="NO", structural_danger="NO", uncontrolled_flood="NO", vulnerability_concern="NO"),
            issue_description="Roof leak.", suggested_trade=Trade.ROOFING, scope="Repair roof leak.",
        ),
    )
    coordinator = FixtureCoordinator([stale_proposal])

    record = await dispatcher.run_coordinate(case_id=case_id, trigger_event_id=trigger_event_id, coordinator=coordinator)
    assert record is None, "a stale proposal must never be admitted"

    async with session_scope() as session:
        jobs = (await session.execute(select(JobModel).where(JobModel.case_id == case_id, JobModel.kind == "COORDINATE"))).scalars().all()
        assert any(j.status == "PENDING" for j in jobs), "a fresh COORDINATE job must be enqueued at the current version"

        runs = (await session.execute(select(OrchestrationRunModel).where(OrchestrationRunModel.case_id == case_id))).scalars().all()
        assert len(runs) == 1
        assert runs[0].state == "SUPERSEDED"
        assert runs[0].finished_at is not None


# --------------------------------------------------------------------------
# Uncertain external booking result: preserved as UNKNOWN, never silently
# upgraded to confirmed or silently dropped (CLAUDE.md: "provider request
# acceptance is not booking confirmation")
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uncertain_booking_outcome_is_recorded_as_unknown_not_confirmed(app_db):
    property_id, tenant_id, roofer_id, _scaffolder_id = await _seed_reference_data()
    comm_id = uid()
    async with session_scope() as session:
        session.add(CommunicationModel(id=comm_id, purpose="INTAKE", direction="BROWSER", correlation_token_hash=uid(), state="ACTIVE", provenance="FIXTURE"))
    async with session_scope() as session:
        case_id, _ = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description="Roof leak.", location="Attic", source_text="src",
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )

    coordinator = FixtureCoordinator()

    async def triage(snapshot, trigger_event_id) -> ActionProposal:
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="Safe routine roof leak.", evidence_refs=[],
            action=ApplyTriage(
                risk=RiskAssessment(urgency="ROUTINE", gas="NO", fire="NO", water_near_electrics="NO", structural_danger="NO", uncontrolled_flood="NO", vulnerability_concern="NO"),
                issue_description="Roof leak.", suggested_trade=Trade.ROOFING, scope="Repair roof leak.",
            ),
        )

    coordinator.queue(triage)
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    from app.models import ActionRecordModel, WorkOrderModel

    async with session_scope() as session:
        work_order = (await session.execute(select(WorkOrderModel).where(WorkOrderModel.case_id == case_id))).scalars().first()
        action_record = ActionRecordModel(
            id=uid(), case_id=case_id, kind="SCHEDULE_VISIT", target_id=work_order.id,
            idempotency_key=f"booking:{work_order.id}:uncertain", payload_hash="test-hash",
            proposal={
                "case_id": case_id, "expected_case_version": 1, "trigger_event_id": uid(),
                "decision_summary": "test", "evidence_refs": [],
                "action": {"kind": "SCHEDULE_VISIT", "work_order_id": work_order.id, "contractor_id": roofer_id, "slot_id": "test-slot", "tenant_availability_ids": []},
            },
            state="RUNNING",
        )
        session.add(action_record)
        action_id = action_record.id
        work_order_id = work_order.id

    outcome = BookingOutcome(status=BookingStatus.UNKNOWN, reason="provider request timed out mid-response", provenance=Provenance.SIMULATED)
    booking_request = BookingRequest(
        case_id=uuid.UUID(case_id), work_order_id=uuid.UUID(work_order_id), contractor_id=uuid.UUID(roofer_id),
        slot_id="test-slot", tenant_availability_ids=[], access_confirmed=True, authorized_limit_pence=0,
        idempotency_key="booking:test:uncertain",
    )
    result = await _apply_schedule_result(action_id, work_order_id, booking_request, 1, outcome)

    assert result.status.value == "UNKNOWN"
    assert result.error.code.value == "EXTERNAL_RESULT_UNKNOWN"
    assert result.error.reconciliation_required is True

    async with session_scope() as session:
        wo = await session.get(WorkOrderModel, work_order_id)
        assert wo.status != WorkOrderStatus.SCHEDULED, "an uncertain outcome must never be recorded as a confirmed booking"
        action = await session.get(ActionRecordModel, action_id)
        assert action.state == "UNKNOWN"
