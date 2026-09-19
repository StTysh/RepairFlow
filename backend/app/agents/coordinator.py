"""The one central Pydantic AI coordinator (docs/08/09/13).

GeminiCoordinator implements the same `Coordinator` Protocol as
orchestration/dispatcher.py's FixtureCoordinator, so dispatcher.py and
worker.py never need to know which one is wired up. build_coordinator()
picks the real one when GEMINI_API_KEY is configured and an explicitly
labelled conservative fallback otherwise (docs/04: fixture substitute must
be labelled, never silently passed off as live reasoning).
"""
from __future__ import annotations

import asyncio
import uuid

from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.output import ToolOutput
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from app.agents.dependencies import CoordinatorDeps
from app.agents.instructions import COORDINATOR_INSTRUCTIONS
from app.agents.read_tools import find_appointment_options, list_case_events, read_communication, read_report, read_research
from app.config import Settings
from app.schemas import ActionProposal, CaseSnapshot, Wait

RUN_TIMEOUT_SECONDS = 45
MAX_MODEL_REQUESTS = 4
MAX_TOOL_CALLS = 3


def construct_agent(model) -> Agent[CoordinatorDeps, ActionProposal]:
    """Builds the coordinator agent for any Pydantic AI model instance --
    the real GoogleModel in production, or a TestModel/FunctionModel in
    tests, with identical tool wiring either way."""
    agent = Agent(
        model,
        deps_type=CoordinatorDeps,
        output_type=ToolOutput(ActionProposal),
        instructions=COORDINATOR_INSTRUCTIONS,
        model_settings=ModelSettings(timeout=RUN_TIMEOUT_SECONDS),
        retries=1,
    )
    agent.tool(read_report)
    agent.tool(read_communication)
    agent.tool(list_case_events)
    agent.tool(find_appointment_options)
    agent.tool(read_research)
    return agent


def build_agent(model_name: str, api_key: str) -> Agent[CoordinatorDeps, ActionProposal]:
    return construct_agent(GoogleModel(model_name, provider=GoogleProvider(api_key=api_key)))


def _redact_snapshot(snapshot: CaseSnapshot) -> dict:
    data = snapshot.model_dump(mode="json")
    for comm in data.get("communications", []):
        recording = comm.get("recording")
        if recording:
            recording["media_path"] = None
    return data


def _format_prompt(snapshot: CaseSnapshot, trigger_event_id: str) -> str:
    import json

    payload = _redact_snapshot(snapshot)
    return (
        "A new event just occurred on this repair case. Decide the single next action.\n\n"
        f"trigger_event_id: {trigger_event_id}\n\n"
        "Current case snapshot (JSON):\n"
        f"{json.dumps(payload, indent=2)}"
    )


class GeminiCoordinator:
    def __init__(self, agent: Agent[CoordinatorDeps, ActionProposal], model_id: str):
        self._agent = agent
        self.model_id = model_id

    async def decide(self, snapshot: CaseSnapshot, trigger_event_id: str) -> ActionProposal:
        prompt = _format_prompt(snapshot, trigger_event_id)
        deps = CoordinatorDeps(
            case_id=str(snapshot.case.id), snapshot_version=snapshot.snapshot_version,
            run_id=str(uuid.uuid4()), policy_snapshot=snapshot.policy_snapshot,
        )
        result = await asyncio.wait_for(
            self._agent.run(
                prompt, deps=deps,
                usage_limits=UsageLimits(request_limit=MAX_MODEL_REQUESTS, tool_calls_limit=MAX_TOOL_CALLS),
            ),
            timeout=RUN_TIMEOUT_SECONDS,
        )
        return result.output


class ConservativeFixtureCoordinator:
    """Wired up when no GEMINI_API_KEY is configured. Handles only the
    mechanical, non-interpretive step (triage a case with no work order
    yet, using the safety answers already on record) and otherwise WAITs
    with an explicit FIXTURE-mode explanation -- it must never guess at
    semantic interpretation of a report, which would misrepresent a
    keyword match as model reasoning (docs/04)."""

    model_id = "fixture-conservative"

    async def decide(self, snapshot: CaseSnapshot, trigger_event_id: str) -> ActionProposal:
        from app.schemas import ApplyTriage, Trade

        if not snapshot.work_orders:
            return ActionProposal(
                case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
                decision_summary="FIXTURE mode (no live model configured): applying recorded safety answers without semantic interpretation.",
                evidence_refs=[], action=ApplyTriage(
                    risk=snapshot.case.risk, issue_description=snapshot.issue.description, suggested_trade=Trade.OTHER,
                    scope=snapshot.issue.description,
                ),
            )
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="FIXTURE mode: no live model configured, so no new semantic interpretation is attempted; waiting for operator review.",
            evidence_refs=[], action=Wait(reason="no live coordinator configured", waiting_for="GEMINI_API_KEY / operator review"),
        )


def build_coordinator(settings: Settings):
    if settings.gemini_live:
        agent = build_agent(settings.gemini_model, settings.gemini_api_key)
        return GeminiCoordinator(agent, model_id=settings.gemini_model)
    return ConservativeFixtureCoordinator()
