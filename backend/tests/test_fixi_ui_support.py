"""Focused tests for the backend support added for the Fixi UI integration
phase: case_number allocation, the enriched CaseSnapshot/CaseListItem
fields, case-list filters, the dashboard KPI endpoint, property history and
the appointment-cancel "reschedule" flow (cancel -> COORDINATE re-entry ->
a fresh ScheduleVisit proposal, never an in-place status edit).
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import app.main as main_module
from app.db import session_scope
from app.domain import services
from app.domain.services import ActorContext
from app.models import (
    CommunicationModel,
    JobModel,
    RepairCaseModel,
    WorkOrderModel,
)
from app.orchestration import worker
from app.orchestration.dispatcher import FixtureCoordinator
from app.schemas import (
    ActionProposal,
    ApplyTriage,
    CaseStatus,
    IntakeSubmission,
    ObservationSubmission,
    RequestConfirmation,
    ResolveCase,
    RiskAssessment,
    Trade,
)

from tests.test_hero_path import (
    _accept_report_builder,
    _appointment_for,
    _broad_tenant_window,
    _inject_report,
    _schedule_builder,
    _seed_reference_data,
    _work_order,
    uid,
)

AUTH = ("operator", "repairflow-demo")


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=main_module.app), base_url="http://test")


async def _intake(property_id: str, tenant_id: str, description: str, location: str = "Rear bedroom ceiling") -> str:
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
                description=description, location=location, source_text=description,
            ),
            actor=ActorContext("VOICE_TOOL", comm_id, comm_id),
        )
    return case_id


def _triage_builder(description: str):
    async def triage(snapshot, trigger_event_id) -> ActionProposal:
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="Safe, routine roof ingress; dispatch a roofer.", evidence_refs=[],
            action=ApplyTriage(
                risk=RiskAssessment(urgency="ROUTINE", gas="NO", fire="NO", water_near_electrics="NO", structural_danger="NO", uncontrolled_flood="NO", vulnerability_concern="NO"),
                issue_description=description, suggested_trade=Trade.ROOFING, scope="Inspect and repair roof ingress.",
            ),
        )

    return triage


async def _drive_case_to_scheduled(property_id: str, tenant_id: str, roofer_id: str, description: str = "Water ingress near the roofline."):
    """Intake -> triage -> scheduled REPAIR visit. No approvals needed
    (ordinary REPAIR quote is within ORDINARY_AUTHORITY_LIMIT_PENCE)."""
    case_id = await _intake(property_id, tenant_id, description)
    await _broad_tenant_window(case_id, tenant_id)

    coordinator = FixtureCoordinator()
    coordinator.queue(_triage_builder(description))
    coordinator.queue(_schedule_builder(Trade.ROOFING, roofer_id, "REPAIR"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    repair_wo = await _work_order(case_id, "REPAIR")
    appointment = await _appointment_for(repair_wo.id, attempt_number=1)
    return case_id, coordinator, repair_wo, appointment


async def _request_confirmation_builder(snapshot, trigger_event_id) -> ActionProposal:
    return ActionProposal(
        case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
        decision_summary="All work complete; ask the tenant to confirm resolution.", evidence_refs=[],
        action=RequestConfirmation(issue_id=snapshot.issue.id, questions=["Is the leak fully resolved?"]),
    )


async def _resolve_builder(snapshot, trigger_event_id) -> ActionProposal:
    confirmation_event = next(e for e in snapshot.recent_events if e.type.value == "TENANT_CONFIRMATION_RECEIVED")
    return ActionProposal(
        case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
        decision_summary="Tenant confirmed resolution; resolve the case.", evidence_refs=[],
        action=ResolveCase(issue_id=snapshot.issue.id, confirmation_event_id=confirmation_event.id),
    )


async def _drive_case_to_resolved(property_id: str, tenant_id: str, roofer_id: str, description: str = "Water ingress near the roofline."):
    """Full simple (no-scaffold) hero-lite path through to CASE_RESOLVED."""
    case_id, coordinator, repair_wo, appointment = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id, description)

    await _inject_report(
        work_order_id=repair_wo.id, appointment_id=appointment.id, contractor_id=roofer_id,
        text="Roof repair complete, tiles resealed, no further leaks observed.",
    )
    coordinator.queue(_accept_report_builder("REPAIR"))
    coordinator.queue(_request_confirmation_builder)
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    async with session_scope() as session:
        confirmation_comm = (
            await session.execute(select(CommunicationModel).where(CommunicationModel.case_id == case_id, CommunicationModel.purpose == "FOLLOW_UP"))
        ).scalars().first()
        confirmation_comm_id = confirmation_comm.id

    async with session_scope() as session:
        await services.record_observations(
            session, case_id=case_id, communication_id=confirmation_comm_id,
            submission=ObservationSubmission(communication_id=uuid.UUID(confirmation_comm_id), tenant_confirms_resolved=True, source_text="Yes, all sorted, thanks!"),
            actor=ActorContext("VOICE_TOOL", confirmation_comm_id, uid()),
        )

    coordinator.queue(_resolve_builder)
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        assert case.status == "RESOLVED"
    return case_id


# --------------------------------------------------------------------------
# A. case_number
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_number_assigned_sequentially(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    first = await _intake(property_id, tenant_id, "First issue")
    second = await _intake(property_id, tenant_id, "Second issue")

    async with session_scope() as session:
        first_case = await session.get(RepairCaseModel, first)
        second_case = await session.get(RepairCaseModel, second)

    assert first_case.case_number == 1
    assert second_case.case_number == 2


@pytest.mark.asyncio
async def test_case_number_unique_constraint_enforced(app_db):
    property_id, tenant_id, _, _ = await _seed_reference_data()
    case_id = await _intake(property_id, tenant_id, "Some issue")
    async with session_scope() as session:
        existing = await session.get(RepairCaseModel, case_id)
        dup = RepairCaseModel(
            id=uid(), case_number=existing.case_number, property_id=property_id, tenant_id=tenant_id,
            status=CaseStatus.ACTIVE, version=1, title="Duplicate case_number", risk={},
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            await session.flush()
        # session_scope()'s own exit will try to commit; a flush failure
        # leaves the session in a "must rollback first" state, so clear it
        # here rather than letting that commit raise a different error.
        await session.rollback()


@pytest.mark.asyncio
async def test_case_number_concurrent_creates_stay_unique(app_db):
    """Real concurrency is possible even in this one-process app (two HTTP
    requests interleave on the event loop). MAX(case_number)+1's TOCTOU
    window means not every concurrent create is guaranteed to succeed, but
    the UNIQUE constraint guarantees no two SUCCESSFUL creates ever share a
    number -- assert that, not that all N succeed (see
    services.next_case_number's docstring)."""
    property_id, tenant_id, _, _ = await _seed_reference_data()

    async def create_one(i: int) -> str | None:
        try:
            return await _intake(property_id, tenant_id, f"Concurrent issue {i}")
        except Exception:
            return None

    results = await asyncio.gather(*[create_one(i) for i in range(5)])
    case_ids = [c for c in results if c is not None]
    assert len(case_ids) >= 1

    async with session_scope() as session:
        numbers = (
            await session.execute(select(RepairCaseModel.case_number).where(RepairCaseModel.id.in_(case_ids)))
        ).scalars().all()
    assert len(numbers) == len(set(numbers)), "two successful creates ended up with the same case_number"


# --------------------------------------------------------------------------
# B. CaseSnapshot enrichment
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_snapshot_includes_property_and_tenant_with_nullable_email(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    case_id, _coordinator, _wo, _appt = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id)

    async with await _client() as client:
        r = await client.get(f"/api/v1/cases/{case_id}", auth=AUTH)
        assert r.status_code == 200
        snapshot = r.json()["snapshot"]

    assert snapshot["property"]["id"] == property_id
    assert snapshot["property"]["address_line"] == "1 Test St"
    assert snapshot["tenant"]["id"] == tenant_id
    assert snapshot["tenant"]["display_name"] == "Jordan Hale"
    assert snapshot["tenant"]["email"] is None
    assert "case_number" in snapshot["case"]


@pytest.mark.asyncio
async def test_case_snapshot_assigned_contractor_and_next_appointment(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    case_id, _coordinator, repair_wo, appointment = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id)

    async with await _client() as client:
        r = await client.get(f"/api/v1/cases/{case_id}", auth=AUTH)
        snapshot = r.json()["snapshot"]

    assert snapshot["assigned_contractor"] is not None
    assert snapshot["assigned_contractor"]["id"] == roofer_id
    assert snapshot["assigned_contractor"]["trade"] == "ROOFING"
    # Seed contact_reference is "mock:apex-roofing" -- not phone-shaped, so
    # phone must stay null rather than being fabricated from it.
    assert snapshot["assigned_contractor"]["phone"] is None
    assert snapshot["assigned_contractor"]["provenance"] == "SIMULATED"

    assert snapshot["next_appointment"] is not None
    assert snapshot["next_appointment"]["id"] == appointment.id


@pytest.mark.asyncio
async def test_assigned_contractor_tie_break_prefers_repair_and_list_matches_detail(app_db):
    """`_pick_assigned_work_order`'s whole reason to exist is a case with
    more than one contractor at once (hero path: roofer + scaffolder). Get
    there via test_phase2_reliability's shared blocked-repair setup, then
    approve+execute the scaffold booking too, so REPAIR (BLOCKED, roofer)
    and SCAFFOLD_INSTALL (SCHEDULED, scaffolder) both carry a contractor_id
    -- the real tie-break case, not the trivial single-candidate one every
    other test here exercises. Also proves the list and detail endpoints
    agree, which is the entire point of sharing one selection function.
    """
    from tests.test_hero_path import _approve_latest_awaiting
    from tests.test_phase2_reliability import _drive_to_blocked_repair

    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    case_id, _report_id, coordinator = await _drive_to_blocked_repair(uid(), property_id, tenant_id, roofer_id, scaffolder_id)

    await _approve_latest_awaiting(case_id, "Approved scaffold installation booking.", limit_pence=30_000)
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    repair_wo = await _work_order(case_id, "REPAIR")
    scaffold_wo = await _work_order(case_id, "SCAFFOLD_INSTALL")
    assert repair_wo.status == "BLOCKED" and repair_wo.contractor_id == roofer_id
    assert scaffold_wo.status == "SCHEDULED" and scaffold_wo.contractor_id == scaffolder_id

    async with await _client() as client:
        detail = (await client.get(f"/api/v1/cases/{case_id}", auth=AUTH)).json()["snapshot"]
        list_items = {i["id"]: i for i in (await client.get("/api/v1/cases", auth=AUTH)).json()["items"]}

    assert detail["assigned_contractor"]["id"] == roofer_id
    assert detail["assigned_contractor"]["trade"] == "ROOFING"
    assert list_items[case_id]["assigned_contractor_name"] == "Apex Roofing"


@pytest.mark.asyncio
async def test_case_snapshot_no_contractor_or_appointment_before_scheduling(app_db):
    property_id, tenant_id, _, _ = await _seed_reference_data()
    case_id = await _intake(property_id, tenant_id, "Just reported, nothing scheduled yet")

    async with await _client() as client:
        r = await client.get(f"/api/v1/cases/{case_id}", auth=AUTH)
        snapshot = r.json()["snapshot"]

    assert snapshot["assigned_contractor"] is None
    assert snapshot["next_appointment"] is None


# --------------------------------------------------------------------------
# C. Case list enrichment and filters
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_list_item_fields_and_filters(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    scheduled_case_id, _c, _wo, _appt = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id, "Leaky roof over kitchen")
    plain_case_id = await _intake(property_id, tenant_id, "Broken window latch")

    async with await _client() as client:
        r = await client.get("/api/v1/cases", auth=AUTH)
        assert r.status_code == 200
        items = {i["id"]: i for i in r.json()["items"]}
        assert scheduled_case_id in items and plain_case_id in items
        scheduled_item = items[scheduled_case_id]
        assert scheduled_item["case_number"] > 0
        assert scheduled_item["property_address"] == "1 Test St"
        assert scheduled_item["assigned_contractor_name"] == "Apex Roofing"
        assert items[plain_case_id]["assigned_contractor_name"] is None

        # status filter
        r = await client.get("/api/v1/cases", params={"status": "ACTIVE"}, auth=AUTH)
        assert all(i["status"] == "ACTIVE" for i in r.json()["items"])

        # property_id filter
        r = await client.get("/api/v1/cases", params={"property_id": property_id}, auth=AUTH)
        assert all(i["id"] in items for i in r.json()["items"])

        # q filter (title search)
        r = await client.get("/api/v1/cases", params={"q": "window latch"}, auth=AUTH)
        result_ids = {i["id"] for i in r.json()["items"]}
        assert plain_case_id in result_ids
        assert scheduled_case_id not in result_ids


# --------------------------------------------------------------------------
# D. KPI/dashboard endpoint
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_metrics_reflect_real_statuses(app_db):
    # Drive the resolved case to completion first, while it's the only case
    # in the system -- drain_due_jobs claims the globally-earliest-due job
    # regardless of case, so an *undrained* COORDINATE job from a second
    # case created earlier would steal a queued FixtureCoordinator decision
    # meant for this one. Create the still-open case last instead.
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    resolved_case_id = await _drive_case_to_resolved(property_id, tenant_id, roofer_id, "Resolved case")
    active_case_id = await _intake(property_id, tenant_id, "Active case")

    async with await _client() as client:
        r = await client.get("/api/v1/metrics/dashboard", auth=AUTH)
        assert r.status_code == 200
        body = r.json()

    assert body["active"] >= 1
    assert body["resolved"] >= 1
    assert body["resolved_this_week"] >= 1
    assert body["total"] == body["active"] + body["awaiting_confirmation"] + body["resolved"] + body["escalated"] + body["cancelled"]

    async with session_scope() as session:
        active_case = await session.get(RepairCaseModel, active_case_id)
        resolved_case = await session.get(RepairCaseModel, resolved_case_id)
    assert active_case.status == "ACTIVE"
    assert resolved_case.status == "RESOLVED"


# --------------------------------------------------------------------------
# F. Property history
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_property_history_outcome_grounded_or_null(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    resolved_case_id = await _drive_case_to_resolved(property_id, tenant_id, roofer_id, "Resolved case for history")
    active_case_id = await _intake(property_id, tenant_id, "Still open case for history")

    async with await _client() as client:
        r = await client.get(f"/api/v1/properties/{property_id}/history", auth=AUTH)
        assert r.status_code == 200
        body = r.json()

    assert body["property_id"] == property_id
    by_case = {item["case_id"]: item for item in body["items"]}
    assert resolved_case_id in by_case and active_case_id in by_case

    resolved_item = by_case[resolved_case_id]
    assert resolved_item["status"] == "RESOLVED"
    assert resolved_item["resolved_at"] is not None
    assert resolved_item["outcome"] == "Roof repair complete, tiles resealed, no further leaks observed."

    active_item = by_case[active_case_id]
    assert active_item["status"] == "ACTIVE"
    assert active_item["resolved_at"] is None
    assert active_item["outcome"] is None


@pytest.mark.asyncio
async def test_property_history_unknown_property_404s(app_db):
    async with await _client() as client:
        r = await client.get(f"/api/v1/properties/{uid()}/history", auth=AUTH)
        assert r.status_code == 404


# --------------------------------------------------------------------------
# E. Timeline display fields
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_events_have_display_fields(app_db):
    property_id, tenant_id, _, _ = await _seed_reference_data()
    case_id = await _intake(property_id, tenant_id, "Event display test")

    async with await _client() as client:
        r = await client.get(f"/api/v1/cases/{case_id}/events", auth=AUTH)
        assert r.status_code == 200
        items = r.json()["items"]

    assert items, "expected at least CASE_CREATED"
    created = next(i for i in items if i["type"] == "CASE_CREATED")
    assert created["display_title"] == "Case opened"
    assert created["display_description"]
    for item in items:
        assert item["display_title"]
        assert item["display_description"]


# --------------------------------------------------------------------------
# 6. Reschedule flow: cancel -> work order back to READY -> COORDINATE
#    re-entry -> fresh ScheduleVisit proposal, all through the normal
#    coordinator/policy/approval path.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_appointment_reopens_work_order_and_wakes_coordinator(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    case_id, coordinator, repair_wo, appointment = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id)

    async with session_scope() as session:
        case_before = await services.load_case(session, case_id)
    version_before = case_before.version

    async with await _client() as client:
        r = await client.post(
            f"/api/v1/appointments/{appointment.id}/cancel",
            json={"appointment_id": appointment.id, "reason": "Tenant asked to move the visit."}, auth=AUTH,
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["outcome"]["status"] == "CANCELLED"
        assert body["case_version"] == version_before + 1

    from app.models import AppointmentModel

    async with session_scope() as session:
        appt_after = await session.get(AppointmentModel, appointment.id)
        wo_after = await session.get(WorkOrderModel, repair_wo.id)
        case_after = await services.load_case(session, case_id)
        cancelled_events = (
            await session.execute(
                select(services.CaseEventModel).where(
                    services.CaseEventModel.case_id == case_id, services.CaseEventModel.type == "APPOINTMENT_CANCELLED",
                )
            )
        ).scalars().all()
        coordinate_jobs = (
            await session.execute(select(JobModel).where(JobModel.case_id == case_id, JobModel.kind == "COORDINATE"))
        ).scalars().all()

    assert appt_after.status == "CANCELLED"
    assert wo_after.status == "READY", "cancelling the only appointment should return the work order to READY"
    assert case_after.version == version_before + 1
    assert len(cancelled_events) == 1
    assert any(j.status == "DONE" for j in coordinate_jobs), "cancellation should have enqueued (and, once drained, run) a COORDINATE job"

    # The coordinator can now propose a fresh visit for the READY work
    # order -- this is the entire "reschedule" mechanism, no dedicated
    # reschedule endpoint.
    coordinator.queue(_schedule_builder(Trade.ROOFING, roofer_id, "REPAIR"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    repair_wo_rebooked = await _work_order(case_id, "REPAIR")
    assert repair_wo_rebooked.status == "SCHEDULED"

    async with session_scope() as session:
        appts = (
            await session.execute(select(AppointmentModel).where(AppointmentModel.work_order_id == repair_wo.id))
        ).scalars().all()
    assert len(appts) == 2, "expected the cancelled attempt plus a fresh rebooked one"
    assert {a.status for a in appts} == {"CANCELLED", "CONFIRMED"}


@pytest.mark.asyncio
async def test_cancel_appointment_idempotent_on_already_cancelled(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    case_id, _coordinator, _wo, appointment = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id)

    async with await _client() as client:
        r1 = await client.post(
            f"/api/v1/appointments/{appointment.id}/cancel",
            json={"appointment_id": appointment.id, "reason": "first cancel"}, auth=AUTH,
        )
        assert r1.status_code == 202
        r2 = await client.post(
            f"/api/v1/appointments/{appointment.id}/cancel",
            json={"appointment_id": appointment.id, "reason": "second cancel"}, auth=AUTH,
        )
        assert r2.status_code == 202
        assert r2.json()["outcome"]["status"] == "CANCELLED"
        # Second call is a no-op: no additional version bump.
        assert r2.json()["case_version"] == r1.json()["case_version"]


@pytest.mark.asyncio
async def test_seed_is_idempotent_per_row(app_db):
    """app/seed.py's seed() runs on every backend boot (main.py), so a
    regression here is a crash-on-startup, not just a bad fixture. Runs it
    twice against an isolated DB: the second run must insert nothing and
    must not raise (no per-row IntegrityError from re-adding an existing
    property/tenant/contractor)."""
    from app import seed as seed_module
    from app.models import ContractorModel, PropertyModel, TenantModel

    await seed_module.seed()

    async with session_scope() as session:
        assert len((await session.execute(select(PropertyModel))).scalars().all()) == len(
            seed_module.PROPERTIES
        )
        assert len((await session.execute(select(TenantModel))).scalars().all()) == len(
            seed_module.TENANTS
        )
        assert len((await session.execute(select(ContractorModel))).scalars().all()) == len(
            seed_module.CONTRACTORS
        )

    await seed_module.seed()  # must not raise, and must add nothing further

    async with session_scope() as session:
        assert len((await session.execute(select(PropertyModel))).scalars().all()) == len(
            seed_module.PROPERTIES
        )
        assert len((await session.execute(select(TenantModel))).scalars().all()) == len(
            seed_module.TENANTS
        )
        assert len((await session.execute(select(ContractorModel))).scalars().all()) == len(
            seed_module.CONTRACTORS
        )
