"""Pure, DB-free generator for the synthetic historical archive dataset.

No SQLAlchemy imports here (`app.schemas` enums are plain Pydantic/stdlib
enums, so importing them does not pull in the ORM or touch a database).
`build_dataset()` returns plain dataclasses that `importer.py` turns into
ORM rows; keeping generation pure makes the dataset inspectable/testable
without a database and keeps this module reusable if storage ever changes.

Determinism: every random choice is drawn from a single `random.Random(seed)`
instance in a fixed call order, so `build_dataset(seed=X)` is bit-for-bit
reproducible. Every id is `uuid.uuid5(_NAMESPACE, <stable label>)`, so the
same label always yields the same id, on this run or any later one.

Timestamp ceiling: every generated timestamp is at or before `ARCHIVE_NOW_CEILING`
below, a fixed point in the past. Using a hardcoded ceiling (instead of
`datetime.now()`) keeps this module pure and keeps every generated dataset
permanently in the past -- CLAUDE.md's "strictly in the past" rule does not
erode as real time moves forward past whatever day this was written.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.schemas import (
    CaseStatus,
    ContractorApprovalStatus,
    CostKind,
    EventType,
    MessageDeliveryState,
    MessageSenderType,
    Provenance,
    RoofResponsibility,
    SourceType,
    Trade,
    VisitOutcome,
    WorkOrderKind,
    WorkOrderStatus,
)

GENERATOR_VERSION = "1.2.1"
DEFAULT_SEED = 20260920
DEFAULT_LABEL = "synthetic-archive-v1"

# CLAUDE.md: "no fake live traces" -- an archival OrchestrationRun must never
# carry a model_id that names a real model (no "gemini-..." anywhere), or a
# reader could mistake synthesized reasoning for output a real model
# produced. This is the one and only model_id every archival run uses.
MODEL_ID = "fixture:archive-v1"

# A fixed point safely in the past of "today" (2026-09-20) at the time this
# generator was written, and -- because real time only moves forward --
# permanently in the past of every later run too. Nothing generated here is
# ever dated after this instant.
ARCHIVE_NOW_CEILING = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "repairflow.archive")


def stable_id(label: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, label))


# --------------------------------------------------------------------------
# Plain dataclasses -- what importer.py turns into ORM rows.
# --------------------------------------------------------------------------


@dataclass
class ArchiveProperty:
    id: str
    key: str
    address_line: str
    postcode: str
    landlord_reference: str
    roof_responsibility: RoofResponsibility
    build_year: int
    property_type: str
    bedrooms: int
    photo_key: str
    access_notes: str | None = None


@dataclass
class ArchiveTenant:
    id: str
    property_key: str
    display_name: str
    preferred_channel: str = "NONE"


@dataclass
class ArchiveContractor:
    id: str
    key: str
    display_name: str
    trades: list[str]
    service_postcodes: list[str]
    verification_note: str


@dataclass
class ArchiveEvidenceRef:
    source_type: SourceType
    locator: str
    observed_at: datetime
    provenance: Provenance = Provenance.FIXTURE


@dataclass
class ArchiveWorkOrder:
    id: str
    kind: WorkOrderKind
    trade: Trade
    scope: str
    status: WorkOrderStatus
    contractor_key: str | None
    quote_pence: int | None
    approved_limit_pence: int | None
    created_at: datetime
    updated_at: datetime


@dataclass
class ArchiveAppointment:
    id: str
    action_id: str
    work_order_index: int
    contractor_key: str
    slot_id: str
    start_at: datetime
    end_at: datetime
    attempt_number: int
    visit_outcome: VisitOutcome
    action_idempotency_key: str
    action_created_at: datetime
    action_updated_at: datetime
    action_expected_case_version: int


@dataclass
class ArchiveContractorReport:
    """A contractor's write-up of one attended visit -- one per appointment
    in a resolved case (cancelled cases have no appointments and so get no
    reports, same as reality: work that was never carried out has nobody
    to write it up). `appointment_index`/`work_order_index` index into the
    owning `ArchiveCase.appointments`/`.work_orders`, mirroring how
    `ArchiveAppointment.work_order_index` already does it, so importer.py
    can resolve the real appointment/work-order/contractor ids exactly the
    way it already resolves an appointment's own contractor and slot."""

    id: str
    appointment_index: int
    work_order_index: int
    contractor_key: str
    text: str
    observed_at: datetime
    received_at: datetime


@dataclass
class ArchiveDependency:
    """A prerequisite/dependent work-order edge, discovered from a BLOCKED
    visit and satisfied before the case closes (every archival case is
    RESOLVED or CANCELLED, and a case cannot resolve with an open
    dependency -- docs/07). Indexes (not raw ids) into `ArchiveCase.
    work_orders`/`.appointments`/`.reports`, matching the convention every
    other cross-referencing archive dataclass already uses."""

    id: str
    prerequisite_work_order_index: int
    dependent_work_order_index: int
    reason: str
    discovered_from_appointment_index: int
    satisfied_by_appointment_index: int
    satisfied_at: datetime | None = None  # filled in once the satisfying event's own timestamp is known


@dataclass
class ArchiveCaseEvent:
    """One append-only fact in the case's history (app/schemas.py
    CaseEvent). `causation_event_id` is a real id (not an index): every id
    in this module is a deterministic `stable_id(...)` computed at the
    moment the object is built, so an event can reference an earlier
    sibling's id directly with no importer-side index resolution needed --
    the same reason `ArchiveWorkOrder.id`/`ArchiveAppointment.id` are
    already concrete strings rather than positions."""

    id: str
    type: str  # EventType value
    occurred_at: datetime
    received_at: datetime
    actor_type: str
    actor_id: str
    source_event_key: str
    correlation_id: str
    causation_event_id: str | None = None
    payload: dict = field(default_factory=dict)


@dataclass
class ArchiveOrchestrationRun:
    """One coordinator decision point (app/schemas.py OrchestrationRun).
    `action` is the *complete*, already-resolved inner NextAction payload
    (real work-order/contractor/report ids substituted in here, not left
    as indices) -- importer.py wraps it in the outer ActionProposal
    envelope (case_id/expected_case_version/trigger_event_id/
    decision_summary/evidence_refs) and validates the whole thing against
    the real ActionProposal schema before writing it, exactly as it
    already validates other archival records against their live schemas."""

    id: str
    trigger_event_id: str
    started_at: datetime
    finished_at: datetime
    decision_summary: str
    action: dict
    tool_names: list[str] = field(default_factory=list)


@dataclass
class ArchiveCost:
    id: str
    work_order_index: int | None
    kind: CostKind
    amount_pence: int
    description: str
    incurred_at: datetime


@dataclass
class ArchiveNote:
    id: str
    body: str
    author: str
    created_at: datetime


@dataclass
class ArchiveMessage:
    id: str
    sender_type: MessageSenderType
    sender_name: str
    text: str
    created_at: datetime
    read_at: datetime
    delivery_state: MessageDeliveryState = MessageDeliveryState.INTERNAL_NOTE


@dataclass
class ArchiveDocument:
    stored_name: str
    display_name: str
    description: str
    content: str
    uploaded_at: datetime


@dataclass
class ArchiveCase:
    id: str
    label: str
    property_key: str
    tenant_key: str
    title: str
    category: Trade
    status: CaseStatus
    description: str
    location: str
    urgency: str
    created_at: datetime
    archived_closed_at: datetime
    last_decision_summary: str
    evidence_refs: list[ArchiveEvidenceRef] = field(default_factory=list)
    work_orders: list[ArchiveWorkOrder] = field(default_factory=list)
    appointments: list[ArchiveAppointment] = field(default_factory=list)
    reports: list[ArchiveContractorReport] = field(default_factory=list)
    dependencies: list[ArchiveDependency] = field(default_factory=list)
    costs: list[ArchiveCost] = field(default_factory=list)
    notes: list[ArchiveNote] = field(default_factory=list)
    messages: list[ArchiveMessage] = field(default_factory=list)
    document: ArchiveDocument | None = None
    events: list[ArchiveCaseEvent] = field(default_factory=list)
    runs: list[ArchiveOrchestrationRun] = field(default_factory=list)


@dataclass
class ArchiveDataset:
    label: str
    generator_version: str
    random_seed: int
    description: str
    properties: list[ArchiveProperty]
    tenants: list[ArchiveTenant]
    contractors: list[ArchiveContractor]
    cases: list[ArchiveCase]

    def contractor_id(self, key: str) -> str:
        for c in self.contractors:
            if c.key == key:
                return c.id
        raise KeyError(key)

    def property_id(self, key: str) -> str:
        for p in self.properties:
            if p.key == key:
                return p.id
        raise KeyError(key)

    def tenant_id(self, key: str) -> str:
        for t in self.tenants:
            if t.property_key == key:
                return t.id
        raise KeyError(key)


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------

