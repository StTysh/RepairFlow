"""Phase 3: the real coordinator's *mechanical* round trip -- agent.run()
through tool execution to a validated discriminated-union ActionProposal --
exercised with Pydantic AI's FunctionModel/TestModel so it needs zero
credentials (docs/22: "Pydantic AI's test models and function-model
facilities can control model behavior in unit tests"). What is genuinely
untestable without a live Gemini key is *semantic* interpretation quality
(novel phrasing, prompt-injection resistance) -- that's deferred to the
live-model evaluation gate in docs/22, reported UNMET in docs/23.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.coordinator import GeminiCoordinator, construct_agent
from app.db import session_scope
from app.domain import services
from app.domain.services import ActorContext
from app.models import CommunicationModel
from app.orchestration import dispatcher
from app.schemas import (
    AddPrerequisite,
    ApplyTriage,
    Escalate,
    EvidenceRef,
    IntakeSubmission,
    Provenance,
    ReportSubmission,
    RiskAssessment,
    SourceType,
    Trade,
    Wait,
    WorkOrderKind,
)

from tests.test_hero_path import _seed_reference_data, _work_order, uid


async def _case_with_pending_report():
    """A case with one BLOCKED-worthy report already recorded: a real REPAIR
    work order, SCHEDULED appointment, and a contractor report describing
    (in the agent's own novel wording, not hard-coded anywhere in app code)
    why the roofer can't proceed -- exactly the input the coordinator must
    turn into an AddPrerequisite proposal."""
    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    comm_id = uid()
    async with session_scope() as session:
        session.add(CommunicationModel(id=comm_id, purpose="INTAKE", direction="BROWSER", correlation_token_hash=uid(), state="ACTIVE", provenance="FIXTURE"))
    async with session_scope() as session:
        case_id, intake_result = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description="Water ingress near the roofline.", location="Rear bedroom ceiling", source_text="src",
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )
    async with session_scope() as session:
        triage_result = await services.apply_triage(
            session, case_id=case_id,
            action=ApplyTriage(
                risk=RiskAssessment(urgency="ROUTINE", gas="NO", fire="NO", water_near_electrics="NO", structural_danger="NO", uncontrolled_flood="NO", vulnerability_concern="NO"),
                issue_description="Water ingress near the roofline.", suggested_trade=Trade.ROOFING, scope="Repair roof ingress.",
            ),
            trigger_event_id=str(intake_result.event_ids[0]), actor=ActorContext("SYSTEM", "test-setup", uid()),
        )
    repair_wo = await _work_order(case_id, "REPAIR")

    from app.models import ActionRecordModel, AppointmentModel

    async with session_scope() as session:
        appt = AppointmentModel(
            id=uid(), case_id=case_id, work_order_id=repair_wo.id, contractor_id=roofer_id, slot_id="fixture-slot",
            start_at=datetime.now(timezone.utc), end_at=datetime.now(timezone.utc), status="CONFIRMED", connector="MOCK",
            provider_booking_id="mock-fixture", action_id=uid(), attempt_number=1, availability_revision=1, provenance="SIMULATED",
        )
        session.add(appt)
        session.add(ActionRecordModel(id=appt.action_id, case_id=case_id, kind="SCHEDULE_VISIT", idempotency_key=f"fixture:{appt.id}", payload_hash="fixture", proposal={}, state="SUCCEEDED"))

    async with session_scope() as session:
        report_id, _ = await services.record_contractor_report(
            session,
            submission=ReportSubmission(
                work_order_id=uuid.UUID(repair_wo.id), appointment_id=uuid.UUID(appt.id), contractor_id=uuid.UUID(roofer_id),
                text="Had a look today -- there's genuinely no way to reach those tiles off a ladder without real access "
                     "equipment in place first. I don't want to risk it.",
                observed_at=datetime.now(timezone.utc),
            ),
            source_ref=EvidenceRef(source_type=SourceType.REPORT, source_id=uid(), observed_at=datetime.now(timezone.utc), provenance=Provenance.SIMULATED),
            provenance=Provenance.SIMULATED, actor=ActorContext("CONTRACTOR_ADAPTER", roofer_id, uid()),
        )
    return case_id, report_id, repair_wo.id


def _last_trigger_event_id(messages: list[ModelMessage]) -> str:
    text = messages[0].parts[0].content
    for line in text.splitlines():
        if line.startswith("trigger_event_id:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("trigger_event_id not found in prompt")


@pytest.mark.asyncio
async def test_agent_calls_read_report_then_returns_add_prerequisite(app_db):
    case_id, report_id, repair_wo_id = await _case_with_pending_report()

    async with session_scope() as session:
        snapshot = await services.load_case_snapshot(session, case_id)

    call_count = {"n": 0}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ModelResponse(parts=[ToolCallPart(tool_name="read_report", args={"case_id": case_id, "record_id": report_id})])
        output_tool = info.output_tools[0].name
        trigger_event_id = _last_trigger_event_id(messages)
        proposal_args = {
            "case_id": case_id, "expected_case_version": snapshot.snapshot_version, "trigger_event_id": trigger_event_id,
            "decision_summary": "Roofer cannot safely reach the tiles without access equipment; scaffold required.",
            "evidence_refs": [{"source_type": "REPORT", "source_id": report_id, "observed_at": datetime.now(timezone.utc).isoformat(), "provenance": "SIMULATED"}],
            "action": {
                "kind": "ADD_PREREQUISITE", "report_id": report_id, "blocked_work_order_id": repair_wo_id,
                "prerequisite_trade": "SCAFFOLDING", "prerequisite_kind": "SCAFFOLD_INSTALL",
                "prerequisite_scope": "Erect scaffold for safe roof access.", "reason": "No safe ladder access per contractor report.",
            },
        }
        return ModelResponse(parts=[ToolCallPart(tool_name=output_tool, args=proposal_args)])

    agent = construct_agent(FunctionModel(respond))
    coordinator = GeminiCoordinator(agent, model_id="test-function-model")

    proposal = await coordinator.decide(snapshot, trigger_event_id=uid())

    assert call_count["n"] == 2, "the agent must actually invoke read_report, not just be offered it"
    assert isinstance(proposal.action, AddPrerequisite)
    assert str(proposal.action.report_id) == report_id
    assert str(proposal.action.blocked_work_order_id) == repair_wo_id
    assert proposal.action.prerequisite_kind == WorkOrderKind.SCAFFOLD_INSTALL

    # And the resulting proposal is a real, executable ActionProposal --
    # confirm it clears the same admission path the worker uses.
    async with session_scope() as session:
        from app.orchestration.executor import admit_proposal

        record = await admit_proposal(session, proposal, ActorContext("COORDINATOR", coordinator.model_id, uid()))
        assert record.kind == "ADD_PREREQUISITE"


@pytest.mark.asyncio
async def test_agent_direct_output_wait(app_db):
    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    comm_id = uid()
    async with session_scope() as session:
        session.add(CommunicationModel(id=comm_id, purpose="INTAKE", direction="BROWSER", correlation_token_hash=uid(), state="ACTIVE", provenance="FIXTURE"))
    async with session_scope() as session:
        case_id, _ = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description="desc", location="loc", source_text="src",
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output_tool = info.output_tools[0].name
        trigger_event_id = _last_trigger_event_id(messages)
        return ModelResponse(parts=[ToolCallPart(tool_name=output_tool, args={
            "case_id": case_id, "expected_case_version": 1, "trigger_event_id": trigger_event_id,
            "decision_summary": "Nothing new to do yet.", "evidence_refs": [],
            "action": {"kind": "WAIT", "reason": "awaiting first triage", "waiting_for": "nothing specific"},
        })])

    agent = construct_agent(FunctionModel(respond))
    coordinator = GeminiCoordinator(agent, model_id="test-function-model")

    async with session_scope() as session:
        snapshot = await services.load_case_snapshot(session, case_id)

    proposal = await coordinator.decide(snapshot, trigger_event_id=uid())
    assert isinstance(proposal.action, Wait)


@pytest.mark.asyncio
async def test_hazard_gate_bypasses_coordinator_entirely(app_db):
    """docs/13: the deterministic safety gate runs before the model is ever
    called. A coordinator that raises if invoked proves it truly wasn't."""

    class PoisonCoordinator:
        model_id = "poison"

        async def decide(self, snapshot, trigger_event_id):
            raise AssertionError("coordinator must not be invoked when the hazard gate fires")

    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    comm_id = uid()
    async with session_scope() as session:
        session.add(CommunicationModel(id=comm_id, purpose="INTAKE", direction="BROWSER", correlation_token_hash=uid(), state="ACTIVE", provenance="FIXTURE"))
    async with session_scope() as session:
        case_id, intake_result = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description="Smell of gas near the boiler.", location="Airing cupboard", source_text="src",
                safety_answers={"gas": "YES"},
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )
    trigger_event_id = str(intake_result.event_ids[0])

    record = await dispatcher.run_coordinate(case_id=case_id, trigger_event_id=trigger_event_id, coordinator=PoisonCoordinator())
    assert record is None

    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        assert case.status == "ESCALATED"
        assert case.escalation_reason
