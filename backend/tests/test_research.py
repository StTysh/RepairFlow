"""Phase 6: Tavily contractor research (docs/12). No live TAVILY_API_KEY
exists in this environment -- these tests never touch the real network.
`TavilyResearchAdapter`'s HTTP boundary is stubbed with httpx.MockTransport,
which is real httpx request/response handling end to end, just against a
fake transport instead of a socket.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.domain import services
from app.domain.services import ActorContext
from app.integrations.tavily import TavilyResearchAdapter, _build_query
from app.models import CommunicationModel, ContractorCandidateModel, ResearchSnapshotModel
from app.orchestration import worker
from app.orchestration.dispatcher import FixtureCoordinator
from app.orchestration.executor import admit_proposal, execute_action
from app.schemas import (
    ActionProposal,
    DiscoverContractors,
    IntakeSubmission,
    Provenance,
    Trade,
    VerificationStatus,
)

from tests.test_hero_path import _seed_reference_data, uid


def _stub_client_factory(handler):
    """Monkeypatch target: httpx.AsyncClient(timeout=...) inside tavily.py
    must return a client wired to a MockTransport instead of a real socket."""

    class _StubAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    return _StubAsyncClient


# --------------------------------------------------------------------------
# TavilyResearchAdapter response-mapping, no database and no real network
# --------------------------------------------------------------------------


def test_build_query_never_includes_tenant_identity():
    query = _build_query(Trade.ROOFING, "BS1 1AA")
    assert "roofing" in query.lower()
    assert "bs1 1aa" in query.lower()
    # nothing tenant-identifying could leak in since the function only
    # accepts trade+postcode -- this assertion documents that contract.
    assert "tenant" not in query.lower()


@pytest.mark.asyncio
async def test_tavily_adapter_maps_results_groups_domains_and_stays_unverified(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("TAVILY_API_KEY", "test-key-not-real")
    get_settings.cache_clear()

    long_excerpt = "x" * 900  # must be truncated to 400 chars

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.tavily.com/search"
        assert request.headers["authorization"] == "Bearer test-key-not-real"
        return httpx.Response(
            200,
            json={
                "request_id": "req-123",
                "results": [
                    {"url": "https://apexroofing.example/contact", "title": "Apex Roofing 24/7 Emergency Callout", "content": "We offer emergency roofing repairs.", "score": 0.91},
                    {"url": "https://apexroofing.example/services", "title": "Apex Roofing Services", "content": long_excerpt, "score": 0.80},
                    {"url": "https://www.otherroofer.example/", "title": "Other Roofer Ltd", "content": "Local roofing contractor.", "score": 0.65},
                ],
            },
        )

    monkeypatch.setattr("app.integrations.tavily.httpx.AsyncClient", _stub_client_factory(handler))

    adapter = TavilyResearchAdapter()
    case_id = uid()
    result = await adapter.search(case_id, Trade.ROOFING, "BS1")

    assert result.research.provenance == Provenance.LIVE
    assert result.research.provider_request_id == "req-123"
    assert len(result.research.results) == 3
    assert len(result.research.results[1].excerpt) == 400, "excerpt must be bounded, not the full page"
    assert not result.warnings

    # two distinct domains (apexroofing.example, otherroofer.example) ->
    # two candidates, even though apexroofing.example had two results.
    assert len(result.candidates) == 2
    by_domain = {str(c.website): c for c in result.candidates}
    apex = next(c for c in result.candidates if "apexroofing" in str(c.website))
    other = next(c for c in result.candidates if "otherroofer" in str(c.website))

    assert apex.name == "Apex Roofing 24/7 Emergency Callout"  # highest-scoring title in that domain group
    assert len(apex.evidence) == 2, "both apexroofing.example results should be cited as evidence for one candidate"
    assert apex.claimed_emergency_service is True
    assert other.claimed_emergency_service is None, "no emergency claim in the source text -- must stay unknown, not False"

    for candidate in result.candidates:
        assert candidate.verification_status == VerificationStatus.UNVERIFIED
        assert candidate.phone is None, "phone must never be guessed from a snippet"
        assert candidate.service_area is None, "service_area must never be guessed from a snippet"
        assert candidate.case_id == uuid.UUID(case_id)
        assert candidate.research_id == result.research.id


@pytest.mark.asyncio
async def test_tavily_adapter_no_results_preserves_attempt_with_warning(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("TAVILY_API_KEY", "test-key-not-real")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr("app.integrations.tavily.httpx.AsyncClient", _stub_client_factory(handler))

    adapter = TavilyResearchAdapter()
    result = await adapter.search(uid(), Trade.PLUMBING, "BS2")

    assert result.candidates == []
    assert result.research.results == []
    assert len(result.warnings) == 1
    assert "no results" in result.warnings[0].lower()


@pytest.mark.asyncio
async def test_tavily_adapter_provider_failure_retries_once_then_degrades_gracefully(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("TAVILY_API_KEY", "test-key-not-real")
    get_settings.cache_clear()

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(503, json={"error": "temporarily unavailable"})

    monkeypatch.setattr("app.integrations.tavily.httpx.AsyncClient", _stub_client_factory(handler))

    adapter = TavilyResearchAdapter()
    result = await adapter.search(uid(), Trade.ELECTRICAL, "BS3")

    assert call_count["n"] == 2, "exactly one retry on a transient failure, per docs/12's budget"
    assert result.candidates == []
    assert result.research.results == []
    assert result.warnings and "failed" in result.warnings[0].lower()
    # a provider failure must never fabricate a result
    assert result.research.query  # the attempt itself is still preserved


# --------------------------------------------------------------------------
# End-to-end DISCOVER_CONTRACTORS execution, FixtureResearchAdapter default
# (no TAVILY_API_KEY in these -- this is the always-available no-credentials
# path exercised by the real worker/executor, not the adapter in isolation)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_contractors_executes_with_fixture_adapter_by_default(app_db):
    property_id, tenant_id, _roofer_id, _scaffolder_id = await _seed_reference_data()
    comm_id = uid()
    async with session_scope() as session:
        session.add(
            CommunicationModel(id=comm_id, purpose="INTAKE", direction="BROWSER", correlation_token_hash=uid(), state="ACTIVE", provenance="FIXTURE")
        )
    async with session_scope() as session:
        case_id, _ = await services.submit_intake(
            session, communication_id=comm_id,
            submission=IntakeSubmission(
                communication_id=uuid.UUID(comm_id), property_id=uuid.UUID(property_id), tenant_id=uuid.UUID(tenant_id),
                description="Leaking gutter.", location="Front elevation", source_text="src",
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )

    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        from app.models import CaseEventModel

        trigger_event = (
            await session.execute(select(CaseEventModel).where(CaseEventModel.case_id == case_id).order_by(CaseEventModel.seq))
        ).scalars().first()

        proposal = ActionProposal(
            case_id=case.id, expected_case_version=case.version, trigger_event_id=trigger_event.id,
            decision_summary="Discovering candidate roofers near the property.", evidence_refs=[],
            action=DiscoverContractors(trade=Trade.ROOFING, postcode="BS1"),
        )
        action_record = await admit_proposal(session, proposal, ActorContext("COORDINATOR", "test", uid()))

    # DISCOVER_CONTRACTORS never requires approval (executor._needs_approval
    # has no branch for it) -- admit_proposal already enqueued EXECUTE_ACTION.
    processed = await worker.drain_due_jobs(FixtureCoordinator(), raise_on_error=True)
    assert processed >= 1

    async with session_scope() as session:
        snapshot = (
            await session.execute(select(ResearchSnapshotModel).where(ResearchSnapshotModel.case_id == case_id))
        ).scalars().first()
        candidates = (
            await session.execute(select(ContractorCandidateModel).where(ContractorCandidateModel.case_id == case_id))
        ).scalars().all()

    assert snapshot is not None
    assert snapshot.provenance == "FIXTURE", "must be clearly labelled FIXTURE, never passed off as LIVE"
    assert candidates == []
    assert snapshot.results == []