PROPERTY_SPECS: list[dict] = [
    dict(
        key="king_street", address_line="14 King Street, Bristol", postcode="BS1 5NB",
        landlord_reference="ARC-LL-001", build_year=1898, property_type="Terraced house", bedrooms=3,
        photo_key="property-birch-lane.jpg", roof_responsibility=RoofResponsibility.LANDLORD,
        access_notes="Roof accessed via rear yard ladder point only.",
        tenant_name="Robert Whitfield", case_count=8, recurring_trade=Trade.ROOFING, recurring_count=4,
    ),
    dict(
        key="birch_lane", address_line="8 Birch Lane, Bath", postcode="BA2 4RJ",
        landlord_reference="ARC-LL-002", build_year=1972, property_type="Semi-detached house", bedrooms=4,
        photo_key="property-church-road.jpg", roof_responsibility=RoofResponsibility.LANDLORD,
        access_notes=None,
        tenant_name="Margaret Osei", case_count=9, recurring_trade=Trade.PLUMBING, recurring_count=3,
    ),
    dict(
        key="church_road", address_line="22 Church Road, Gloucester", postcode="GL1 3JN",
        landlord_reference="ARC-LL-003", build_year=1935, property_type="Terraced house", bedrooms=2,
        photo_key="property-maple-road.jpg", roof_responsibility=RoofResponsibility.OTHER,
        access_notes="Loft hatch access only, no external ladder point.",
        tenant_name="Daniel Kowalski", case_count=6, recurring_trade=Trade.ELECTRICAL, recurring_count=2,
    ),
    dict(
        key="maple_road", address_line="5 Maple Road, Swindon", postcode="SN1 2EF",
        landlord_reference="ARC-LL-004", build_year=2001, property_type="Flat", bedrooms=2,
        photo_key="property-oak-avenue.jpg", roof_responsibility=RoofResponsibility.UNKNOWN,
        access_notes=None,
        tenant_name="Fatima Choudhury", case_count=5, recurring_trade=None, recurring_count=0,
    ),
    dict(
        key="oak_avenue", address_line="41 Oak Avenue, Newport", postcode="NP20 4QW",
        landlord_reference="ARC-LL-005", build_year=1958, property_type="Semi-detached house", bedrooms=3,
        photo_key="property-riverdale-road.jpg", roof_responsibility=RoofResponsibility.LANDLORD,
        access_notes="Steep-pitch roof; height-access certified contractor required.",
        tenant_name="Liam Fitzgerald", case_count=10, recurring_trade=Trade.ROOFING, recurring_count=3,
    ),
    dict(
        key="riverdale_road", address_line="3 Riverdale Road, Exeter", postcode="EX4 6LP",
        landlord_reference="ARC-LL-006", build_year=1988, property_type="Detached house", bedrooms=4,
        photo_key="property-station-view.jpg", roof_responsibility=RoofResponsibility.OTHER,
        access_notes=None,
        tenant_name="Grace Mensah", case_count=7, recurring_trade=Trade.PLUMBING, recurring_count=2,
    ),
    dict(
        key="station_view", address_line="17 Station View, Taunton", postcode="TA1 3HD",
        landlord_reference="ARC-LL-007", build_year=1926, property_type="Terraced house", bedrooms=3,
        photo_key="property-wellington-close.jpg", roof_responsibility=RoofResponsibility.UNKNOWN,
        access_notes="Managing agent holds key for communal areas.",
        tenant_name="Thomas Iqbal", case_count=8, recurring_trade=Trade.ELECTRICAL, recurring_count=3,
    ),
    dict(
        key="wellington_close", address_line="2 Wellington Close, Cardiff", postcode="CF10 2FG",
        landlord_reference="ARC-LL-008", build_year=1965, property_type="Flat", bedrooms=1,
        photo_key="house-exterior.jpg", roof_responsibility=RoofResponsibility.LANDLORD,
        access_notes=None,
        tenant_name="Eleanor Vaughn", case_count=7, recurring_trade=None, recurring_count=0,
    ),
]

CONTRACTOR_SPECS: list[dict] = [
    dict(key="roofer_a", display_name="Kingswood Roofing (archived, FIXTURE)", trade=Trade.ROOFING,
         postcodes=["BS1", "BS2", "NP20"]),
    dict(key="roofer_b", display_name="Severnside Roofing Services (archived, FIXTURE)", trade=Trade.ROOFING,
         postcodes=["NP20", "EX4"]),
    dict(key="plumber_a", display_name="Blackthorn Plumbing (archived, FIXTURE)", trade=Trade.PLUMBING,
         postcodes=["BA2", "EX4"]),
    dict(key="electrician_a", display_name="Redgate Electrical (archived, FIXTURE)", trade=Trade.ELECTRICAL,
         postcodes=["GL1", "TA1"]),
    dict(key="scaffolder_a", display_name="Ironframe Scaffolding (archived, FIXTURE)", trade=Trade.SCAFFOLDING,
         postcodes=["BS1", "GL1", "TA1"]),
    dict(key="general_a", display_name="Allwright General Maintenance (archived, FIXTURE)", trade=Trade.OTHER,
         postcodes=["SN1", "CF10", "BS1"]),
]

_TRADE_TO_CONTRACTOR_KEYS: dict[Trade, list[str]] = {
    Trade.ROOFING: ["roofer_a", "roofer_b"],
    Trade.PLUMBING: ["plumber_a"],
    Trade.ELECTRICAL: ["electrician_a"],
    Trade.SCAFFOLDING: ["scaffolder_a"],
    Trade.OTHER: ["general_a"],
}

_ALL_TRADES = [Trade.ROOFING, Trade.PLUMBING, Trade.ELECTRICAL, Trade.SCAFFOLDING, Trade.OTHER]

_YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
_YEAR_WEIGHTS = [3, 4, 5, 6, 6, 3]
# Latest a 2026 case's created_at may fall -- leaves ~60 days of headroom for
# the full work-order -> appointment -> invoice -> closure lifecycle to land
# before ARCHIVE_NOW_CEILING.
_YEAR_2026_LATEST_CREATED = ARCHIVE_NOW_CEILING - timedelta(days=60)

_TITLES: dict[Trade, list[tuple[str, str, str]]] = {
    # (title, description, location)
    Trade.ROOFING: [
        ("Rain coming in around the chimney flashing",
         "Tenant reported damp patches spreading on the chimney breast after heavy rain.",
         "Second floor bedroom"),
        ("Slipped ridge tiles above the bay window",
         "Tenant reported two ridge tiles visibly displaced after high winds overnight.",
         "Front elevation, above bay window"),
        ("Gutter pulling away from the fascia at the rear",
         "Tenant reported water sheeting down the rear wall instead of draining away.",
         "Rear elevation"),
        ("Damp patch reappearing on the landing ceiling after rain",
         "Tenant reported a recurring damp stain on the landing ceiling that darkens after rainfall.",
         "Landing ceiling"),
        ("Flashing repair failing again around the chimney breast",
         "Tenant reported the same chimney breast damp returning a season after the last repair.",
         "Loft space, chimney breast"),
        ("Persistent damp staining on the top-floor ceiling",
         "Tenant reported a spreading brown stain on the top-floor ceiling despite prior work.",
         "Top floor bedroom ceiling"),
        ("Loose tiles rattling in high wind",
         "Tenant reported loose roof tiles rattling and one tile found in the garden.",
         "Rear roof slope"),
        ("Valley gutter overflowing in heavy rain",
         "Tenant reported water overflowing the valley gutter and running down an external wall.",
         "Roof valley, side elevation"),
    ],
    Trade.PLUMBING: [
        ("Slow leak under the kitchen sink soaking the cupboard base",
         "Tenant reported a persistent drip from the trap under the kitchen sink.",
         "Kitchen"),
        ("Bathroom basin draining very slowly",
         "Tenant reported the basin taking several minutes to drain, with gurgling.",
         "Bathroom"),
        ("Boiler losing pressure overnight",
         "Tenant reported the boiler dropping below 1 bar most mornings.",
         "Airing cupboard"),
        ("Dripping tap in the family bathroom",
         "Tenant reported a steadily dripping mixer tap keeping them awake at night.",
         "Family bathroom"),
        ("Toilet cistern not refilling properly",
         "Tenant reported the upstairs toilet cistern refilling very slowly after flushing.",
         "Upstairs bathroom"),
        ("Radiator in the lounge not heating up",
         "Tenant reported the lounge radiator staying cold at the top while the rest of the system runs.",
         "Lounge"),
        ("Stopcock seized and leaking at the union",
         "Tenant reported a small leak from the stopcock under the kitchen sink.",
         "Kitchen, under-sink cupboard"),
    ],
    Trade.ELECTRICAL: [
        ("Hallway sockets tripping the consumer unit",
         "Tenant reported the hallway ring tripping the RCD whenever the vacuum is used.",
         "Hallway"),
        ("Kitchen light fitting flickering intermittently",
         "Tenant reported the kitchen ceiling light flickering on and off at random.",
         "Kitchen"),
        ("Extractor fan in the bathroom not switching on",
         "Tenant reported the bathroom extractor fan no longer starting with the light.",
         "Bathroom"),
        ("Consumer unit tripping during storms",
         "Tenant reported the consumer unit tripping repeatedly during recent storms.",
         "Under-stairs cupboard"),
        ("Outside light not working after dusk",
         "Tenant reported the porch light staying off despite the bulb having been replaced.",
         "Front porch"),
        ("Socket outlet scorched behind the sofa",
         "Tenant reported a burning smell and a visibly scorched double socket.",
         "Living room"),
    ],
    Trade.SCAFFOLDING: [
        ("Access scaffold required for chimney repointing",
         "Roofer advised chimney repointing cannot be reached safely off a ladder.",
         "Chimney stack, roof level"),
        ("Access scaffold for second-floor render repair",
         "Contractor advised second-floor render work needs a working platform.",
         "Second floor, side elevation"),
        ("Access platform for gutter replacement at height",
         "Contractor advised full gutter replacement needs continuous platform access.",
         "Roofline, full elevation"),
    ],
    Trade.OTHER: [
        ("Front door not closing flush against the frame",
         "Tenant reported the front door catching on the frame and not locking without force.",
         "Front entrance"),
        ("Fence panel blown down in the rear garden",
         "Tenant reported a fence panel blown flat after overnight winds.",
         "Rear garden boundary"),
        ("Kitchen cupboard door hinge broken",
         "Tenant reported a kitchen cupboard door hanging loose after the hinge sheared.",
         "Kitchen"),
        ("Loft hatch insulation flap missing",
         "Tenant reported the loft hatch letting a draught through with the flap missing.",
         "Landing, loft hatch"),
        ("Communal stairwell handrail loose",
         "Tenant reported the stairwell handrail coming away from its bracket.",
         "Communal stairwell"),
        ("Damp smell in the ground-floor storage cupboard",
         "Tenant reported a persistent musty smell in the understairs storage cupboard.",
         "Understairs cupboard"),
    ],
}

_SCOPES: dict[Trade, list[str]] = {
    Trade.ROOFING: [
        "Strip and renew lead flashing; make good internally.",
        "Re-bed and secure displaced ridge tiles.",
        "Re-fix guttering, renew brackets and clear downpipe.",
        "Trace and repair localised felt/tile defect causing ingress.",
    ],
    Trade.PLUMBING: [
        "Replace failed trap seal and dry out affected area.",
        "Clear blocked waste and re-seat fitting.",
        "Investigate pressure loss and service expansion vessel.",
        "Replace worn tap washer/cartridge and re-test.",
    ],
    Trade.ELECTRICAL: [
        "Fault-find circuit, replace damaged fitting and re-test.",
        "Isolate, replace faulty accessory and confirm RCD stability.",
        "Diagnose intermittent fault and renew affected wiring run.",
    ],
    Trade.SCAFFOLDING: [
        "Erect access scaffold to the affected elevation for safe working.",
        "Erect and hand over independent scaffold with edge protection.",
    ],
    Trade.OTHER: [
        "Ease and adjust fitting, realign and re-test operation.",
        "Replace damaged component and make good surrounding area.",
        "Investigate and remediate reported defect.",
    ],
}

