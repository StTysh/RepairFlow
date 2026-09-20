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

GENERATOR_VERSION = "1.0.0"
DEFAULT_SEED = 20260920
DEFAULT_LABEL = "synthetic-archive-v1"

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
    costs: list[ArchiveCost] = field(default_factory=list)
    notes: list[ArchiveNote] = field(default_factory=list)
    messages: list[ArchiveMessage] = field(default_factory=list)
    document: ArchiveDocument | None = None


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
    for a, (wo_index, attempt_number) in enumerate(visits):
        wo = case.work_orders[wo_index]
        lead = timedelta(days=rng.randint(2, 18), hours=rng.randint(0, 12))
        start_at = wo.created_at + lead
        end_at = start_at + timedelta(hours=rng.randint(1, 6))

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

    closure_delay = timedelta(hours=rng.randint(2, 72)) if rng.random() < 0.5 else timedelta(days=rng.randint(1, 21))
    case.archived_closed_at = latest_end + closure_delay

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
    for wo_idx in range(1, work_order_count):
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
