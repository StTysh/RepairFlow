"""Focused tests for the backend support added for the Fixi UI integration
phase: case_number allocation, the enriched CaseSnapshot/CaseListItem
fields, case-list filters, the dashboard KPI endpoint, property history and
the appointment-cancel "reschedule" flow (cancel -> COORDINATE re-entry ->
a fresh ScheduleVisit proposal, never an in-place status edit).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

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
        properties = (await session.execute(select(PropertyModel))).scalars().all()
        assert len(properties) == len(seed_module.PROPERTIES)
        assert len((await session.execute(select(TenantModel))).scalars().all()) == len(
            seed_module.TENANTS
        )
        assert len((await session.execute(select(ContractorModel))).scalars().all()) == len(
            seed_module.CONTRACTORS
        )
        # Every seeded property gets a backfilled build_year on the first run.
        build_years_after_first_run = {p.id: p.build_year for p in properties}
        assert all(v is not None for v in build_years_after_first_run.values())

    await seed_module.seed()  # must not raise, and must add nothing further

    async with session_scope() as session:
        properties = (await session.execute(select(PropertyModel))).scalars().all()
        assert len(properties) == len(seed_module.PROPERTIES)
        assert len((await session.execute(select(TenantModel))).scalars().all()) == len(
            seed_module.TENANTS
        )
        assert len((await session.execute(select(ContractorModel))).scalars().all()) == len(
            seed_module.CONTRACTORS
        )
        # The backfill pass must not overwrite build_year on a second run.
        assert {p.id: p.build_year for p in properties} == build_years_after_first_run


# --------------------------------------------------------------------------
# G. Property history enrichment (contractor_name / quoted_pence / trade)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_property_history_enriched_fields(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    scheduled_case_id, _c, _wo, _appt = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id, "Enriched history test")
    plain_case_id = await _intake(property_id, tenant_id, "Just reported, no work order yet")

    async with await _client() as client:
        r = await client.get(f"/api/v1/properties/{property_id}/history", auth=AUTH)
        assert r.status_code == 200
        by_case = {item["case_id"]: item for item in r.json()["items"]}

    scheduled_item = by_case[scheduled_case_id]
    assert scheduled_item["contractor_name"] == "Apex Roofing"
    assert scheduled_item["quoted_pence"] == 10_000
    assert scheduled_item["trade"] == "ROOFING"

    plain_item = by_case[plain_case_id]
    assert plain_item["contractor_name"] is None
    assert plain_item["quoted_pence"] is None
    assert plain_item["trade"] is None


@pytest.mark.asyncio
async def test_property_history_and_stats_exclude_cancelled_work_orders(app_db):
    """A CANCELLED work order's quote is money that will never be spent, and
    its trade isn't what the case is actually "about" any more -- both
    services._pick_primary_trade and the quoted_pence/quoted_by_trade sums
    must exclude it. No domain service currently cancels a work order
    in-place, so this sets WorkOrderModel.status directly to exercise the
    query-level exclusion in isolation."""
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    case_id, _c, repair_wo, _appt = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id, "Cancelled work order test")

    async with session_scope() as session:
        wo = await session.get(WorkOrderModel, repair_wo.id)
        issue_id = wo.issue_id
        wo.status = "CANCELLED"
        session.add(
            WorkOrderModel(
                id=uid(), case_id=case_id, issue_id=issue_id, kind="SCAFFOLD_INSTALL", trade="SCAFFOLDING",
                scope="Erect scaffold.", status="READY", required_for_resolution=True, quote_pence=30_000,
            )
        )

    async with await _client() as client:
        history = (await client.get(f"/api/v1/properties/{property_id}/history", auth=AUTH)).json()
        stats = (await client.get(f"/api/v1/properties/{property_id}/stats", auth=AUTH)).json()

    item = next(i for i in history["items"] if i["case_id"] == case_id)
    assert item["trade"] == "SCAFFOLDING"
    assert item["quoted_pence"] == 30_000  # cancelled REPAIR's 10_000 excluded

    by_trade = {row["trade"]: row for row in stats["quoted_by_trade"]}
    assert by_trade.keys() == {"SCAFFOLDING"}
    assert by_trade["SCAFFOLDING"]["quoted_pence"] == 30_000


# --------------------------------------------------------------------------
# H. Property build_year (honest-or-null; seeded properties now carry a real
# fictional value -- see app/seed.py PROPERTIES)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_property_build_year_present_for_seeded_properties(app_db):
    """Every seeded demo property is a fictional persona (fake address, fake
    tenant), so a plausible fictional build_year on it is honest seed data,
    not a fabricated fact about a real place -- see app/seed.py's PROPERTIES
    comment. This only covers the *seeded* properties; a property created
    ad hoc without one (e.g. _seed_reference_data() in test_hero_path.py)
    must still come back null -- see
    test_property_stats_breakdown_and_recurring_issues's
    `body["build_year"] is None` assertion elsewhere in this file."""
    from app import seed as seed_module

    await seed_module.seed()

    async with await _client() as client:
        r = await client.get("/api/v1/properties", auth=AUTH)
        assert r.status_code == 200
        body = r.json()

    rows = body["items"]
    assert rows, "expected the sample portfolio command to have created properties"
    assert all(p["build_year"] is not None for p in rows)
    assert all(1900 <= p["build_year"] <= 2026 for p in rows)


# --------------------------------------------------------------------------
# I. Property-level stats endpoint
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_property_stats_breakdown_and_recurring_issues(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()

    first_case, _c1, _wo1, _a1 = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id, "First roof leak")
    second_case, _c2, _wo2, _a2 = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id, "Second roof leak")

    async with await _client() as client:
        r = await client.get(f"/api/v1/properties/{property_id}/stats", auth=AUTH)
        assert r.status_code == 200
        body = r.json()

    assert body["property_id"] == property_id
    assert body["total_count"] == 2
    # Both cases are still ACTIVE (SCHEDULED work order, not yet
    # AWAITING_CONFIRMATION).
    assert body["active_count"] == 2
    assert body["build_year"] is None

    by_trade = {row["trade"]: row for row in body["quoted_by_trade"]}
    assert by_trade.keys() == {"ROOFING"}
    assert by_trade["ROOFING"]["quoted_pence"] == 20_000  # 10_000 REPAIR quote x 2 cases
    assert by_trade["ROOFING"]["percentage"] == 100.0

    assert len(body["quoted_by_year"]) == 1
    assert body["quoted_by_year"][0]["quoted_pence"] == 20_000

    recurring = {row["trade"]: row for row in body["recurring_issues"]}
    assert recurring.keys() == {"ROOFING"}
    assert recurring["ROOFING"]["occurrence_count"] == 2


@pytest.mark.asyncio
async def test_property_stats_unknown_property_404s(app_db):
    async with await _client() as client:
        r = await client.get(f"/api/v1/properties/{uid()}/stats", auth=AUTH)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_property_stats_empty_property_returns_honest_zeros(app_db):
    property_id, _tenant_id, _roofer_id, _ = await _seed_reference_data()

    async with await _client() as client:
        r = await client.get(f"/api/v1/properties/{property_id}/stats", auth=AUTH)
        assert r.status_code == 200
        body = r.json()

    assert body["total_count"] == 0
    assert body["active_count"] == 0
    assert body["quoted_by_trade"] == []
    assert body["quoted_by_year"] == []
    assert body["recurring_issues"] == []


# --------------------------------------------------------------------------
# J. Dashboard metrics: avg_resolution_hours + trend deltas
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_metrics_delta_pct_and_avg_resolution_hours(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    case_id = await _intake(property_id, tenant_id, "Backdated case for trend test")

    ten_days_ago = datetime.now(timezone.utc) - timedelta(days=10)
    async with session_scope() as session:
        case = await session.get(RepairCaseModel, case_id)
        case.created_at = ten_days_ago
        created_event = (
            await session.execute(
                select(services.CaseEventModel).where(
                    services.CaseEventModel.case_id == case_id, services.CaseEventModel.type == "CASE_CREATED",
                )
            )
        ).scalars().first()
        created_event.occurred_at = ten_days_ago

    await _broad_tenant_window(case_id, tenant_id)
    coordinator = FixtureCoordinator()
    coordinator.queue(_triage_builder("Backdated case for trend test"))
    coordinator.queue(_schedule_builder(Trade.ROOFING, roofer_id, "REPAIR"))
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    repair_wo = await _work_order(case_id, "REPAIR")
    appointment = await _appointment_for(repair_wo.id, attempt_number=1)
    await _inject_report(work_order_id=repair_wo.id, appointment_id=appointment.id, contractor_id=roofer_id, text="Roof repair complete.")
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
            submission=ObservationSubmission(communication_id=uuid.UUID(confirmation_comm_id), tenant_confirms_resolved=True, source_text="Yes, thanks!"),
            actor=ActorContext("VOICE_TOOL", confirmation_comm_id, uid()),
        )
    coordinator.queue(_resolve_builder)
    await worker.drain_due_jobs(coordinator, raise_on_error=True)

    async with await _client() as client:
        r = await client.get("/api/v1/metrics/dashboard", auth=AUTH)
        assert r.status_code == 200
        body = r.json()

    assert body["resolved"] == 1
    assert body["active"] == 0
    # Resolved "now", created ~10 days ago -> well over 100 hours.
    assert body["avg_resolution_hours"] is not None
    assert body["avg_resolution_hours"] > 100
    # 7 days ago this case's only event was CASE_CREATED -> reconstructed
    # ACTIVE; today it's RESOLVED (0 ACTIVE) -> a full swing to -100%.
    assert body["active_delta_pct"] == -100.0
    # No CaseEvent ever marks entry into AWAITING_CONFIRMATION, so this must
    # always come back None rather than a fabricated number (see
    # services.reconstructed_status_counts).
    assert body["awaiting_confirmation_delta_pct"] is None


@pytest.mark.asyncio
async def test_dashboard_metrics_no_resolutions_yields_null_avg(app_db):
    property_id, tenant_id, _, _ = await _seed_reference_data()
    await _intake(property_id, tenant_id, "Still open, nothing resolved")

    async with await _client() as client:
        r = await client.get("/api/v1/metrics/dashboard", auth=AUTH)
        assert r.status_code == 200
        body = r.json()

    assert body["resolved"] == 0
    assert body["avg_resolution_hours"] is None
    # No case existed 7 days ago either -> nothing to compare against.
    assert body["active_delta_pct"] is None
    assert body["escalated_delta_pct"] is None


# --------------------------------------------------------------------------
# K. Cross-case upcoming appointments
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upcoming_appointments_list(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    case_id, _coordinator, _wo, appointment = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id, "Upcoming visit test")

    async with await _client() as client:
        r = await client.get("/api/v1/appointments/upcoming", auth=AUTH)
        assert r.status_code == 200
        items = r.json()["items"]

    assert len(items) == 1
    item = items[0]
    assert item["appointment_id"] == appointment.id
    assert item["case_id"] == case_id
    assert item["trade"] == "ROOFING"
    assert item["property_address"] == "1 Test St"
    assert item["contractor_id"] == roofer_id
    assert item["contractor_name"] == "Apex Roofing"
    assert item["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_upcoming_appointments_excludes_past_start(app_db):
    """The single appointment in test_upcoming_appointments_list happens to
    be in the future either way, so that test alone can't prove the
    start_at >= now filter is doing anything. Backdate it directly and
    confirm it drops out."""
    from app.models import AppointmentModel

    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    _case_id, _coordinator, _wo, appointment = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id, "Past visit test")

    now = datetime.now(timezone.utc)
    async with session_scope() as session:
        appt = await session.get(AppointmentModel, appointment.id)
        appt.start_at = now - timedelta(days=2)
        appt.end_at = now - timedelta(days=1)

    async with await _client() as client:
        r = await client.get("/api/v1/appointments/upcoming", auth=AUTH)
        assert r.status_code == 200
        assert r.json()["items"] == []


@pytest.mark.asyncio
async def test_upcoming_appointments_excludes_cancelled(app_db):
    property_id, tenant_id, roofer_id, _ = await _seed_reference_data()
    _case_id, _coordinator, _wo, appointment = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id, "Cancelled visit test")

    async with await _client() as client:
        r = await client.post(
            f"/api/v1/appointments/{appointment.id}/cancel",
            json={"appointment_id": appointment.id, "reason": "no longer needed"}, auth=AUTH,
        )
        assert r.status_code == 202

        r = await client.get("/api/v1/appointments/upcoming", auth=AUTH)
        assert r.status_code == 200
        assert r.json()["items"] == []


# --------------------------------------------------------------------------
# L. Broader case search + contractor filter
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_list_search_widened_and_contractor_filter(app_db):
    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    scheduled_case_id, _c, _wo, _appt = await _drive_case_to_scheduled(property_id, tenant_id, roofer_id, "Leaky roof over kitchen")
    plain_case_id = await _intake(property_id, tenant_id, "Broken window latch")

    async with await _client() as client:
        # Property address match.
        r = await client.get("/api/v1/cases", params={"q": "Test St"}, auth=AUTH)
        result_ids = {i["id"] for i in r.json()["items"]}
        assert scheduled_case_id in result_ids and plain_case_id in result_ids

        # Tenant display name match.
        r = await client.get("/api/v1/cases", params={"q": "Jordan Hale"}, auth=AUTH)
        result_ids = {i["id"] for i in r.json()["items"]}
        assert scheduled_case_id in result_ids and plain_case_id in result_ids

        # contractor_id filter: only the case with an active roofer work order.
        r = await client.get("/api/v1/cases", params={"contractor_id": roofer_id}, auth=AUTH)
        result_ids = {i["id"] for i in r.json()["items"]}
        assert result_ids == {scheduled_case_id}

        r = await client.get("/api/v1/cases", params={"contractor_id": scaffolder_id}, auth=AUTH)
        assert r.json()["items"] == []


# --------------------------------------------------------------------------
# M. Read-only messages panel
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_messages_empty_then_ordered(app_db):
    from app.models import MessageModel

    property_id, tenant_id, _, _ = await _seed_reference_data()
    case_id = await _intake(property_id, tenant_id, "Message thread test")

    async with await _client() as client:
        r = await client.get(f"/api/v1/cases/{case_id}/messages", auth=AUTH)
        assert r.status_code == 200
        assert r.json() == {"case_id": case_id, "items": []}

    now = datetime.now(timezone.utc)
    async with session_scope() as session:
        session.add(
            MessageModel(
                id=uid(), case_id=case_id, sender_type="TENANT", sender_name="Jordan Hale",
                text="Hi, any update?", created_at=now - timedelta(hours=1),
            )
        )
        session.add(
            MessageModel(
                id=uid(), case_id=case_id, sender_type="OPERATOR", sender_name="Operator",
                text="On it, roofer booked for tomorrow.", created_at=now,
            )
        )

    async with await _client() as client:
        r = await client.get(f"/api/v1/cases/{case_id}/messages", auth=AUTH)
        assert r.status_code == 200
        items = r.json()["items"]

    assert [i["sender_type"] for i in items] == ["TENANT", "OPERATOR"]
    assert items[0]["text"] == "Hi, any update?"
    assert items[0]["photo_url"] is None
    assert items[1]["sender_name"] == "Operator"


@pytest.mark.asyncio
async def test_case_messages_unknown_case_404s(app_db):
    async with await _client() as client:
        r = await client.get(f"/api/v1/cases/{uid()}/messages", auth=AUTH)
        assert r.status_code == 404


# --------------------------------------------------------------------------
# N. Notifications feed
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notifications_awaiting_approval_and_escalation(app_db):
    from tests.test_hero_path import _approve_latest_awaiting
    from tests.test_phase2_reliability import _drive_to_blocked_repair

    property_id, tenant_id, roofer_id, scaffolder_id = await _seed_reference_data()
    blocked_case_id, _report_id, _coordinator = await _drive_to_blocked_repair(
        uid(), property_id, tenant_id, roofer_id, scaffolder_id
    )

    escalated_case_id = await _intake(property_id, tenant_id, "Gas smell reported")
    await _broad_tenant_window(escalated_case_id, tenant_id)

    async def hazard_triage(snapshot, trigger_event_id) -> ActionProposal:
        return ActionProposal(
            case_id=snapshot.case.id, expected_case_version=snapshot.snapshot_version, trigger_event_id=trigger_event_id,
            decision_summary="Possible gas hazard; escalate immediately.", evidence_refs=[],
            action=ApplyTriage(
                risk=RiskAssessment(
                    urgency="EMERGENCY", gas="YES", fire="NO", water_near_electrics="NO",
                    structural_danger="NO", uncontrolled_flood="NO", vulnerability_concern="NO",
                ),
                issue_description="Gas smell reported", suggested_trade=Trade.OTHER, scope="Investigate gas smell.",
            ),
        )

    hazard_coordinator = FixtureCoordinator()
    hazard_coordinator.queue(hazard_triage)
    await worker.drain_due_jobs(hazard_coordinator, raise_on_error=True)

    # A hazardous triage is itself gated behind operator approval (docs/19)
    # -- ApplyTriage lands as an AWAITING_APPROVAL action first; approving
    # it is what actually runs apply_triage and flips the case to
    # ESCALATED + fires CASE_ESCALATED.
    await _approve_latest_awaiting(escalated_case_id, "Reviewed; genuine gas hazard, escalate.", limit_pence=None)
    await worker.drain_due_jobs(hazard_coordinator, raise_on_error=True)

    async with session_scope() as session:
        escalated_case = await services.load_case(session, escalated_case_id)
        assert escalated_case.status == "ESCALATED"
        escalated_version = escalated_case.version

    async with await _client() as client:
        r = await client.get("/api/v1/notifications", auth=AUTH)
        assert r.status_code == 200
        body = r.json()

    by_kind: dict[str, list[dict]] = {}
    for item in body["items"]:
        by_kind.setdefault(item["kind"], []).append(item)

    assert {i["case_id"] for i in by_kind.get("AWAITING_APPROVAL", [])} >= {blocked_case_id}
    assert all(i["unread"] for i in by_kind["AWAITING_APPROVAL"])

    escalation_items = {i["case_id"]: i for i in by_kind.get("CASE_ESCALATED", [])}
    assert escalated_case_id in escalation_items
    assert escalation_items[escalated_case_id]["unread"] is True
    assert body["unread_count"] == sum(1 for i in body["items"] if i["unread"])

    # Once the case is resumed (no longer ESCALATED), the same historical
    # escalation event must flip to read rather than disappearing.
    async with await _client() as client:
        r = await client.post(
            f"/api/v1/cases/{escalated_case_id}/resume",
            json={
                "version": escalated_version, "reason": "Gas Safe engineer confirmed no leak.",
                "resolved_hold_evidence": "Gas Safe engineer report received.",
            },
            auth=AUTH,
        )
        assert r.status_code == 202

        r = await client.get("/api/v1/notifications", auth=AUTH)
        assert r.status_code == 200
        body = r.json()

    escalation_items = {i["case_id"]: i for i in body["items"] if i["kind"] == "CASE_ESCALATED"}
    assert escalation_items[escalated_case_id]["unread"] is False


@pytest.mark.asyncio
async def test_notifications_empty_when_nothing_pending(app_db):
    property_id, tenant_id, _, _ = await _seed_reference_data()
    await _intake(property_id, tenant_id, "Ordinary case, nothing pending")

    async with await _client() as client:
        r = await client.get("/api/v1/notifications", auth=AUTH)
        assert r.status_code == 200
        body = r.json()

    assert body["items"] == []
    assert body["unread_count"] == 0



@pytest.mark.asyncio
async def test_every_appended_event_type_is_declared_in_the_enum():
    """A missing EventType does not fail where it is written -- CaseEventModel
    stores a plain string -- it fails much later, when load_case_snapshot
    validates the case's own history and 500s the entire ticket page. Three
    event types had already drifted out of the enum before this test
    existed, so the drift is checked mechanically rather than by eye."""
    import re
    from pathlib import Path

    from app.schemas import EventType

    declared = {member.value for member in EventType}
    appended: set[str] = set()
    app_dir = Path(__file__).resolve().parent.parent / "app"
    for source in app_dir.rglob("*.py"):
        appended |= set(re.findall(r'event_type="([A-Z_]+)"', source.read_text(encoding="utf-8")))

    missing = sorted(appended - declared)
    assert not missing, f"event types appended but not declared in EventType: {missing}"


@pytest.mark.asyncio
async def test_added_column_is_backfilled_with_its_default(tmp_path):
    """`create_all` never alters an existing table, so a column added to a
    model after a database was created arrives NULL on every row already
    there -- and a SQLAlchemy `default=` runs at INSERT time, so it does
    not help them. For a NOT NULL column that is a crash waiting for the
    first read of an old row, which is exactly how it would have shipped:
    every test and every manual check so far ran against a database
    created fresh, where the migration path is a no-op.

    This builds the failure deliberately: a table created WITHOUT the new
    columns, a row inserted into it, then create_all(). The row must read
    back with the model's defaults, not NULL.
    """
    import os

    import sqlalchemy as sa

    import app.db as db_module
    from app.config import get_settings
    from app.models import MessageModel

    path = tmp_path / "legacy.db"
    legacy = sa.create_engine(f"sqlite:///{path}")
    with legacy.begin() as conn:
        # The pre-migration shape of `messages`, as it existed on disk.
        conn.exec_driver_sql(
            "CREATE TABLE messages ("
            " id VARCHAR(36) PRIMARY KEY, case_id VARCHAR(36), sender_type VARCHAR(40),"
            " sender_name VARCHAR(128), text TEXT, photo_url VARCHAR(512), created_at VARCHAR(32))"
        )
        conn.exec_driver_sql(
            "INSERT INTO messages (id, case_id, sender_type, sender_name, text, created_at)"
            " VALUES ('m1', 'c1', 'TENANT', 'Old Row', 'Predates the new columns',"
            " '2026-01-01T00:00:00+00:00')"
        )
    legacy.dispose()

    previous = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(path)
    get_settings.cache_clear()
    db_module._engine = None
    db_module._session_factory = None
    try:
        await db_module.create_all()
        async with db_module.session_scope() as session:
            row = await session.get(MessageModel, "m1")
            assert row is not None
            # Every NOT NULL column the model gained must have a value.
            assert row.channel is not None, "channel left NULL on a pre-existing row"
            assert row.delivery_state is not None, "delivery_state left NULL"
            assert row.attachments == [], "attachments left NULL rather than an empty list"
            # A genuinely nullable addition stays null -- backfilling it
            # would invent a fact about a row nobody has looked at.
            assert row.read_at is None
            assert row.archive_batch_id is None
    finally:
        await db_module.dispose_engine()
        if previous is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = previous
        get_settings.cache_clear()
        db_module._engine = None
        db_module._session_factory = None