# Base QUOTE ranges (pence) per trade, before the yearly multiplier below.
_COST_RANGE_PENCE: dict[Trade, tuple[int, int]] = {
    Trade.ROOFING: (80_000, 350_000),
    Trade.PLUMBING: (15_000, 90_000),
    Trade.ELECTRICAL: (20_000, 150_000),
    Trade.SCAFFOLDING: (40_000, 120_000),
    Trade.OTHER: (8_000, 45_000),
}
# A mild inflation-like drift so year-over-year spend is not flat.
_YEAR_COST_MULTIPLIER: dict[int, float] = {
    2021: 0.85, 2022: 0.90, 2023: 1.00, 2024: 1.05, 2025: 1.12, 2026: 1.18,
}

_ILLUSTRATION_FILES = ["ceiling-stain.jpg", "ceiling-damp.jpg", "roof-flashing.jpg"]

# --------------------------------------------------------------------------
# Contractor report text -- one write-up per attended appointment.
#
# Varied along two axes (trade x outcome), not one template repeated for
# every row: a roofer's completion note reads nothing like a plumber's, and
# a COMPLETED visit reads nothing like a NO_ACCESS one. Within each
# trade/outcome cell there are 2-4 alternatives, and completion reports get
# an independently-drawn closing remark appended (including a 1-in-4 chance
# of no closer at all), so the ~92 completion reports the seed produces
# don't collapse onto ~25 literal strings.
# --------------------------------------------------------------------------

_COMPLETION_REPORTS: dict[Trade, list[str]] = {
    Trade.ROOFING: [
        "Re-bedded and secured the displaced ridge tiles and checked the surrounding courses; two more that had worked loose were refixed at the same time.",
        "Stripped the failed lead flashing around the chimney and dressed in new lead, pointed in on completion. Loft space checked internally -- no residual damp visible.",
        "Cleared the blocked downpipe and re-fixed the gutter brackets that had pulled away from the fascia. Ran water through the full run to confirm free flow before leaving site.",
        "Traced the tile defect to a cracked felt underlay two courses up from the eaves; replaced the felt section and re-laid the tiles over it.",
        "Repaired the valley gutter join that was letting water track behind the lead and resealed it. Watched it clear under a hosepipe test with no overflow.",
    ],
    Trade.PLUMBING: [
        "Replaced the perished trap seal under the kitchen sink and dried out the cupboard base. Ran the tap for ten minutes with no further drips.",
        "Cleared the slow-draining waste with a manual rod and re-seated the basin trap; drainage now clears in seconds.",
        "Serviced the expansion vessel and repressurised the system to 1.3 bar; boiler holding pressure steady before leaving site.",
        "Fitted a new tap cartridge and tested under mains pressure -- no leak at the union.",
        "Renewed the cistern inlet valve and adjusted the float height; refills fully within thirty seconds now.",
    ],
    Trade.ELECTRICAL: [
        "Isolated the circuit, replaced the scorched double socket and confirmed insulation resistance before re-energising. RCD held stable through three test trips.",
        "Fault-found the hallway ring to a damaged cable run behind the skirting; renewed the section and re-tested with no further trips under load.",
        "Replaced the failed bathroom extractor fan unit and confirmed it starts correctly with the light switch.",
        "Diagnosed a loose neutral in the kitchen light fitting; renewed the connection and confirmed stable operation over a ten-minute test.",
    ],
    Trade.SCAFFOLDING: [
        "Erected independent scaffold to the affected elevation with edge protection and toe boards; handed over to the follow-on trade the same day.",
        "Scaffold erected to full working height with guard-rail protection throughout; inspected and tagged before handover.",
    ],
    Trade.OTHER: [
        "Eased and adjusted the door on its hinges and planed the binding edge; closes and locks flush now.",
        "Replaced the sheared cupboard hinge and reset the door; opens and closes without catching.",
        "Refitted the loose handrail bracket with longer fixings into solid blockwork.",
        "Replaced the missing loft hatch insulation flap; no draught noticeable at the hatch on completion.",
    ],
}

_COMPLETION_CLOSERS: list[str] = [
    "",
    "",
    " Tenant was present at the end of the visit and confirmed happy with the result.",
    " Work area left clean and tidy on completion.",
    " No further action expected on this repair.",
]

_NO_ACCESS_REPORTS: list[str] = [
    "Attended at the agreed time but got no answer at the property; no access arranged and no key held for this visit. Please confirm access before rebooking.",
    "Called ahead as agreed and knocked twice on arrival, but the property appeared unoccupied. No access obtained -- will need a further appointment.",
    "On site at the booked slot; a neighbour said the tenant had gone out. No one answered the door, so no work could be started today.",
    "Waited fifteen minutes past the appointment time with no response from the property. Logging as a missed-access visit; please rebook and confirm the tenant will be in.",
]

_FAILED_REPORTS: dict[Trade, list[str]] = {
    Trade.ROOFING: [
        "Got on the roof and started the repair, but the replacement lead brought was the wrong gauge for this run; stood down until the correct material is sourced.",
        "Began the repair but found the underlying timber more extensively rotted than the original report described; work paused pending a revised scope.",
    ],
    Trade.PLUMBING: [
        "Started the job but the replacement part needed is out of stock at the merchant; it has been ordered and a return visit will be booked once it arrives.",
        "Isolated the leak but found the pipework behind it in worse condition than expected; a further visit with additional materials is needed to finish safely.",
    ],
    Trade.ELECTRICAL: [
        "Began fault-finding and traced the problem further along the circuit than expected; isolating it safely needs a second visit with the right test equipment.",
        "Started the repair but discovered the fault also affects an adjoining circuit; work paused rather than leave the property in an unsafe state overnight.",
    ],
    Trade.SCAFFOLDING: [
        "Arrived to erect the scaffold but ground conditions at the base-plate positions were unsuitable; work paused pending a revised base layout.",
        "Started the erection but one delivery of standards did not arrive with the load; the structure could not be completed safely today.",
    ],
    Trade.OTHER: [
        "Started the job but the replacement part on hand did not match the fitting; a further visit is needed once the correct part is sourced.",
        "Began the repair but found additional damage once the fitting was removed; work paused to agree a revised scope before continuing.",
    ],
}

_BLOCKED_REPORTS: dict[Trade, list[str]] = {
    Trade.ROOFING: [
        "Inspected the chimney and confirmed the repointing cannot be reached safely from a ladder; work cannot proceed until access scaffold is erected.",
        "On site inspection, the pitch and height here rule out ladder access for this repair; a height-access contractor with scaffold is needed first.",
    ],
    Trade.PLUMBING: [
        "Traced the leak to a joint behind the boxed-in stack; cannot open that section up without the water authority isolating supply at the boundary first.",
    ],
    Trade.ELECTRICAL: [
        "Found the fault upstream of the consumer unit; this needs the distribution network operator to isolate the supply before it is safe to open up.",
    ],
    Trade.SCAFFOLDING: [
        "Surveyed the elevation but the ground here will not take standard base plates; needs a scaffold design review before erection can proceed.",
    ],
    Trade.OTHER: [
        "On inspection this repair depends on work at height that has not been made safe yet; standing down until that is arranged.",
    ],
}

_UNKNOWN_REPORTS: list[str] = [
    "Attended site; the outcome of this visit was not clearly recorded at the time. Following up to confirm status before closing out.",
]


def _report_text(rng: random.Random, *, trade: Trade, outcome: VisitOutcome) -> str:
    if outcome == VisitOutcome.COMPLETED:
        pool = _COMPLETION_REPORTS.get(trade, _COMPLETION_REPORTS[Trade.OTHER])
        return rng.choice(pool) + rng.choice(_COMPLETION_CLOSERS)
    if outcome == VisitOutcome.NO_ACCESS:
        return rng.choice(_NO_ACCESS_REPORTS)
    if outcome == VisitOutcome.FAILED:
        pool = _FAILED_REPORTS.get(trade, _FAILED_REPORTS[Trade.OTHER])
        return rng.choice(pool)
    if outcome == VisitOutcome.BLOCKED:
        pool = _BLOCKED_REPORTS.get(trade, _BLOCKED_REPORTS[Trade.OTHER])
        return rng.choice(pool)
    return rng.choice(_UNKNOWN_REPORTS)


def _add_reports(rng: random.Random, case: ArchiveCase) -> None:
    """One report per appointment, timestamped at-or-after that visit's
    `end_at` and strictly before `case.archived_closed_at` (must already be
    set -- call this after the appointments loop and the closure-delay
    calculation below). `archived_closed_at` is always `latest_end +
    closure_delay` with `closure_delay >= 2 hours`, and every appointment's
    `end_at <= latest_end`, so the write-up window (10 minutes to 4 hours
    after the visit) always fits before closure with room to spare.

    Report flavour is keyed off *that appointment's own work order's*
    trade (`wo.trade`), not a single case-wide trade: every case used to
    have one trade uniformly, so this was equivalent to a case-level
    parameter, but a dependency-derived prerequisite work order (see
    `_inject_dependency_if_applicable`) can carry a different trade
    (SCAFFOLDING) from the rest of the case -- its report must read like a
    scaffold report, not a mislabelled roofing/plumbing one."""
    reports: list[ArchiveContractorReport] = []
    closed_at = case.archived_closed_at
    for i, appt in enumerate(case.appointments):
        wo = case.work_orders[appt.work_order_index]
        text = _report_text(rng, trade=wo.trade, outcome=appt.visit_outcome)

        headroom = max(int((closed_at - appt.end_at).total_seconds()) - 60, 60)
        observed_offset = min(rng.randint(600, 4 * 3600), headroom)
        observed_at = appt.end_at + timedelta(seconds=observed_offset)

        remaining = max(int((closed_at - observed_at).total_seconds()) - 30, 0)
        received_offset = rng.randint(300, 3 * 3600) if remaining > 0 else 0
        received_at = observed_at + timedelta(seconds=min(received_offset, remaining))

        reports.append(
            ArchiveContractorReport(
                id=stable_id(f"archive:report:{case.label}:{i}"),
                appointment_index=i,
                work_order_index=appt.work_order_index,
                contractor_key=wo.contractor_key,
                text=text,
                observed_at=observed_at,
                received_at=received_at,
            )
        )
    case.reports = reports


