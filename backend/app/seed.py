"""Synthetic reference data for the hero demo: properties, tenants, approved
fictional roofers and a scaffolder. Does not create a case — the case is
created through intake (docs/04: "create case from browser voice or
labelled captured intake"), so the initial state never contains the
scaffold branch.

Seeding is idempotent per row (checked individually, not "bail if the demo
property exists") so this can be re-run safely against a database that
already has real, in-progress demo data on it -- adding a new property here
must not require wiping anything. Existing rows are left untouched; only
rows that don't yet exist are inserted.

Run with: python -m app.seed
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from app.db import create_all, session_scope
from app.models import (
    ActionRecordModel,
    AppointmentModel,
    ContractorModel,
    ContractorReportModel,
    DependencyModel,
    MessageModel,
    PropertyModel,
    RepairCaseModel,
    RepairIssueModel,
    TenantModel,
    WorkOrderModel,
)
from app.schemas import (
    ActionState,
    AppointmentStatus,
    CaseStatus,
    ConnectorType,
    ContractorApprovalStatus,
    DependencyStatus,
    InterpretationStatus,
    MessageSenderType,
    Provenance,
    RoofResponsibility,
    SourceType,
    Trade,
    VisitOutcome,
    WorkOrderKind,
    WorkOrderStatus,
)

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "repairflow.demo")


def _demo_id(label: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, label))


# --- Original hero-path fixtures --------------------------------------------
# Do not change these values: they're baked into already-recorded LIVE call
# evidence from real ElevenLabs testing. Only add alongside, never edit.
DEMO_PROPERTY_ID = _demo_id("property:14-elm-court")
DEMO_TENANT_ID = _demo_id("tenant:jordan-hale")
DEMO_ROOFER_ID = _demo_id("contractor:apex-roofing")
DEMO_ROOFER_2_ID = _demo_id("contractor:bristol-roof-and-gutter")
DEMO_ROOFER_3_ID = _demo_id("contractor:summit-heights-roofing")
DEMO_SCAFFOLDER_ID = _demo_id("contractor:steadfast-scaffold")
# Non-roofing trades, so a plumbing/electrical case can be booked against a
# real approved firm instead of being left unassigned.
DEMO_PLUMBER_ID = _demo_id("contractor:harbourside-plumbing")
DEMO_ELECTRICIAN_ID = _demo_id("contractor:clifton-electrical")

# --- Additional properties/tenants (portfolio breadth for the maintenance
# dashboard -- distinct addresses so tickets don't all land on one property).
DEMO_PROPERTY_2_ID = _demo_id("property:27-cathedral-walk")
DEMO_TENANT_2_ID = _demo_id("tenant:priya-desai")
DEMO_PROPERTY_3_ID = _demo_id("property:58-gloucester-road")
DEMO_TENANT_3_ID = _demo_id("tenant:tomasz-nowak")
DEMO_PROPERTY_4_ID = _demo_id("property:9-redcliffe-parade")
DEMO_TENANT_4_ID = _demo_id("tenant:aaliyah-bennett")


PROPERTIES: list[dict] = [
    dict(
        id=DEMO_PROPERTY_ID,
        address_line="14 Elm Court, Bristol",
        postcode="BS1 4ND",
        timezone="Europe/London",
        landlord_reference="LL-2201",
        roof_responsibility=RoofResponsibility.LANDLORD,
        access_notes="Terraced house; roof accessed from rear garden only.",
        # Fictional-but-plausible construction year for this demo persona
        # (CLAUDE.md's honesty boundary is about not touching a
        # LIVE-provenance case/communication, not about leaving fictional
        # property metadata null forever -- a build year on a fictional
        # address is exactly the kind of invented detail seed data exists
        # for). Applied via the update-if-null pass below for rows that
        # already exist from a prior seed run.
        build_year=1961,
    ),
    dict(
        id=DEMO_PROPERTY_2_ID,
        address_line="27 Cathedral Walk, Bristol",
        postcode="BS8 1JX",
        timezone="Europe/London",
        landlord_reference="LL-2202",
        roof_responsibility=RoofResponsibility.LANDLORD,
        access_notes="Flat 3B, top floor; roof access via communal stairwell, managing agent holds the key.",
        build_year=2005,
    ),
    dict(
        id=DEMO_PROPERTY_3_ID,
        address_line="58 Gloucester Road, Bristol",
        postcode="BS7 8BT",
        timezone="Europe/London",
        landlord_reference="LL-2203",
        roof_responsibility=RoofResponsibility.OTHER,
        access_notes="Mid-terrace; loft hatch access only, no external ladder point.",
        build_year=1978,
    ),
    dict(
        id=DEMO_PROPERTY_4_ID,
        address_line="9 Redcliffe Parade, Bristol",
        postcode="BS1 6SP",
        timezone="Europe/London",
        landlord_reference="LL-2204",
        roof_responsibility=RoofResponsibility.UNKNOWN,
        access_notes="Ground-floor flat; shared roof, access managed by the freeholder.",
        build_year=1967,
    ),
]

TENANTS: list[dict] = [
    dict(
        id=DEMO_TENANT_ID,
        property_id=DEMO_PROPERTY_ID,
        display_name="Jordan Hale",
        phone_e164="+441179460000",
        preferred_channel="VOICE",
        contact_allowed=True,
        accessibility_notes=None,
    ),
    dict(
        id=DEMO_TENANT_2_ID,
        property_id=DEMO_PROPERTY_2_ID,
        display_name="Priya Desai",
        phone_e164="+441179460011",
        preferred_channel="VOICE",
        contact_allowed=True,
        accessibility_notes=None,
    ),
    dict(
        id=DEMO_TENANT_3_ID,
        property_id=DEMO_PROPERTY_3_ID,
        display_name="Tomasz Nowak",
        phone_e164="+441179460022",
        preferred_channel="VOICE",
        contact_allowed=True,
        accessibility_notes=None,
    ),
    dict(
        id=DEMO_TENANT_4_ID,
        property_id=DEMO_PROPERTY_4_ID,
        display_name="Aaliyah Bennett",
        phone_e164="+441179460033",
        preferred_channel="VOICE",
        contact_allowed=True,
        accessibility_notes=None,
    ),
]

CONTRACTORS: list[dict] = [
    dict(
        id=DEMO_ROOFER_ID,
        display_name="Apex Roofing (fictional, SIMULATED)",
        trades=[Trade.ROOFING.value],
        service_postcodes=["BS1", "BS2", "BS3"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:apex-roofing",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[
            {"name": "Dave Okafor", "role": "Site lead, height-access certified"},
            {"name": "Priya Chandra", "role": "Roofer"},
        ],
    ),
    dict(
        id=DEMO_ROOFER_2_ID,
        display_name="Bristol Roof & Gutter (fictional, SIMULATED)",
        trades=[Trade.ROOFING.value],
        service_postcodes=["BS1", "BS2"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:bristol-roof-and-gutter",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Marcus Webb", "role": "Roofer"}],
    ),
    dict(
        id=DEMO_ROOFER_3_ID,
        display_name="Summit Heights Roofing (fictional, SIMULATED)",
        trades=[Trade.ROOFING.value],
        service_postcodes=["BS3", "BS4"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:summit-heights-roofing",
        verification_note="Seeded demo fixture; not a real company. Specialises in steep-pitch and chimney-adjacent work.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Aisha Rahman", "role": "Site lead, steep-pitch specialist"}],
    ),
    dict(
        id=DEMO_PLUMBER_ID,
        display_name="Harbourside Plumbing & Heating (fictional, SIMULATED)",
        trades=[Trade.PLUMBING.value],
        service_postcodes=["BS1", "BS2", "BS7", "BS8"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:harbourside-plumbing",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Gareth Lloyd", "role": "Gas-safe engineer"}],
    ),
    dict(
        id=DEMO_ELECTRICIAN_ID,
        display_name="Clifton Electrical Services (fictional, SIMULATED)",
        trades=[Trade.ELECTRICAL.value],
        service_postcodes=["BS1", "BS7", "BS8"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:clifton-electrical",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Nadia Fischer", "role": "Approved electrician"}],
    ),
    dict(
        id=DEMO_SCAFFOLDER_ID,
        display_name="Steadfast Scaffold Co (fictional, SIMULATED)",
        trades=[Trade.SCAFFOLDING.value],
        service_postcodes=["BS1", "BS2", "BS3"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:steadfast-scaffold",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[],
    ),
]


# --- Demo activity: closed history, one live dependency, upcoming visits ----
#
# Everything below is SIMULATED demo content for the fictional properties and
# tenants defined above -- it never touches DEMO_PROPERTY_ID's real recorded
# LIVE call evidence, and no row here is attached to a case that has a LIVE
# communication on it. Its purpose is to give the property-insight charts,
# the work/dependency graph, the upcoming-visits list and the message thread
# something real to read, instead of every panel rendering an empty state.
#
# Historical cases are RESOLVED and dated in past years so the "quoted by
# year" and "recurring issues" aggregations have something to group. Amounts
# are `quote_pence` (what a contractor quoted), never "spend" -- no field in
# this system represents money actually paid.

# Which seeded firm covers which trade. Only trades with an approved firm
# can be assigned one -- anything else stays unassigned rather than
# attaching a contractor who doesn't do that work.
_CONTRACTOR_BY_TRADE: dict[Trade, str] = {
    Trade.ROOFING: DEMO_ROOFER_ID,
    Trade.PLUMBING: DEMO_PLUMBER_ID,
    Trade.ELECTRICAL: DEMO_ELECTRICIAN_ID,
    Trade.SCAFFOLDING: DEMO_SCAFFOLDER_ID,
}

_HISTORY_YEAR_CASES: list[dict] = [
    # 27 Cathedral Walk -- plumbing twice (a real recurring issue), plus electrics.
    dict(
        label="hist:cathedral:2023:plumbing",
        property_id=DEMO_PROPERTY_2_ID,
        tenant_id=DEMO_TENANT_2_ID,
        title="Slow leak under the kitchen sink soaking the cupboard base",
        description="Tenant reported a persistent drip from the trap under the kitchen sink; cupboard base swollen.",
        location="Kitchen",
        trade=Trade.PLUMBING,
        scope="Replace failed trap seal and dry out cupboard base.",
        quote_pence=42000,
        year=2023,
        month=3,
        outcome_days=4,
    ),
    dict(
        label="hist:cathedral:2024:plumbing",
        property_id=DEMO_PROPERTY_2_ID,
        tenant_id=DEMO_TENANT_2_ID,
        title="Bathroom basin draining very slowly",
        description="Tenant reported the basin taking several minutes to drain, with occasional gurgling.",
        location="Bathroom",
        trade=Trade.PLUMBING,
        scope="Clear blocked basin waste and re-seat the pop-up waste.",
        quote_pence=28500,
        year=2024,
        month=9,
        outcome_days=2,
    ),
    dict(
        label="hist:cathedral:2025:electrical",
        property_id=DEMO_PROPERTY_2_ID,
        tenant_id=DEMO_TENANT_2_ID,
        title="Hallway sockets tripping the consumer unit",
        description="Tenant reported the hallway ring tripping the RCD whenever the hoover is used.",
        location="Hallway",
        trade=Trade.ELECTRICAL,
        scope="Fault-find hallway ring, replace damaged socket and re-test circuit.",
        quote_pence=115000,
        year=2025,
        month=2,
        outcome_days=6,
    ),
    # 58 Gloucester Road -- roofing twice (recurring), plus a one-off.
    dict(
        label="hist:gloucester:2023:roofing",
        property_id=DEMO_PROPERTY_3_ID,
        tenant_id=DEMO_TENANT_3_ID,
        title="Rain coming in around the chimney flashing",
        description="Tenant reported damp patches on the chimney breast after heavy rain.",
        location="Second floor bedroom",
        trade=Trade.ROOFING,
        scope="Strip and renew lead flashing around the chimney stack; make good internally.",
        quote_pence=240000,
        year=2023,
        month=11,
        outcome_days=12,
    ),
    dict(
        label="hist:gloucester:2024:other",
        property_id=DEMO_PROPERTY_3_ID,
        tenant_id=DEMO_TENANT_3_ID,
        title="Front door not closing flush against the frame",
        description="Tenant reported the front door catching on the frame and not locking without force.",
        location="Front entrance",
        trade=Trade.OTHER,
        scope="Ease and adjust front door, realign keep plate.",
        quote_pence=16500,
        year=2024,
        month=6,
        outcome_days=3,
    ),
    dict(
        label="hist:gloucester:2025:roofing",
        property_id=DEMO_PROPERTY_3_ID,
        tenant_id=DEMO_TENANT_3_ID,
        title="Gutter pulling away from the fascia at the rear",
        description="Tenant reported water sheeting down the rear wall instead of running to the downpipe.",
        location="Rear elevation",
        trade=Trade.ROOFING,
        scope="Re-fix rear guttering, renew two brackets and clear the downpipe.",
        quote_pence=89000,
        year=2025,
        month=5,
        outcome_days=5,
    ),
]

# Live (still-ACTIVE) cases whose scheduled visits populate "Upcoming visits".
_UPCOMING_CASES: list[dict] = [
    dict(
        label="live:cathedral:boiler",
        property_id=DEMO_PROPERTY_2_ID,
        tenant_id=DEMO_TENANT_2_ID,
        title="Boiler losing pressure overnight and needing daily top-ups",
        description="Tenant reported the boiler dropping below 1 bar most mornings and needing re-pressurising.",
        location="Kitchen",
        trade=Trade.PLUMBING,
        scope="Investigate pressure loss, check expansion vessel and pressure relief valve.",
        quote_pence=38000,
        days_ahead=2,
    ),
    dict(
        label="live:gloucester:gutter",
        property_id=DEMO_PROPERTY_3_ID,
        tenant_id=DEMO_TENANT_3_ID,
        title="Gutter overflowing above the front bay window",
        description="Tenant reported the front gutter overflowing during rain, splashing the bay window below.",
        location="Front elevation",
        trade=Trade.ROOFING,
        scope="Clear front guttering and check falls to the downpipe.",
        quote_pence=24000,
        days_ahead=4,
    ),
]

# The dependency story, as a real case: a roof repair that a contractor
# found unreachable without scaffolding, so a SCAFFOLD_INSTALL work order
# now blocks the REPAIR one. Gives WorkGraph a genuine two-node + edge graph
# and the approval card a genuine pending decision.
_SCAFFOLD_CASE_LABEL = "live:redcliffe:scaffold"


def _hist_ids(label: str) -> dict[str, str]:
    """Deterministic ids for every row belonging to one seeded case, so the
    whole bundle is insert-once/idempotent off its label alone."""
    return {
        key: _demo_id(f"{label}:{key}")
        for key in (
            "case", "issue", "work_order", "scaffold_work_order", "action",
            "scaffold_action", "appointment", "report", "dependency",
        )
    }


def _source_ref(observed_at: datetime, source_id: str) -> dict:
    return {
        "source_type": SourceType.OPERATOR.value,
        "source_id": source_id,
        "locator": None,
        "observed_at": observed_at.isoformat(),
        "provenance": Provenance.SIMULATED.value,
    }


async def _seed_demo_activity(session) -> dict[str, int]:
    """Inserts the history/dependency/upcoming-visit/message rows above.
    Every row is keyed on a deterministic uuid5 so re-running is a no-op.
    Case numbers are allocated from the live MAX at insert time (not baked
    into the label) so seeding can never collide with cases a user already
    created."""
    counts = {"cases": 0, "appointments": 0, "reports": 0, "dependencies": 0, "messages": 0}

    next_number = (
        await session.execute(sa.select(sa.func.coalesce(sa.func.max(RepairCaseModel.case_number), 0)))
    ).scalar_one() + 1

    def take_number() -> int:
        nonlocal next_number
        value = next_number
        next_number += 1
        return value

    # --- Closed history (drives quoted-by-trade / by-year / recurring) -----
    for spec in _HISTORY_YEAR_CASES:
        ids = _hist_ids(spec["label"])
        if await session.get(RepairCaseModel, ids["case"]) is not None:
            continue
        created = datetime(spec["year"], spec["month"], 12, 9, 30, tzinfo=timezone.utc)
        resolved = created + timedelta(days=spec["outcome_days"])
        session.add(
            RepairCaseModel(
                id=ids["case"], case_number=take_number(), property_id=spec["property_id"],
                tenant_id=spec["tenant_id"], status=CaseStatus.RESOLVED, version=4,
                title=spec["title"], risk={"urgency": "ROUTINE"}, created_at=created,
                updated_at=resolved, last_decision_summary="Work completed and tenant confirmed resolution.",
            )
        )
        session.add(
            RepairIssueModel(
                id=ids["issue"], case_id=ids["case"], description=spec["description"],
                location=spec["location"], started_at=created,
                tenant_resolution_confirmed_at=resolved,
            )
        )
        session.add(
            WorkOrderModel(
                id=ids["work_order"], case_id=ids["case"], issue_id=ids["issue"],
                kind=WorkOrderKind.REPAIR, trade=spec["trade"], scope=spec["scope"],
                status=WorkOrderStatus.COMPLETED,
                contractor_id=_CONTRACTOR_BY_TRADE.get(spec["trade"]),
                required_for_resolution=True, quote_pence=spec["quote_pence"],
                approved_limit_pence=spec["quote_pence"], created_at=created, updated_at=resolved,
            )
        )
        counts["cases"] += 1

    # --- Still-open cases with a confirmed future visit -------------------
    now = datetime.now(timezone.utc)
    for spec in _UPCOMING_CASES:
        ids = _hist_ids(spec["label"])
        if await session.get(RepairCaseModel, ids["case"]) is not None:
            continue
        created = now - timedelta(days=3)
        # Resolve by trade rather than trusting the spec blindly: a case is
        # only ever assigned a firm that actually lists that trade.
        contractor_id = _CONTRACTOR_BY_TRADE.get(spec["trade"])
        session.add(
            RepairCaseModel(
                id=ids["case"], case_number=take_number(), property_id=spec["property_id"],
                tenant_id=spec["tenant_id"], status=CaseStatus.ACTIVE, version=3,
                title=spec["title"], risk={"urgency": "ROUTINE"}, created_at=created,
                updated_at=now - timedelta(hours=6),
                last_decision_summary="Visit scheduled with an approved contractor.",
            )
        )
        session.add(
            RepairIssueModel(
                id=ids["issue"], case_id=ids["case"], description=spec["description"],
                location=spec["location"], started_at=created,
            )
        )
        session.add(
            WorkOrderModel(
                id=ids["work_order"], case_id=ids["case"], issue_id=ids["issue"],
                kind=WorkOrderKind.REPAIR, trade=spec["trade"], scope=spec["scope"],
                status=WorkOrderStatus.SCHEDULED, contractor_id=contractor_id,
                required_for_resolution=True, quote_pence=spec["quote_pence"],
                approved_limit_pence=spec["quote_pence"], created_at=created, updated_at=now,
            )
        )
        counts["cases"] += 1
        if contractor_id is None:
            # An appointment requires a contractor FK; without an approved
            # firm for this trade there is nothing honest to book against.
            continue
        # These models declare raw ForeignKey columns with no ORM
        # relationship(), so SQLAlchemy's unit of work can't infer that the
        # case/work-order rows must land before the rows pointing at them --
        # flush each layer explicitly rather than relying on insert order.
        await session.flush()
        session.add(
            ActionRecordModel(
                id=ids["action"], case_id=ids["case"], kind="SCHEDULE_VISIT",
                target_id=ids["work_order"], idempotency_key=f"seed:{spec['label']}:booking",
                payload_hash=_demo_id(f"{spec['label']}:hash").replace("-", "")[:64],
                proposal={
                    "case_id": ids["case"], "expected_case_version": 2,
                    "trigger_event_id": _demo_id(f"{spec['label']}:trigger"),
                    "decision_summary": "Booked the first available slot with an approved contractor.",
                    "evidence_refs": [],
                    # Must satisfy the real ScheduleVisit schema in full --
                    # CaseSnapshot validates every pending action record, so
                    # a partial payload here 500s the whole case detail.
                    "action": {
                        "kind": "SCHEDULE_VISIT", "work_order_id": ids["work_order"],
                        "contractor_id": contractor_id,
                        "slot_id": f"seed-slot-{spec['label']}",
                        "tenant_availability_ids": [],
                    },
                },
                state=ActionState.SUCCEEDED.value, created_at=created, updated_at=now,
            )
        )
        start_at = (now + timedelta(days=spec["days_ahead"])).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        session.add(
            AppointmentModel(
                id=ids["appointment"], case_id=ids["case"], work_order_id=ids["work_order"],
                contractor_id=contractor_id, slot_id=f"seed-slot-{spec['label']}",
                start_at=start_at, end_at=start_at + timedelta(hours=3),
                status=AppointmentStatus.CONFIRMED, connector=ConnectorType.MOCK,
                action_id=ids["action"], attempt_number=1, provenance=Provenance.SIMULATED,
            )
        )
        await session.flush()
        counts["appointments"] += 1

    # --- The scaffold-blocks-roofing case (WorkGraph + approval card) ------
    ids = _hist_ids(_SCAFFOLD_CASE_LABEL)
    if await session.get(RepairCaseModel, ids["case"]) is None:
        created = now - timedelta(days=6)
        visited = now - timedelta(days=1, hours=4)
        session.add(
            RepairCaseModel(
                id=ids["case"], case_number=take_number(), property_id=DEMO_PROPERTY_4_ID,
                tenant_id=DEMO_TENANT_4_ID, status=CaseStatus.ACTIVE, version=6,
                title="Slipped ridge tiles above the bay window after high winds",
                risk={"urgency": "URGENT"}, created_at=created, updated_at=visited,
                last_decision_summary=(
                    "Roofer could not work at height safely without an access platform; "
                    "scaffolding raised as a prerequisite and the roof repair is blocked until it is up."
                ),
            )
        )
        session.add(
            RepairIssueModel(
                id=ids["issue"], case_id=ids["case"],
                description="Tenant reported two ridge tiles visibly displaced above the front bay window after high winds.",
                location="Front elevation, above bay window", started_at=created,
                unresolved_concerns=["Displaced tiles remain a falling risk until secured."],
            )
        )
        session.add(
            WorkOrderModel(
                id=ids["work_order"], case_id=ids["case"], issue_id=ids["issue"],
                kind=WorkOrderKind.REPAIR, trade=Trade.ROOFING,
                scope="Re-bed and secure displaced ridge tiles above the front bay window.",
                status=WorkOrderStatus.BLOCKED, contractor_id=DEMO_ROOFER_3_ID,
                required_for_resolution=True, quote_pence=145000, approved_limit_pence=145000,
                created_at=created, updated_at=visited,
            )
        )
        session.add(
            WorkOrderModel(
                id=ids["scaffold_work_order"], case_id=ids["case"], issue_id=ids["issue"],
                kind=WorkOrderKind.SCAFFOLD_INSTALL, trade=Trade.SCAFFOLDING,
                scope="Erect access scaffold to the front elevation for safe ridge-level working.",
                status=WorkOrderStatus.READY, contractor_id=DEMO_SCAFFOLDER_ID,
                required_for_resolution=True, quote_pence=68000,
                created_at=visited, updated_at=visited,
            )
        )
        await session.flush()  # case/issue/work orders before anything FK-ing them
        session.add(
            ActionRecordModel(
                id=ids["action"], case_id=ids["case"], kind="SCHEDULE_VISIT",
                target_id=ids["work_order"], idempotency_key=f"seed:{_SCAFFOLD_CASE_LABEL}:booking",
                payload_hash=_demo_id(f"{_SCAFFOLD_CASE_LABEL}:hash").replace("-", "")[:64],
                proposal={
                    "case_id": ids["case"], "expected_case_version": 3,
                    "trigger_event_id": _demo_id(f"{_SCAFFOLD_CASE_LABEL}:trigger"),
                    "decision_summary": "Booked an inspection visit with an approved roofer.",
                    "evidence_refs": [],
                    "action": {
                        "kind": "SCHEDULE_VISIT", "work_order_id": ids["work_order"],
                        "contractor_id": DEMO_ROOFER_3_ID,
                        "slot_id": f"seed-slot-{_SCAFFOLD_CASE_LABEL}",
                        "tenant_availability_ids": [],
                    },
                },
                state=ActionState.SUCCEEDED.value, created_at=created, updated_at=visited,
            )
        )
        await session.flush()  # action before the appointment referencing it
        session.add(
            AppointmentModel(
                id=ids["appointment"], case_id=ids["case"], work_order_id=ids["work_order"],
                contractor_id=DEMO_ROOFER_3_ID, slot_id=f"seed-slot-{_SCAFFOLD_CASE_LABEL}",
                start_at=visited, end_at=visited + timedelta(hours=2),
                status=AppointmentStatus.FINISHED, visit_outcome=VisitOutcome.BLOCKED,
                connector=ConnectorType.MOCK, action_id=ids["action"], attempt_number=1,
                provenance=Provenance.SIMULATED,
            )
        )
        await session.flush()  # appointment before the report referencing it
        session.add(
            ContractorReportModel(
                id=ids["report"], case_id=ids["case"], work_order_id=ids["work_order"],
                appointment_id=ids["appointment"], contractor_id=DEMO_ROOFER_3_ID,
                text=(
                    "Attended and inspected from ground level. Two ridge tiles are displaced and one is "
                    "overhanging the bay. Cannot be reached safely off a ladder at this height and pitch -- "
                    "an access scaffold to the front elevation is needed before the repair can be carried out."
                ),
                observed_at=visited, received_at=visited + timedelta(minutes=20),
                source_ref=_source_ref(visited, ids["appointment"]),
                provenance=Provenance.SIMULATED, interpretation_status=InterpretationStatus.APPLIED,
            )
        )
        await session.flush()  # report before the dependency citing it
        session.add(
            DependencyModel(
                id=ids["dependency"], case_id=ids["case"],
                prerequisite_work_order_id=ids["scaffold_work_order"],
                dependent_work_order_id=ids["work_order"], status=DependencyStatus.OPEN,
                reason="Ridge-level work cannot proceed safely until access scaffolding is erected.",
                discovered_from_report_id=ids["report"], created_at=visited,
            )
        )
        # The one genuinely pending decision: committing spend on the
        # scaffold. Left AWAITING_APPROVAL so the approval card and the
        # notifications bell both have something real to act on.
        session.add(
            ActionRecordModel(
                id=ids["scaffold_action"], case_id=ids["case"], kind="SCHEDULE_VISIT",
                target_id=ids["scaffold_work_order"],
                idempotency_key=f"seed:{_SCAFFOLD_CASE_LABEL}:scaffold-booking",
                payload_hash=_demo_id(f"{_SCAFFOLD_CASE_LABEL}:scaffold-hash").replace("-", "")[:64],
                proposal={
                    "case_id": ids["case"], "expected_case_version": 6,
                    "trigger_event_id": _demo_id(f"{_SCAFFOLD_CASE_LABEL}:scaffold-trigger"),
                    "decision_summary": (
                        "Roofer reported the ridge tiles are unreachable safely without an access "
                        "platform. Proposing to book Steadfast Scaffold Co to erect a front-elevation "
                        "scaffold (quoted £680) so the blocked roof repair can proceed."
                    ),
                    "evidence_refs": [],
                    "action": {
                        "kind": "SCHEDULE_VISIT", "work_order_id": ids["scaffold_work_order"],
                        "contractor_id": DEMO_SCAFFOLDER_ID,
                        "slot_id": f"seed-slot-{_SCAFFOLD_CASE_LABEL}-scaffold",
                        "tenant_availability_ids": [],
                    },
                },
                state=ActionState.AWAITING_APPROVAL.value, created_at=visited, updated_at=visited,
            )
        )
        counts["cases"] += 1
        counts["appointments"] += 1
        counts["reports"] += 1
        counts["dependencies"] += 1

    # --- Message threads ---------------------------------------------------
    scaffold_ids = _hist_ids(_SCAFFOLD_CASE_LABEL)
    boiler_ids = _hist_ids("live:cathedral:boiler")
    threads: list[tuple[str, list[tuple[MessageSenderType, str, str, int]]]] = [
        (
            scaffold_ids["case"],
            [
                (MessageSenderType.TENANT, "Aaliyah Bennett",
                 "Two of the ridge tiles above the bay look like they've shifted after the wind last night. "
                 "One is hanging over the edge.", 6),
                (MessageSenderType.OPERATOR, "Fixi",
                 "Thanks for flagging this -- please keep clear of the front path underneath until it's made safe. "
                 "We're arranging a roofer now.", 6),
                (MessageSenderType.CONTRACTOR, "Aisha Rahman, Summit Heights Roofing",
                 "Attended today. Can't reach it safely off a ladder at that pitch -- you'll need a scaffold to the "
                 "front before we can re-bed those tiles.", 1),
            ],
        ),
        (
            boiler_ids["case"],
            [
                (MessageSenderType.TENANT, "Priya Desai",
                 "The boiler's down to about 0.8 bar again this morning. I've topped it up but it keeps dropping.", 3),
                (MessageSenderType.OPERATOR, "Fixi",
                 "Noted -- we've booked an engineer to look at the expansion vessel and pressure relief valve.", 2),
            ],
        ),
    ]
    for case_id, entries in threads:
        if await session.get(RepairCaseModel, case_id) is None:
            continue
        for index, (sender_type, sender_name, text, days_ago) in enumerate(entries):
            message_id = _demo_id(f"message:{case_id}:{index}")
            if await session.get(MessageModel, message_id) is not None:
                continue
            session.add(
                MessageModel(
                    id=message_id, case_id=case_id, sender_type=sender_type,
                    sender_name=sender_name, text=text, photo_url=None,
                    created_at=now - timedelta(days=days_ago, hours=index),
                )
            )
            counts["messages"] += 1

    return counts


async def seed() -> None:
    await create_all()
    added_properties = added_tenants = added_contractors = 0
    updated_properties = 0
    async with session_scope() as session:
        for row in PROPERTIES:
            existing_property = await session.get(PropertyModel, row["id"])
            if existing_property is None:
                session.add(PropertyModel(**row))
                added_properties += 1
            elif existing_property.build_year is None and row.get("build_year") is not None:
                # Backfill for a property inserted by an earlier seed run,
                # before build_year existed/was populated here. Never
                # overwrites a build_year that's already set.
                existing_property.build_year = row["build_year"]
                updated_properties += 1
        for row in TENANTS:
            if await session.get(TenantModel, row["id"]) is None:
                session.add(TenantModel(**row))
                added_tenants += 1
        for row in CONTRACTORS:
            if await session.get(ContractorModel, row["id"]) is None:
                session.add(ContractorModel(**row))
                added_contractors += 1
        # The activity rows below carry FKs to the properties/tenants/
        # contractors above, so those have to hit the DB first.
        await session.flush()
        activity = await _seed_demo_activity(session)
    print(
        f"Seed complete: {added_properties} propert(y/ies), {added_tenants} tenant(s), "
        f"{added_contractors} contractor(s) newly added, {updated_properties} propert(y/ies) "
        f"backfilled with build_year "
        f"({len(PROPERTIES)} properties / {len(TENANTS)} tenants / {len(CONTRACTORS)} contractors total)."
    )
    print(
        f"Demo activity: {activity['cases']} case(s), {activity['appointments']} appointment(s), "
        f"{activity['reports']} contractor report(s), {activity['dependencies']} dependency(ies), "
        f"{activity['messages']} message(s) newly added."
    )


if __name__ == "__main__":
    asyncio.run(seed())
