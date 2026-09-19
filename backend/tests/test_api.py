"""Phase 4: the HTTP API layer, exercised through real ASGI requests (not
direct Python calls) against app.main.app. The background worker loop is
not started here (that needs FastAPI's lifespan, which is exercised
manually in a smoke check, not per-test) -- tests drive jobs explicitly
with worker.drain_due_jobs, exactly as the real background loop would.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest
from httpx import ASGITransport, AsyncClient

from sqlalchemy import select

import app.main as main_module
from app.config import get_settings
from app.db import session_scope
from app.models import MockReservationModel, RepairCaseModel
from app.orchestration import dispatcher, worker

from tests.test_phase2_reliability import _drive_to_blocked_repair
from tests.test_hero_path import _approve_latest_awaiting, _seed_reference_data, uid

AUTH = ("operator", "repairflow-demo")


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=main_module.app), base_url="http://test")


@pytest.mark.asyncio
async def test_healthz_requires_no_auth(app_db):
    async with await _client() as client:
        r = await client.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_api_requires_operator_auth(app_db):
    # Independent of whatever OPERATOR_AUTH_ENABLED a developer's local .env
    # happens to have (it's commonly disabled for local demo convenience) --
    # this test asserts the ENABLED behavior specifically.
    os.environ["OPERATOR_AUTH_ENABLED"] = "true"
    get_settings.cache_clear()
    try:
        async with await _client() as client:
            r = await client.get("/api/v1/cases")
            assert r.status_code == 401
            r = await client.get("/api/v1/cases", auth=("operator", "wrong-password"))
            assert r.status_code == 401
            r = await client.get("/api/v1/cases", auth=AUTH)
            assert r.status_code == 200
    finally:
        os.environ.pop("OPERATOR_AUTH_ENABLED", None)
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_intake_approve_and_progress_through_http(app_db):
    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    coordinator = dispatcher.FixtureCoordinator()

    async def triage(snapshot, trigger_event_id):
        from app.schemas import ActionProposal, ApplyTriage, RiskAssessment, Trade

        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="Safe routine roof ingress.", evidence_refs=[],
            action=ApplyTriage(
                risk=RiskAssessment(urgency="ROUTINE", gas="NO", fire="NO", water_near_electrics="NO", structural_danger="NO", uncontrolled_flood="NO", vulnerability_concern="NO"),
                issue_description="Water ingress.", suggested_trade=Trade.ROOFING, scope="Repair roof ingress.",
            ),
        )

    coordinator.queue(triage)

    async with await _client() as client:
        r = await client.post(
            "/api/v1/demo/intake",
            json={
                "property_id": property_id, "tenant_id": tenant_id,
                "description": "Water ingress near the roofline.", "location": "Rear bedroom ceiling", "source_text": "src",
            },
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        case_id = r.json()["case_id"]

        await worker.drain_due_jobs(coordinator, raise_on_error=True)

        r = await client.get(f"/api/v1/cases/{case_id}", auth=AUTH)
        assert r.status_code == 200
        snapshot = r.json()["snapshot"]
        assert snapshot["case"]["status"] == "ACTIVE"
        assert any(w["kind"] == "REPAIR" and w["status"] == "READY" for w in snapshot["work_orders"])

        # polling with the known version returns 304 and no body
        r = await client.get(f"/api/v1/cases/{case_id}", params={"known_version": snapshot["case"]["version"]}, auth=AUTH)
        assert r.status_code == 304

        # events endpoint reflects the same history
        r = await client.get(f"/api/v1/cases/{case_id}/events", auth=AUTH)
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 2  # CASE_CREATED, WORK_ORDER_CREATED


@pytest.mark.asyncio
async def test_approval_round_trip_through_http(app_db):
    """The full admit -> AWAITING_APPROVAL -> approve via HTTP -> executed
    loop, proving the exposed payload_hash actually round-trips correctly."""
    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    coordinator = dispatcher.FixtureCoordinator()

    async with await _client() as client:
        r = await client.post(
            "/api/v1/demo/intake",
            json={
                "property_id": property_id, "tenant_id": tenant_id,
                "description": "Gas smell near the boiler.", "location": "Airing cupboard", "source_text": "src",
                "safety_answers": {"gas": "UNKNOWN"},
            },
            auth=AUTH,
        )
        case_id = r.json()["case_id"]

        # No live/fixture coordinator decision has been queued for this
        # case's worker-driven COORDINATE job; drive it directly instead so
        # this test exercises HTTP approval, not model wiring.
        async def triage(snapshot, trigger_event_id):
            from app.schemas import ActionProposal, ApplyTriage, RiskAssessment, Trade

            return ActionProposal(
                case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
                decision_summary="Unknown safety facts; still proposing triage but it must require approval.",
                evidence_refs=[],
                action=ApplyTriage(
                    risk=RiskAssessment(urgency="ROUTINE"),  # all defaults: UNKNOWN
                    issue_description="Gas smell near the boiler.", suggested_trade=Trade.OTHER, scope="Investigate.",
                ),
            )

        coordinator.queue(triage)
        await worker.drain_due_jobs(coordinator, raise_on_error=True)

        r = await client.get(f"/api/v1/cases/{case_id}", auth=AUTH)
        pending = r.json()["snapshot"]["pending_actions"]
        assert len(pending) == 1
        action = pending[0]
        assert action["state"] == "AWAITING_APPROVAL"
        assert "payload_hash" in action and action["payload_hash"]

        approval_body = {
            "action_id": action["id"], "expected_case_version": r.json()["snapshot"]["case"]["version"],
            "approve": True, "authorized_limit_pence": None, "reason": "reviewed, safe to proceed",
            "action_payload_hash": action["payload_hash"],
        }
        r = await client.post(f"/api/v1/actions/{action['id']}/approval", json=approval_body, auth=AUTH)
        assert r.status_code == 202, r.text

        await worker.drain_due_jobs(coordinator, raise_on_error=True)

        r = await client.get(f"/api/v1/cases/{case_id}", auth=AUTH)
        snapshot = r.json()["snapshot"]
        assert any(w["status"] == "READY" for w in snapshot["work_orders"])


@pytest.mark.asyncio
async def test_demo_reset_clears_case_and_releases_mock_reservation(app_db):
    """demo_reset must not violate FKs (dependencies -> reports -> appointments
    -> action_records is the load-bearing chain) and must release, not orphan,
    the MockReservationModel/MockSlotModel rows a booked SCHEDULE_VISIT
    created (those tables have no case_id column, so they're cleaned up
    through work_order_id instead)."""
    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    case_id, report_id, _coordinator = await _drive_to_blocked_repair(uid(), property_id, tenant_id, roofer_id, scaffolder_id)

    # approve + execute the pending scaffold booking so a real
    # MockReservationModel row exists to be cleaned up
    await _approve_latest_awaiting(case_id, "Approved for reset test.", limit_pence=30_000)
    await worker.drain_due_jobs(dispatcher.FixtureCoordinator(), raise_on_error=True)

    async with session_scope() as session:
        reservations_before = (await session.execute(select(MockReservationModel))).scalars().all()
    assert len(reservations_before) >= 1, "expected a booked scaffold slot to produce a reservation"

    async with await _client() as client:
        r = await client.post("/api/v1/demo/reset", params={"confirm_reset": "true"}, auth=AUTH)
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["cleared"] is True
        assert body["case_count"] >= 1

    async with session_scope() as session:
        remaining_case = await session.get(RepairCaseModel, case_id)
        reservations_after = (await session.execute(select(MockReservationModel))).scalars().all()
    assert remaining_case is None
    assert reservations_after == []