_NOTE_AUTHORS = ["operator", "archive-import"]
_NOTE_TEMPLATES = [
    "Contractor confirmed access arranged directly with the tenant for this visit.",
    "Quote reviewed against prior invoices for this property before approval.",
    "Tenant chased once by phone; no further contact needed after the visit.",
    "Filed under the property's historical maintenance record at handover.",
    "Cross-checked against the landlord's own maintenance log for this period.",
]

_CANCEL_NOTE_TEMPLATES = [
    "Tenant vacated the property before this work could be scheduled; case closed without further action.",
    "Issue found to be a tenant-responsibility matter on inspection; case closed, no landlord works required.",
    "Duplicate of an existing case for the same defect; closed to avoid double-booking a contractor.",
]


# Relative monthly likelihood that a repair of each trade is *reported*,
# January to December. Uniform dates made the charts read as synthetic on
# sight -- and worse, backwards: roofing peaked in July, which is the
# opposite of when roofs fail. These are the obvious physical seasons,
# not fitted data, and they only shape which month a case lands in.
_TRADE_SEASONALITY: dict[Trade, tuple[int, ...]] = {
    # Storms and driving rain: heavy in late autumn and winter.
    Trade.ROOFING: (16, 14, 11, 7, 5, 4, 4, 5, 8, 12, 16, 18),
    # Burst and frozen pipes cluster in the cold months; a quieter summer
    # baseline of ordinary leaks and blockages never goes away.
    Trade.PLUMBING: (15, 14, 11, 8, 6, 5, 5, 6, 7, 10, 14, 17),
    # Mostly aseasonal. A mild winter lift: more hours of lighting and
    # heating load, and damp finding its way into fittings.
    Trade.ELECTRICAL: (11, 10, 9, 8, 7, 7, 7, 7, 8, 9, 11, 12),
    # Follows the work it enables, so it tracks roofing loosely.
    Trade.SCAFFOLDING: (14, 12, 11, 8, 6, 5, 5, 6, 8, 11, 14, 15),
}
_FLAT_SEASONALITY = (1,) * 12


def _pick_date_in_year(rng: random.Random, year: int, trade: Trade | None = None) -> datetime:
    """A reporting date inside `year`, weighted by the trade's season.

    The month is drawn from the trade's weights and the position within
    that month is uniform, so the shape is seasonal without any case
    landing on a suspiciously round date. 2026 is truncated at
    `_YEAR_2026_LATEST_CREATED` because the archive must stay in the
    past; months wholly after that cutoff are dropped from the draw
    rather than silently clamped onto the boundary, which would pile
    cases onto a single timestamp.
    """
    latest = _YEAR_2026_LATEST_CREATED if year == 2026 else datetime(year, 12, 31, 23, 0, 0, tzinfo=timezone.utc)
    weights = _TRADE_SEASONALITY.get(trade, _FLAT_SEASONALITY) if trade is not None else _FLAT_SEASONALITY

    months = [m for m in range(1, 13) if datetime(year, m, 1, tzinfo=timezone.utc) <= latest]
    month = rng.choices(months, weights=[weights[m - 1] for m in months])[0]

    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    month_end = (
        datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    )
    month_end = min(month_end, latest)
    span_seconds = max(int((month_end - month_start).total_seconds()), 3600)
    return month_start + timedelta(seconds=rng.randint(0, span_seconds))


def _build_properties() -> list[ArchiveProperty]:
    return [
        ArchiveProperty(
            id=stable_id(f"archive:property:{spec['key']}"),
            key=spec["key"],
            address_line=spec["address_line"],
            postcode=spec["postcode"],
            landlord_reference=spec["landlord_reference"],
            roof_responsibility=spec["roof_responsibility"],
            build_year=spec["build_year"],
            property_type=spec["property_type"],
            bedrooms=spec["bedrooms"],
            photo_key=spec["photo_key"],
            access_notes=spec["access_notes"],
        )
        for spec in PROPERTY_SPECS
    ]


def _build_tenants() -> list[ArchiveTenant]:
    return [
        ArchiveTenant(
            id=stable_id(f"archive:tenant:{spec['key']}"),
            property_key=spec["key"],
            display_name=spec["tenant_name"],
        )
        for spec in PROPERTY_SPECS
    ]


def _build_contractors() -> list[ArchiveContractor]:
    return [
        ArchiveContractor(
            id=stable_id(f"archive:contractor:{spec['key']}"),
            key=spec["key"],
            display_name=spec["display_name"],
            trades=[spec["trade"].value],
            service_postcodes=list(spec["postcodes"]),
            verification_note=(
                "Archival record only -- imported by the synthetic history batch. "
                "Not vetted under the current approval workflow and never bookable."
            ),
        )
        for spec in CONTRACTOR_SPECS
    ]


def _contractor_key_for_trade(rng: random.Random, trade: Trade) -> str:
    options = _TRADE_TO_CONTRACTOR_KEYS[trade]
    return options[rng.randrange(len(options))] if len(options) > 1 else options[0]


def _cost_amount(rng: random.Random, trade: Trade, year: int, *, factor: float) -> int:
    lo, hi = _COST_RANGE_PENCE[trade]
    base = rng.randint(lo, hi)
    scaled = base * _YEAR_COST_MULTIPLIER.get(year, 1.0) * factor
    return max(int(round(scaled)), 1000)


# --------------------------------------------------------------------------
# Event log + coordinator decision history.
#
# Everything below derives a CaseEvent/OrchestrationRun narrative from a
# case's *already-built* structure (work orders, appointments and their
# real visit outcomes, the contractor reports just written, any dependency
# injected above, and archived_closed_at) -- it never invents a fact that
# isn't already implied by that structure. Real ids throughout (every
# work order/appointment/report/case id is already a concrete stable_id
# string by the time this runs), so causation_event_id/trigger_event_id
# are plain id references, not indices importer.py has to resolve later.
# --------------------------------------------------------------------------


def _contractor_id(key: str) -> str:
    """Mirrors `_build_contractors`'s id formula exactly -- a pure function
    of the contractor key, so this can be computed without threading the
    whole ArchiveDataset through case-building."""
    return stable_id(f"archive:contractor:{key}")


def _issue_id(label: str) -> str:
    """Mirrors importer.py's `stable_id(f"archive:issue:{case.label}")`
    exactly -- the RepairIssue a ResolveCase/RequestConfirmation action
    must reference."""
    return stable_id(f"archive:issue:{label}")


def _no_hazard_risk(urgency: str, assessed_at: datetime) -> dict:
    """A plain dict matching app.schemas.RiskAssessment, always hazard-free:
    every archival case closes as RESOLVED/CANCELLED through ordinary
    handling, never through the hazard-escalation path, so an archival
    ApplyTriage action's risk answers must never trip policy.is_hazard.
    importer.py validates this against the real schema before writing it."""
    return {
        "urgency": urgency,
        "gas": "NO",
        "fire": "NO",
        "water_near_electrics": "NO",
        "structural_danger": "NO",
        "uncontrolled_flood": "NO",
        "vulnerability_concern": "NO",
        "evidence_refs": [],
        "uncertainties": [],
        "assessed_at": assessed_at,
    }


def _clipped_nudge(rng: random.Random, base: datetime, ceiling: datetime, lo_seconds: int, hi_seconds: int) -> datetime:
    """`base` plus a random offset, clipped so the result always stays
    strictly before `ceiling` -- the same clipping technique `_add_reports`
    already uses (headroom = max(..., floor)) to keep a synthetic
    timestamp inside its real window however little of that window is
    actually left. Every caller here has multi-hour real headroom by
    construction (archived_closed_at is always latest_end + a closure
    delay of at least 2 hours), so the sub-2-second fallback below is a
    defensive floor, not the normal path."""
    span = int((ceiling - base).total_seconds())
    if span < 2:
        return base + timedelta(seconds=1)
    hi = max(1, min(hi_seconds, span - 1))
    lo = max(1, min(lo_seconds, hi))
    return base + timedelta(seconds=rng.randint(lo, hi))


def _tighten_run_finish(
    rng: random.Random, started: datetime, spread_finish: datetime
) -> datetime:
    """A coordinator round's finish, seconds after its start -- not days.

    `_time_points` spreads its points across whatever headroom exists so
    they stay ordered and inside the ceiling. That is right for the gap
    BETWEEN events (a tenant really can take two days to confirm a
    repair) and wrong for the gap between one run's own started_at and
    finished_at, which is a model call. On a case that closed weeks after
    its last completion the spread produced runs whose duration rendered
    as "took 192381.0s" -- a 53-hour thought. Pull the finish back to a
    plausible few seconds, never past the point the spread had allotted,
    so ordering against everything after it is preserved.
    """
    span = int((spread_finish - started).total_seconds())
    if span <= 1:
        return spread_finish
    return started + timedelta(seconds=rng.randint(1, min(span, 45)))


def _time_points(
    rng: random.Random, start: datetime, ceiling: datetime, count: int, *, reserve_seconds: int = 0,
) -> list[datetime]:
    """`count` strictly increasing timestamps, each strictly between the
    previous one (or `start`) and `ceiling`.

    Unlike chaining independent `_clipped_nudge` calls (each one free to
    reach for up to its own `hi_seconds`), this divides whatever headroom
    actually exists into `count` shares up front, so a sequence of
    decision timestamps can never compound past `ceiling` just because
    the true remaining headroom is much smaller than any single nudge's
    requested range. `_add_reports`'s own floor logic can leave as little
    as ~30 seconds between the last report and case closure (its
    `headroom`/`remaining` clamps both bottom out independently), and that
    is exactly the case this function has to still get right.

    `reserve_seconds` holds back that much time before `ceiling` for a
    caller who knows more points still need to land after this batch (the
    per-work-order completion chain reserves room for the case-level
    confirm/resolve chain that always follows the *last* one to finish).
    """
    effective_ceiling = ceiling - timedelta(seconds=reserve_seconds)
    if int((effective_ceiling - start).total_seconds()) < count + 1:
        effective_ceiling = min(start + timedelta(seconds=count + 1), ceiling - timedelta(seconds=1))

    points: list[datetime] = []
    cursor = start
    for i in range(count):
        remaining_buckets = count - i
        remaining_span = max(int((effective_ceiling - cursor).total_seconds()), remaining_buckets + 1)
        max_step = max(remaining_span - remaining_buckets, 1)
        bucket_target = max(remaining_span // (remaining_buckets + 1), 1)
        hi = max(1, min(bucket_target, max_step))
        step = rng.randint(1, hi)
        cursor = cursor + timedelta(seconds=step)
        points.append(cursor)
    return points


# Real tool names from app/agents/read_tools.py -- app.agents.coordinator
# registers exactly these five (coordinator.py: agent.tool(...) x5). An
# archival run's tool_calls must name tools that actually exist, the same
# "no fake live traces" rule that governs model_id.
_TOOLS_FOR_TRIAGE = ["list_case_events"]
_TOOLS_FOR_SCHEDULE = ["list_case_events", "find_appointment_options"]
_TOOLS_FOR_ACCEPT_REPORT = ["read_report"]
_TOOLS_FOR_ADD_PREREQUISITE = ["read_report", "list_case_events"]
_TOOLS_FOR_REQUEST_CONFIRMATION = ["list_case_events"]
_TOOLS_FOR_RESOLVE = ["list_case_events"]


def _deduplicate_occurred_at(events: list[ArchiveCaseEvent]) -> None:
    """Breaks any exact-timestamp tie between two already-sorted events by
    nudging the later one forward a single second. Two independently
    drawn real timestamps (one work order's created_at, a different
    appointment's end_at, ...) landing on the identical second is rare
    but not impossible across ~700 generated timestamps -- CaseEvent.seq
    is what actually orders same-case history on screen, but "timestamps
    must be strictly ordered" means no two events in the same case may
    share one. In-place; assumes `events` is already sorted."""
    for i in range(1, len(events)):
        if events[i].occurred_at <= events[i - 1].occurred_at:
            events[i].occurred_at = events[i - 1].occurred_at + timedelta(seconds=1)
            events[i].received_at = events[i].occurred_at


def _inject_dependency_if_applicable(rng: random.Random, case: ArchiveCase) -> ArchiveDependency | None:
    """If the appointments loop above already rolled a BLOCKED outcome (an
    existing possibility on any retried visit -- this function does not
    decide it), gives it a real prerequisite: a genuine access work order
    using the one access trade this archive's contractor roster actually
    has (SCAFFOLDING/scaffolder_a), which must be attended and completed
    before the blocked work order's retry can go ahead. At most one per
    case: `visits` only ever inserts a single retry, so there is at most
    one BLOCKED appointment to satisfy.

    Structural, not textual: without this, DEPENDENCY_DISCOVERED /
    DEPENDENCY_SATISFIED (_build_resolved_case_history, below) would be
    events about a dependency that doesn't actually exist anywhere in the
    imported database -- exactly the "invented independently of the
    structure" outcome this generator exists to avoid.
    """
    blocked_index = next(
        (i for i, a in enumerate(case.appointments) if a.visit_outcome == VisitOutcome.BLOCKED), None
    )
    if blocked_index is None:
        return None
    blocked_appt = case.appointments[blocked_index]
    dependent_wo_index = blocked_appt.work_order_index
    retry_index = next(
        i for i, a in enumerate(case.appointments)
        if a.work_order_index == dependent_wo_index and a.attempt_number == blocked_appt.attempt_number + 1
    )
    retry_appt = case.appointments[retry_index]

    year = case.created_at.year
    scaffold_index = len(case.work_orders)
    scaffold_created = blocked_appt.end_at + timedelta(hours=rng.randint(6, 48))
    scaffold_quote = _cost_amount(rng, Trade.SCAFFOLDING, year, factor=0.5)
    scaffold_wo = ArchiveWorkOrder(
        id=stable_id(f"archive:workorder:{case.label}:dep:{scaffold_index}"),
        kind=WorkOrderKind.SCAFFOLD_INSTALL,
        trade=Trade.SCAFFOLDING,
        scope="Erect access equipment so the blocked repair can proceed safely.",
        status=WorkOrderStatus.COMPLETED,
        contractor_key="scaffolder_a",
        quote_pence=scaffold_quote,
        approved_limit_pence=scaffold_quote,
        created_at=scaffold_created,
        updated_at=scaffold_created,
    )
    case.work_orders.append(scaffold_wo)

    scaffold_start = scaffold_created + timedelta(days=rng.randint(2, 6), hours=rng.randint(0, 12))
    scaffold_end = scaffold_start + timedelta(hours=rng.randint(2, 5))
    scaffold_appt_index = len(case.appointments)
    case.appointments.append(
        ArchiveAppointment(
            id=stable_id(f"archive:appointment:{case.label}:dep:{scaffold_index}"),
            action_id=stable_id(f"archive:action:{case.label}:dep:{scaffold_index}"),
            work_order_index=scaffold_index,
            contractor_key="scaffolder_a",
            slot_id=f"archive-slot-{case.label}-dep-{scaffold_index}",
            start_at=scaffold_start,
            end_at=scaffold_end,
            attempt_number=1,
            visit_outcome=VisitOutcome.COMPLETED,
            action_idempotency_key=f"archive:{case.label}:booking:dep:{scaffold_index}",
            action_created_at=scaffold_created,
            action_updated_at=scaffold_end,
            action_expected_case_version=1,
        )
    )
    scaffold_wo.updated_at = max(scaffold_wo.updated_at, scaffold_end)

    # The retry can only go ahead once the prerequisite is actually done --
    # re-time it after the scaffold visit instead of wherever the main
    # appointments loop happened to place it.
    duration = retry_appt.end_at - retry_appt.start_at
    new_start = scaffold_end + timedelta(days=rng.randint(2, 8), hours=rng.randint(0, 12))
    retry_appt.start_at = new_start
    retry_appt.end_at = new_start + duration

    dependency = ArchiveDependency(
        id=stable_id(f"archive:dependency:{case.label}"),
        prerequisite_work_order_index=scaffold_index,
        dependent_work_order_index=dependent_wo_index,
        reason="The blocked visit reported that this repair cannot proceed safely without access equipment in place first.",
        discovered_from_appointment_index=blocked_index,
        satisfied_by_appointment_index=scaffold_appt_index,
    )
    case.dependencies.append(dependency)
    return dependency


def _build_resolved_case_history(rng: random.Random, case: ArchiveCase, *, dependency: ArchiveDependency | None) -> None:
    events: list[ArchiveCaseEvent] = []
    runs: list[ArchiveOrchestrationRun] = []
    counters = {"e": 0, "r": 0}

    def add_event(
        type_: str, occurred_at: datetime, actor_type: str, actor_id: str,
        source_key: str, correlation_id: str, *, causation_event_id: str | None = None, payload: dict | None = None,
    ) -> str:
        EventType(type_)  # raises ValueError on a typo'd event type at generation time, not at read time
        eid = stable_id(f"archive:event:{case.label}:{counters['e']}")
        counters["e"] += 1
        events.append(
            ArchiveCaseEvent(
                id=eid, type=type_, occurred_at=occurred_at, received_at=occurred_at,
                actor_type=actor_type, actor_id=actor_id, source_event_key=source_key,
                correlation_id=correlation_id, causation_event_id=causation_event_id, payload=payload or {},
            )
        )
        return eid

    def add_run(
        trigger_id: str, started_at: datetime, finished_at: datetime,
        decision_summary: str, action: dict, tool_names: list[str],
    ) -> str:
        rid = stable_id(f"archive:run:{case.label}:{counters['r']}")
        counters["r"] += 1
        runs.append(
            ArchiveOrchestrationRun(
                id=rid, trigger_event_id=trigger_id, started_at=started_at, finished_at=finished_at,
                decision_summary=decision_summary[:500], action=action, tool_names=tool_names,
            )
        )
        return rid

    comm_id = stable_id(f"archive:comm:{case.label}:intake")
    case_created_id = add_event(
        "CASE_CREATED", case.created_at, "OPERATOR", "operator",
        f"archive:intake:{case.label}", comm_id, payload={"communication_id": comm_id},
    )

    dependency_wo_indices = {dependency.prerequisite_work_order_index} if dependency is not None else set()
    primary_indices = [i for i in range(len(case.work_orders)) if i not in dependency_wo_indices]

    completion_events: dict[int, str] = {}
    completion_times: dict[int, datetime] = {}

    for i in primary_indices:
        wo = case.work_orders[i]

        triage_started = _clipped_nudge(rng, case.created_at, wo.created_at, 30, 600)
        triage_finished = _clipped_nudge(rng, triage_started, wo.created_at, 5, 300)
        add_run(
            case_created_id, triage_started, triage_finished, f"Triage: {wo.scope}",
            {
                "kind": "APPLY_TRIAGE", "risk": _no_hazard_risk(case.urgency, triage_finished),
                "issue_description": case.description, "suggested_trade": wo.trade.value, "scope": wo.scope,
            },
            _TOOLS_FOR_TRIAGE,
        )
        wo_created_id = add_event(
            "WORK_ORDER_CREATED", wo.created_at, "COORDINATOR", MODEL_ID,
            f"archive:triage:{case.label}:{i}", case_created_id,
            causation_event_id=case_created_id, payload={"scope": wo.scope},
        )

        legs = sorted(
            ((pos, a) for pos, a in enumerate(case.appointments) if a.work_order_index == i),
            key=lambda t: t[1].attempt_number,
        )
        next_trigger_id, next_trigger_time = wo_created_id, wo.created_at

        for appt_pos, appt in legs:
            report = case.reports[appt_pos]

            run_started = _clipped_nudge(rng, next_trigger_time, appt.start_at, 30, 600)
            run_finished = _clipped_nudge(rng, run_started, appt.start_at, 5, 300)
            confirmed_at = _clipped_nudge(rng, run_finished, appt.start_at, 5, 900)
            schedule_summary = (
                f"Booking a visit for: {wo.scope}" if appt.attempt_number == 1
                else f"Rebooking after the previous visit could not complete: {wo.scope}"
            )
            add_run(
                next_trigger_id, run_started, run_finished, schedule_summary,
                {
                    "kind": "SCHEDULE_VISIT", "work_order_id": wo.id,
                    "contractor_id": _contractor_id(appt.contractor_key), "slot_id": appt.slot_id,
                    "tenant_availability_ids": [],
                },
                _TOOLS_FOR_SCHEDULE,
            )
            add_event(
                "APPOINTMENT_CONFIRMED", confirmed_at, "EXECUTOR", "executor",
                f"archive:booking:{appt.id}:confirmed", appt.action_id,
                payload={"appointment_id": appt.id, "work_order_id": wo.id},
            )
            add_event(
                "APPOINTMENT_WINDOW_ENDED", appt.end_at, "SYSTEM", "appointment-window-timer",
                f"archive:window-ended:{appt.id}", appt.id,
                payload={"appointment_id": appt.id, "work_order_id": wo.id},
            )
            report_event_id = add_event(
                "CONTRACTOR_REPORT_RECEIVED", report.received_at, "OPERATOR", "operator",
                f"archive:report:{report.id}", report.id,
                payload={"report_id": report.id, "work_order_id": wo.id},
            )

            if appt.visit_outcome == VisitOutcome.COMPLETED:
                # reserve_seconds: this may be the work order that finishes
                # *last* in the whole case, in which case the case-level
                # confirm/resolve chain below still has to fit after
                # `completed_at` and before archived_closed_at.
                accept_started, accept_spread, completed_at = _time_points(
                    rng, report.received_at, case.archived_closed_at, 3, reserve_seconds=10,
                )
                accept_finished = _tighten_run_finish(rng, accept_started, accept_spread)
                add_run(
                    report_event_id, accept_started, accept_finished, f"Accepting completed work: {wo.scope}",
                    {"kind": "ACCEPT_REPORT", "report_id": report.id, "outcome": "COMPLETED", "completion_evidence_refs": []},
                    _TOOLS_FOR_ACCEPT_REPORT,
                )
                completed_id = add_event(
                    "WORK_ORDER_COMPLETED", completed_at, "COORDINATOR", MODEL_ID,
                    f"archive:report:{report.id}:accept", report_event_id,
                    causation_event_id=report_event_id, payload={"work_order_id": wo.id, "report_id": report.id},
                )
                completion_events[i] = completed_id
                completion_times[i] = completed_at
                break  # COMPLETED is always this work order's last leg

            if appt.visit_outcome == VisitOutcome.BLOCKED:
                assert dependency is not None and dependency.dependent_work_order_index == i
                addp_started = _clipped_nudge(rng, report.received_at, case.archived_closed_at, 30, 600)
                addp_finished = _clipped_nudge(rng, addp_started, case.archived_closed_at, 5, 300)
                scaffold_wo = case.work_orders[dependency.prerequisite_work_order_index]
                add_run(
                    report_event_id, addp_started, addp_finished,
                    "Access blocked; a prerequisite work order is required first.",
                    {
                        "kind": "ADD_PREREQUISITE", "report_id": report.id, "blocked_work_order_id": wo.id,
                        "prerequisite_trade": scaffold_wo.trade.value, "prerequisite_kind": scaffold_wo.kind.value,
                        "prerequisite_scope": scaffold_wo.scope, "reason": dependency.reason,
                    },
                    _TOOLS_FOR_ADD_PREREQUISITE,
                )
                discovered_at = _clipped_nudge(rng, addp_finished, case.archived_closed_at, 1, 300)
                discovered_id = add_event(
                    "DEPENDENCY_DISCOVERED", discovered_at, "COORDINATOR", MODEL_ID,
                    f"archive:report:{report.id}:prerequisite", report_event_id,
                    causation_event_id=report_event_id,
                    payload={
                        "report_id": report.id, "prerequisite_work_order_id": scaffold_wo.id,
                        "blocked_work_order_id": wo.id, "removal_work_order_id": None,
                    },
                )

                scaffold_appt = case.appointments[dependency.satisfied_by_appointment_index]
                scaffold_report = case.reports[dependency.satisfied_by_appointment_index]
                s_run_started = _clipped_nudge(rng, discovered_at, scaffold_appt.start_at, 30, 600)
                s_run_finished = _clipped_nudge(rng, s_run_started, scaffold_appt.start_at, 5, 300)
                s_confirmed_at = _clipped_nudge(rng, s_run_finished, scaffold_appt.start_at, 5, 900)
                add_run(
                    discovered_id, s_run_started, s_run_finished, f"Booking a visit for: {scaffold_wo.scope}",
                    {
                        "kind": "SCHEDULE_VISIT", "work_order_id": scaffold_wo.id,
                        "contractor_id": _contractor_id(scaffold_appt.contractor_key),
                        "slot_id": scaffold_appt.slot_id, "tenant_availability_ids": [],
                    },
                    _TOOLS_FOR_SCHEDULE,
                )
                add_event(
                    "APPOINTMENT_CONFIRMED", s_confirmed_at, "EXECUTOR", "executor",
                    f"archive:booking:{scaffold_appt.id}:confirmed", scaffold_appt.action_id,
                    payload={"appointment_id": scaffold_appt.id, "work_order_id": scaffold_wo.id},
                )
                add_event(
                    "APPOINTMENT_WINDOW_ENDED", scaffold_appt.end_at, "SYSTEM", "appointment-window-timer",
                    f"archive:window-ended:{scaffold_appt.id}", scaffold_appt.id,
                    payload={"appointment_id": scaffold_appt.id, "work_order_id": scaffold_wo.id},
                )
                s_report_event_id = add_event(
                    "CONTRACTOR_REPORT_RECEIVED", scaffold_report.received_at, "OPERATOR", "operator",
                    f"archive:report:{scaffold_report.id}", scaffold_report.id,
                    payload={"report_id": scaffold_report.id, "work_order_id": scaffold_wo.id},
                )

                s_accept_started = _clipped_nudge(rng, scaffold_report.received_at, case.archived_closed_at, 30, 600)
                s_accept_finished = _clipped_nudge(rng, s_accept_started, case.archived_closed_at, 5, 300)
                add_run(
                    s_report_event_id, s_accept_started, s_accept_finished,
                    f"Accepting completed work: {scaffold_wo.scope}",
                    {"kind": "ACCEPT_REPORT", "report_id": scaffold_report.id, "outcome": "COMPLETED", "completion_evidence_refs": []},
                    _TOOLS_FOR_ACCEPT_REPORT,
                )
                s_completed_at = _clipped_nudge(rng, s_accept_finished, case.archived_closed_at, 1, 200)
                s_completed_id = add_event(
                    "WORK_ORDER_COMPLETED", s_completed_at, "COORDINATOR", MODEL_ID,
                    f"archive:report:{scaffold_report.id}:accept", s_report_event_id,
                    causation_event_id=s_report_event_id,
                    payload={"work_order_id": scaffold_wo.id, "report_id": scaffold_report.id},
                )
                satisfied_at = _clipped_nudge(rng, s_completed_at, case.archived_closed_at, 1, 200)
                satisfied_id = add_event(
                    "DEPENDENCY_SATISFIED", satisfied_at, "COORDINATOR", MODEL_ID,
                    f"archive:dependency:{dependency.id}:satisfied", s_report_event_id,
                    causation_event_id=s_completed_id,
                    payload={"dependency_id": dependency.id, "dependent_work_order_id": wo.id},
                )
                dependency.satisfied_at = satisfied_at

                next_trigger_id, next_trigger_time = satisfied_id, satisfied_at
                continue  # the retry leg of this same work order follows

            # NO_ACCESS / FAILED: accept_report's real else-branch appends no
            # CaseEvent at all -- the work order just goes back to READY and
            # a retry is booked off the same report event.
            accept_started = _clipped_nudge(rng, report.received_at, case.archived_closed_at, 30, 600)
            accept_finished = _clipped_nudge(rng, accept_started, case.archived_closed_at, 5, 300)
            add_run(
                report_event_id, accept_started, accept_finished,
                f"Visit could not complete ({appt.visit_outcome.value.replace('_', ' ').lower()}); rebooking.",
                {"kind": "ACCEPT_REPORT", "report_id": report.id, "outcome": appt.visit_outcome.value, "completion_evidence_refs": []},
                _TOOLS_FOR_ACCEPT_REPORT,
            )
            next_trigger_id, next_trigger_time = report_event_id, report.received_at

    last_wo_index = max(completion_times, key=lambda k: completion_times[k])
    last_completion_id = completion_events[last_wo_index]
    last_completion_time = completion_times[last_wo_index]

    rc_started, rc_spread, confirmation_at, resolve_started, resolve_spread = _time_points(
        rng, last_completion_time, case.archived_closed_at, 5,
    )
    rc_finished = _tighten_run_finish(rng, rc_started, rc_spread)
    resolve_finished = _tighten_run_finish(rng, resolve_started, resolve_spread)
    add_run(
        last_completion_id, rc_started, rc_finished,
        "Asking the tenant to confirm the repair resolved the issue.",
        {"kind": "REQUEST_CONFIRMATION", "issue_id": _issue_id(case.label), "questions": ["Can you confirm the repair resolved the issue?"]},
        _TOOLS_FOR_REQUEST_CONFIRMATION,
    )
    confirmation_comm_id = stable_id(f"archive:comm:{case.label}:confirmation")
    confirmation_id = add_event(
        "TENANT_CONFIRMATION_RECEIVED", confirmation_at, "OPERATOR", "operator",
        f"archive:observations:{case.label}:confirmation", confirmation_comm_id,
        payload={"communication_id": confirmation_comm_id, "confirmed": True},
    )

    add_run(
        confirmation_id, resolve_started, resolve_finished,
        "Resolving the case: tenant confirmed the repair.",
        {"kind": "RESOLVE_CASE", "issue_id": _issue_id(case.label), "confirmation_event_id": confirmation_id},
        _TOOLS_FOR_RESOLVE,
    )
    # Hard constraint: app.analytics.property_history_items reads this
    # event's occurred_at as the case's resolution date, so it must equal
    # archived_closed_at exactly or the same case shows two different
    # closure dates on two screens.
    add_event(
        "CASE_RESOLVED", case.archived_closed_at, "COORDINATOR", MODEL_ID,
        f"archive:resolve:{case.label}", confirmation_id,
        causation_event_id=confirmation_id, payload={"issue_id": _issue_id(case.label)},
    )

    case.events = sorted(events, key=lambda e: e.occurred_at)
    _deduplicate_occurred_at(case.events)
    case.runs = sorted(runs, key=lambda r: r.started_at)


def _build_cancelled_case_history(rng: random.Random, case: ArchiveCase) -> None:
    """A cancelled case never had a visit -- there is no appointment/report
    cycle to derive events from, only intake, triage and the cancellation
    itself (matches how app/api/cases.py's own cancel endpoint works: a
    direct operator action, not a coordinator decision)."""
    events: list[ArchiveCaseEvent] = []
    runs: list[ArchiveOrchestrationRun] = []
    counters = {"e": 0, "r": 0}

    def add_event(
        type_: str, occurred_at: datetime, actor_type: str, actor_id: str,
        source_key: str, correlation_id: str, *, causation_event_id: str | None = None, payload: dict | None = None,
    ) -> str:
        EventType(type_)  # raises ValueError on a typo'd event type at generation time, not at read time
        eid = stable_id(f"archive:event:{case.label}:{counters['e']}")
        counters["e"] += 1
        events.append(
            ArchiveCaseEvent(
                id=eid, type=type_, occurred_at=occurred_at, received_at=occurred_at,
                actor_type=actor_type, actor_id=actor_id, source_event_key=source_key,
                correlation_id=correlation_id, causation_event_id=causation_event_id, payload=payload or {},
            )
        )
        return eid

    def add_run(trigger_id: str, started_at: datetime, finished_at: datetime, decision_summary: str, action: dict, tool_names: list[str]) -> str:
        rid = stable_id(f"archive:run:{case.label}:{counters['r']}")
        counters["r"] += 1
        runs.append(
            ArchiveOrchestrationRun(
                id=rid, trigger_event_id=trigger_id, started_at=started_at, finished_at=finished_at,
                decision_summary=decision_summary[:500], action=action, tool_names=tool_names,
            )
        )
        return rid

    comm_id = stable_id(f"archive:comm:{case.label}:intake")
    case_created_id = add_event(
        "CASE_CREATED", case.created_at, "OPERATOR", "operator",
        f"archive:intake:{case.label}", comm_id, payload={"communication_id": comm_id},
    )

    wo = case.work_orders[0]
    triage_started = _clipped_nudge(rng, case.created_at, wo.created_at, 30, 600)
    triage_finished = _clipped_nudge(rng, triage_started, wo.created_at, 5, 300)
    add_run(
        case_created_id, triage_started, triage_finished, f"Triage: {wo.scope}",
        {
            "kind": "APPLY_TRIAGE", "risk": _no_hazard_risk(case.urgency, triage_finished),
            "issue_description": case.description, "suggested_trade": wo.trade.value, "scope": wo.scope,
        },
        _TOOLS_FOR_TRIAGE,
    )
    add_event(
        "WORK_ORDER_CREATED", wo.created_at, "COORDINATOR", MODEL_ID,
        f"archive:triage:{case.label}", case_created_id,
        causation_event_id=case_created_id, payload={"scope": wo.scope},
    )

    reason = case.notes[0].body if case.notes else "Case cancelled; no work order was completed."
    cancel_corr_id = stable_id(f"archive:cancel-corr:{case.label}")
    # Hard constraint: same reasoning as CASE_RESOLVED above -- this must
    # equal archived_closed_at exactly.
    add_event(
        "CASE_CANCELLED", case.archived_closed_at, "OPERATOR", "operator",
        f"archive:cancel:{case.label}", cancel_corr_id, payload={"reason": reason},
    )

    case.events = sorted(events, key=lambda e: e.occurred_at)
    _deduplicate_occurred_at(case.events)
    case.runs = sorted(runs, key=lambda r: r.started_at)


def _build_case(
    rng: random.Random,
    *,
    property_key: str,
    trade: Trade,
    year: int,
    seq: int,
    status: CaseStatus,
) -> ArchiveCase:
    label = f"{property_key}:{trade.value.lower()}:{year}:{seq}"
    title, description, location = rng.choice(_TITLES[trade])
    created_at = _pick_date_in_year(rng, year, trade)
    urgency = rng.choices(["ROUTINE", "URGENT", "EMERGENCY"], weights=[70, 25, 5])[0]

    case = ArchiveCase(
        id=stable_id(f"archive:case:{label}"),
        label=label,
        property_key=property_key,
        tenant_key=property_key,
        title=title,
        category=trade,
        status=status,
        description=description,
        location=location,
        urgency=urgency,
        created_at=created_at,
        archived_closed_at=created_at,  # placeholder, replaced below
        last_decision_summary="",
    )

    if status == CaseStatus.CANCELLED:
        _fill_cancelled_case(rng, case, trade=trade, year=year)
    else:
        _fill_resolved_case(rng, case, trade=trade, year=year)

    return case


def _fill_resolved_case(rng: random.Random, case: ArchiveCase, *, trade: Trade, year: int) -> None:
    created_at = case.created_at
    work_order_count = rng.choices([1, 2, 3], weights=[55, 35, 10])[0]

    cursor = created_at
    for i in range(work_order_count):
        stagger = timedelta(hours=rng.randint(4, 120))
        wo_created = cursor + stagger
        wo_kind = WorkOrderKind.SCAFFOLD_INSTALL if trade == Trade.SCAFFOLDING else WorkOrderKind.REPAIR
        quote = _cost_amount(rng, trade, year, factor=1.0)
        wo = ArchiveWorkOrder(
            id=stable_id(f"archive:workorder:{case.label}:{i}"),
            kind=wo_kind,
            trade=trade,
            scope=rng.choice(_SCOPES[trade]),
            status=WorkOrderStatus.COMPLETED,
            contractor_key=_contractor_key_for_trade(rng, trade),
            quote_pence=quote,
            approved_limit_pence=quote,
            created_at=wo_created,
            updated_at=wo_created,  # refined once the appointment closing it is known
        )
        case.work_orders.append(wo)
        cursor = wo_created

    # One attendance per work order, plus an optional retry on one of
    # them. The old shape drew 1-2 appointments regardless of how many
    # work orders the case had, so a three-work-order case routinely
    # produced work orders marked COMPLETED with no appointment behind
    # them -- 22 of 87 in the generated set. A completed repair that
    # nobody ever attended is not a thing that happens, and the archive's
    # own `no_open_or_pending_work` check reads the status enum only, so
    # it could never catch it.
    visits: list[tuple[int, int]] = [(i, 1) for i in range(len(case.work_orders))]
    if rng.random() < 0.4:
        # A first attempt that failed and was rebooked: the retry goes on
        # a work order that already has an attempt, so the pairing stays
        # one-appointment-per-work-order plus this extra.
        retry_index = rng.randrange(len(case.work_orders))
        visits.insert(retry_index + 1, (retry_index, 2))
    appointment_count = len(visits)
    latest_end: datetime = created_at
    # Per-work-order cursor: a retry (attempt 2) is scheduled after the
    # attempt it retries actually *ended*, not independently redrawn from
    # the work order's own created_at. Both used to draw their `lead`
    # independently from the same wo.created_at -- 13 of 23 generated
    # retry pairs came out with attempt 2 chronologically *before*
    # attempt 1 (a "completed" re-visit dated weeks ahead of the
    # "no access"/"failed" visit it was supposedly a retry of), which
    # made an honest event log impossible: there is no order in which
    # APPOINTMENT_CONFIRMED(2)/CONTRACTOR_REPORT_RECEIVED(2) can follow
    # APPOINTMENT_CONFIRMED(1)/CONTRACTOR_REPORT_RECEIVED(1) if the
    # underlying timestamps already disagree about which came first.
    last_attempt_end: dict[int, datetime] = {}
    for a, (wo_index, attempt_number) in enumerate(visits):
        wo = case.work_orders[wo_index]
        if attempt_number == 1:
            lead = timedelta(days=rng.randint(2, 18), hours=rng.randint(0, 12))
            start_at = wo.created_at + lead
        else:
            gap = timedelta(days=rng.randint(3, 14), hours=rng.randint(0, 12))
            start_at = last_attempt_end[wo_index] + gap
        end_at = start_at + timedelta(hours=rng.randint(1, 6))
        last_attempt_end[wo_index] = end_at

        # Only an attempt that is itself followed by a retry on the *same*
        # work order failed. Every other visit completed -- the case is a
        # resolved one, so each of its work orders has to have been
        # finished by something.
        superseded = any(i == wo_index and n > attempt_number for i, n in visits)
        if superseded:
            outcome = rng.choice([VisitOutcome.NO_ACCESS, VisitOutcome.BLOCKED, VisitOutcome.FAILED])
        else:
            outcome = VisitOutcome.COMPLETED

        action_created = wo.created_at
        case.appointments.append(
            ArchiveAppointment(
                id=stable_id(f"archive:appointment:{case.label}:{a}"),
                action_id=stable_id(f"archive:action:{case.label}:{a}"),
                work_order_index=wo_index,
                contractor_key=wo.contractor_key,
                slot_id=f"archive-slot-{case.label}-{a}",
                start_at=start_at,
                end_at=end_at,
                attempt_number=attempt_number,
                visit_outcome=outcome,
                action_idempotency_key=f"archive:{case.label}:booking:{a}",
                action_created_at=action_created,
                action_updated_at=end_at,
                action_expected_case_version=1,
            )
        )
        if end_at > latest_end:
            latest_end = end_at
        wo.updated_at = max(wo.updated_at, end_at)

    # A BLOCKED visit is not just report-text flavour: it means a real
    # prerequisite had to be discovered, attended and satisfied before the
    # blocked work order could be retried -- and DEPENDENCY_DISCOVERED/
    # DEPENDENCY_SATISFIED (below, in _build_case_history) need a real
    # DependencyModel-shaped row behind them, not an event about nothing.
    # Materialises a genuine prerequisite work order for exactly the
    # case(s) that already rolled a BLOCKED outcome above, and re-times
    # the retry to start only after the prerequisite finishes.
    dependency = _inject_dependency_if_applicable(rng, case)
    if dependency is not None:
        latest_end = max(a.end_at for a in case.appointments)

    closure_delay = timedelta(hours=rng.randint(2, 72)) if rng.random() < 0.5 else timedelta(days=rng.randint(1, 21))
    case.archived_closed_at = latest_end + closure_delay

    # --- contractor reports ------------------------------------------------
    # One write-up per attended appointment, matching that visit's own
    # outcome (a completion reads differently from a NO_ACCESS/FAILED/
    # BLOCKED writeup) -- must run after archived_closed_at is set, since
    # every report is timestamped inside (visit end, case closure).
    _add_reports(rng, case)

    # --- costs -----------------------------------------------------------
    cost_count = rng.choices([1, 2, 3], weights=[30, 45, 25])[0]
    interval_span = max(int((case.archived_closed_at - created_at).total_seconds()), 3600)

    def _incurred_at(fraction: float) -> datetime:
        return created_at + timedelta(seconds=int(interval_span * fraction))

    primary_quote = case.work_orders[0].quote_pence or 0
    case.costs.append(
        ArchiveCost(
            id=stable_id(f"archive:cost:{case.label}:0"),
            work_order_index=0,
            kind=CostKind.QUOTE,
            amount_pence=primary_quote,
            description=f"Quoted price for: {case.work_orders[0].scope}",
            incurred_at=_incurred_at(0.05),
        )
    )
    if cost_count >= 2:
        invoice_amount = int(round(primary_quote * rng.uniform(0.85, 1.15)))
        case.costs.append(
            ArchiveCost(
                id=stable_id(f"archive:cost:{case.label}:1"),
                work_order_index=0,
                kind=CostKind.INVOICE,
                amount_pence=max(invoice_amount, 500),
                description="Invoice received on completion of works.",
                incurred_at=_incurred_at(0.9),
            )
        )
    if cost_count >= 3:
        last_invoice = case.costs[-1].amount_pence
        adjustment = int(round(last_invoice * rng.uniform(-0.08, 0.08)))
        if adjustment == 0:
            adjustment = 500
        case.costs.append(
            ArchiveCost(
                id=stable_id(f"archive:cost:{case.label}:2"),
                work_order_index=0,
                kind=CostKind.ADJUSTMENT,
                amount_pence=adjustment,
                description="Post-completion adjustment following final reconciliation.",
                incurred_at=_incurred_at(0.97),
            )
        )

    # A 2nd/3rd work order (work_order_count can be up to 3, see above) used
    # to get no CostEntryModel row at all -- only work_orders[0] ever did --
    # which is why WorkOrderModel.quote_pence sums (what Property Stats
    # charts) and CostEntryModel QUOTE sums (what Insights/Reports/CSV
    # chart) disagreed for the same archival case, sometimes by 3x+
    # (docs/audit/11 Finding 3). app.analytics.reconciled_quotes falls back
    # to a work order's own quote_pence when it has no QUOTE entry, which
    # already fixes this at read time with no importer change required --
    # but ledgering every work order here too (symmetric with the
    # work-order-creation loop above) keeps the archive's own CostEntryModel
    # table a complete, non-lossy record on its own terms, not merely
    # "correct once read through the reconciliation layer". No new rng
    # draws here, so this does not perturb any other case's generated data.
    #
    # Iterates to len(case.work_orders), not work_order_count: a dependency
    # can have appended one more work order (the prerequisite) above, and it
    # needs a QUOTE entry of its own for exactly the same reason -- skipping
    # it would resurrect the same quoted-totals mismatch this loop exists
    # to prevent, just for the newest work-order source instead of the
    # original one.
    for wo_idx in range(1, len(case.work_orders)):
        extra_wo = case.work_orders[wo_idx]
        case.costs.append(
            ArchiveCost(
                id=stable_id(f"archive:cost:{case.label}:quote:{wo_idx}"),
                work_order_index=wo_idx,
                kind=CostKind.QUOTE,
                amount_pence=extra_wo.quote_pence or 0,
                description=f"Quoted price for: {extra_wo.scope}",
                incurred_at=_incurred_at(0.05),
            )
        )

    # --- notes -------------------------------------------------------------
    note_count = rng.choices([0, 1, 2], weights=[30, 45, 25])[0]
    for i in range(note_count):
        case.notes.append(
            ArchiveNote(
                id=stable_id(f"archive:note:{case.label}:{i}"),
                body=rng.choice(_NOTE_TEMPLATES),
                author=rng.choice(_NOTE_AUTHORS),
                created_at=_incurred_at(0.5 + 0.1 * i),
            )
        )

    case.last_decision_summary = "Work completed; case closed as resolved."

    # --- event log + coordinator decision history ---------------------------
    # Derived entirely from the structure just built above (work orders,
    # appointments, their visit outcomes, the reports just written, the
    # dependency if one was injected, and archived_closed_at) -- never
    # invented independently of it.
    _build_resolved_case_history(rng, case, dependency=dependency)


def _fill_cancelled_case(rng: random.Random, case: ArchiveCase, *, trade: Trade, year: int) -> None:
    created_at = case.created_at
    wo_created = created_at + timedelta(hours=rng.randint(4, 96))
    quote = _cost_amount(rng, trade, year, factor=0.6)
    wo = ArchiveWorkOrder(
        id=stable_id(f"archive:workorder:{case.label}:0"),
        kind=WorkOrderKind.SCAFFOLD_INSTALL if trade == Trade.SCAFFOLDING else WorkOrderKind.REPAIR,
        trade=trade,
        scope=rng.choice(_SCOPES[trade]),
        status=WorkOrderStatus.CANCELLED,
        contractor_key=_contractor_key_for_trade(rng, trade),
        quote_pence=quote,
        approved_limit_pence=None,
        created_at=wo_created,
        updated_at=wo_created + timedelta(days=rng.randint(1, 10)),
    )
    case.work_orders.append(wo)
    case.archived_closed_at = wo.updated_at + timedelta(hours=rng.randint(2, 48))

    case.costs.append(
        ArchiveCost(
            id=stable_id(f"archive:cost:{case.label}:0"),
            work_order_index=0,
            kind=CostKind.QUOTE,
            amount_pence=quote,
            description=f"Quoted price for: {wo.scope} (work never carried out).",
            incurred_at=wo_created + timedelta(hours=1),
        )
    )
    case.notes.append(
        ArchiveNote(
            id=stable_id(f"archive:note:{case.label}:0"),
            body=rng.choice(_CANCEL_NOTE_TEMPLATES),
            author="archive-import",
            created_at=case.archived_closed_at - timedelta(hours=1),
        )
    )
    case.last_decision_summary = "Case cancelled; no work order was completed."

    _build_cancelled_case_history(rng, case)


def _add_evidence_if_applicable(rng: random.Random, case: ArchiveCase) -> None:
    if case.category not in (Trade.ROOFING,) and rng.random() > 0.15:
        return
    if case.category == Trade.ROOFING and rng.random() > 0.55:
        return
    count = rng.choice([1, 2])
    files = rng.sample(_ILLUSTRATION_FILES, k=min(count, len(_ILLUSTRATION_FILES)))
    for filename in files:
        case.evidence_refs.append(
            ArchiveEvidenceRef(
                source_type=SourceType.OPERATOR,
                # "illustrative-sample:" marks this explicitly as a bundled
                # illustration image, not captured evidence -- alongside
                # provenance=FIXTURE below, which is the schema's existing
                # mechanism for marking a record as non-real (CLAUDE.md).
                locator=f"illustrative-sample:{filename}",
                observed_at=case.created_at,
                provenance=Provenance.FIXTURE,
            )
        )


def _maybe_add_messages(rng: random.Random, case: ArchiveCase, tenant_name: str) -> None:
    if rng.random() > (1 / 3):
        return
    created = case.created_at
    entries = [
        (MessageSenderType.TENANT, tenant_name,
         f"Reported: {case.description}"),
        (MessageSenderType.OPERATOR, "Fixi",
         "Thanks for flagging this -- arranging a contractor visit now."),
    ]
    if rng.random() < 0.5:
        entries.append(
            (MessageSenderType.CONTRACTOR, "Contractor",
             "Attended and carried out the agreed works; case can be closed.")
        )
    for i, (sender_type, sender_name, text) in enumerate(entries):
        msg_at = created + timedelta(hours=i * 6 + rng.randint(0, 4))
        case.messages.append(
            ArchiveMessage(
                id=stable_id(f"archive:message:{case.label}:{i}"),
                sender_type=sender_type,
                sender_name=sender_name,
                text=text,
                created_at=msg_at,
                read_at=msg_at + timedelta(minutes=rng.randint(5, 240)),
            )
        )


def _maybe_add_document(rng: random.Random, case: ArchiveCase, address_line: str) -> None:
    if rng.random() > (10 / 60):
        return
    stored_name = f"{stable_id(f'archive:document:{case.label}')}.txt"
    content = (
        "RepairFlow archival record\n"
        f"Case: {case.title}\n"
        f"Property: {address_line}\n"
        f"Category: {case.category.value}\n"
        f"Closed: {case.archived_closed_at.date().isoformat()}\n"
        "\n"
        "This is a synthetic sample document created for demo history "
        "illustration. It is not a real invoice, quote, or piece of "
        "correspondence.\n"
    )
    case.document = ArchiveDocument(
        stored_name=stored_name,
        display_name=f"Archival record - {case.title[:60]}",
        description="Synthetic archival record; not a scanned original.",
        content=content,
        uploaded_at=case.archived_closed_at,
    )


def build_dataset(seed: int = DEFAULT_SEED, label: str = DEFAULT_LABEL) -> ArchiveDataset:
    rng = random.Random(seed)

    properties = _build_properties()
    tenants = _build_tenants()
    contractors = _build_contractors()

    cases: list[ArchiveCase] = []
    for spec in PROPERTY_SPECS:
        property_key = spec["key"]
        case_count = spec["case_count"]
        recurring_trade: Trade | None = spec["recurring_trade"]
        recurring_count = spec["recurring_count"]

        trades_for_property: list[Trade] = []
        if recurring_trade is not None:
            trades_for_property.extend([recurring_trade] * recurring_count)
        remaining = case_count - len(trades_for_property)
        for _ in range(remaining):
            trades_for_property.append(_ALL_TRADES[rng.randrange(len(_ALL_TRADES))])
        rng.shuffle(trades_for_property)

        years_for_property = rng.choices(_YEARS, weights=_YEAR_WEIGHTS, k=case_count)
        years_for_property.sort()

        status_rolls = rng.choices(
            [CaseStatus.RESOLVED, CaseStatus.CANCELLED], weights=[90, 10], k=case_count
        )

        per_property_seq: dict[tuple[Trade, int], int] = {}
        for trade, year, status in zip(trades_for_property, years_for_property, status_rolls):
            seq_key = (trade, year)
            seq = per_property_seq.get(seq_key, 0)
            per_property_seq[seq_key] = seq + 1
            case = _build_case(
                rng, property_key=property_key, trade=trade, year=year, seq=seq, status=status
            )
            if status == CaseStatus.RESOLVED:
                _add_evidence_if_applicable(rng, case)
                tenant_name = next(t.display_name for t in tenants if t.property_key == property_key)
                _maybe_add_messages(rng, case, tenant_name)
                address_line = next(p.address_line for p in properties if p.key == property_key)
                _maybe_add_document(rng, case, address_line)
            cases.append(case)

    return ArchiveDataset(
        label=label,
        generator_version=GENERATOR_VERSION,
        random_seed=seed,
        description=(
            "Synthetic historical archive: illustrative sample repair history "
            "across 8 archival properties (2021-2026), for demo analytics only."
        ),
        properties=properties,
        tenants=tenants,
        contractors=contractors,
        cases=cases,
    )
