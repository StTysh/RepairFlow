"""Operational sample workload: open and recently-closed cases.

Why this exists, and how it differs from `app.archive`
------------------------------------------------------
`app.archive` imports *closed* history and tags every row with an
`archive_batch_id`. Everything operational -- the dashboard counters, the
ticket list, the overview -- filters that out on purpose, so importing the
archive leaves the working surfaces exactly as empty as they were. That is
the right containment for sample history, and it is not what this module
does.

This module writes **operational** rows (`archive_batch_id IS NULL`): the
cases an operator is supposed to be looking at. Without them a freshly
bootstrapped workspace shows `awaiting_confirmation = 0`,
`escalated = 0`, `resolved_this_week = 0` and a null average
resolution time, because nothing has ever moved through those states --
the numbers are not wrong, there is simply nothing to count.

Because these rows *are* operational, honesty costs more here than it does
in the archive. Every case this module writes:

* carries `Provenance.SIMULATED` on its events, appointments and reports,
  so no screen can present generated activity as something that really
  happened (docs/19; "all demo physical activity and outbound commitments
  carry simulation provenance");
* names its contractors from the seeded roster, whose display names all
  end in "(fictional, SIMULATED)";
* gets a CASE note recording that it came from this generator, which is
  also how `--status` finds them again;
* writes **no** `jobs` rows. A job is a durable instruction to go and do
  something; generated history must never cause the worker to wake up and
  act on a case that nobody actually filed.

Timestamps are backdated deliberately. `avg_resolution_hours` measures
`CASE_RESOLVED.occurred_at - case.created_at` over a 30-day window, so a
case created and resolved in the same second would report a resolution
time of zero and quietly poison the mean. The scenarios below span
realistic durations (about 16 hours to 6 days) and land inside or outside
the 7-day "this week" window on purpose.

    python -m app.sample_operations --status
    python -m app.sample_operations --dry-run
    python -m app.sample_operations --apply
    python -m app.sample_operations --validate
    python -m app.sample_operations --remove

Ids are `uuid5` over a fixed namespace, so `--apply` is idempotent and
`--remove` can find every row it wrote without consulting a manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import run_cli, session_scope
from app.domain.services import evidence_ref_dict
from app.models import (
    ActionRecordModel,
    AppointmentModel,
    CaseEventModel,
    ContractorModel,
    ContractorReportModel,
    CostEntryModel,
    NoteModel,
    OrchestrationRunModel,
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
    CostKind,
    OrchestrationRunState,
    Provenance,
    SourceType,
    RecordSubject,
    Trade,
    VisitOutcome,
    WorkOrderKind,
    WorkOrderStatus,
)

GENERATOR_VERSION = "1.0.0"
MARKER = "sample-operations-v1"
#: Stamped on every generated OrchestrationRun. `fixture:` prefixed so the
#: "was this a real model call" checks (and docs/26's no-fake-traces rule)
#: can tell these apart from a genuine Gemini run at a glance.
MODEL_ID = "fixture:sample-ops-v1"
NOTE_AUTHOR = "sample-operations"

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "repairflow.sample-operations")


def stable_id(label: str) -> str:
    """Deterministic id, so --apply is idempotent and --remove is exact."""
    return str(uuid.uuid5(_NAMESPACE, f"{MARKER}:{label}"))


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Scenario table
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """One generated case.

    `age_days` is how long ago the tenant reported it. `duration_hours` is
    how long the case took to reach its terminal state, and is required for
    RESOLVED and CANCELLED. For open states it is the age of the *latest*
    step instead, which is what drives "waiting since" on the UI.
    """

    key: str
    status: CaseStatus
    title: str
    description: str
    location: str
    trade: Trade
    scope: str
    property_index: int
    tenant_index: int
    age_days: float
    duration_hours: float
    quote_pence: int
    #: ROUTINE or URGENT only. Never EMERGENCY: docs/19 forbids autonomous
    #: handling of gas/fire/flood/electrical danger, so a generated
    #: emergency would be a fake one sitting in the operator's queue.
    urgency: str = "ROUTINE"
    report_text: str = ""
    #: ESCALATED only: why a human was pulled in.
    escalation_reason: str = ""
    escalation_code: str = ""
    #: ESCALATED/ACTIVE retry cases: the first visit failed this way.
    failed_outcome: VisitOutcome | None = None
    #: ACTIVE only: hours from now until the booked visit starts.
    upcoming_visit_in_hours: float = 0.0
    #: CANCELLED only.
    cancel_reason: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


# Resolved inside the last 7 days -- these are what make `resolved_this_week`
# and `avg_resolution_hours` non-zero. Durations vary on purpose: a mean
# assembled from identical samples looks generated the moment anyone reads it.
_RECENT_RESOLVED: tuple[Scenario, ...] = (
    Scenario(
        key="res-01", status=CaseStatus.RESOLVED,
        title="Kitchen extractor fan stopped working",
        description="The extractor fan over the hob stopped turning on Tuesday. No noise at all when the switch is pressed.",
        location="Kitchen", trade=Trade.ELECTRICAL,
        scope="Test extractor isolator and fan unit; replace fan if the motor has failed.",
        property_index=0, tenant_index=0, age_days=6.2, duration_hours=41.0, quote_pence=14500,
        report_text="Isolator tested fine, fan motor had seized. Fitted a replacement unit of the same size and tested on all three speeds. Left the old unit with the tenant's permission for disposal.",
    ),
    Scenario(
        key="res-02", status=CaseStatus.RESOLVED,
        title="Bathroom radiator cold at the top",
        description="The bathroom radiator is warm at the bottom but stays cold across the top third.",
        location="Bathroom", trade=Trade.PLUMBING,
        scope="Bleed radiator, check system pressure and balance if required.",
        property_index=1, tenant_index=1, age_days=5.4, duration_hours=19.5, quote_pence=6500,
        report_text="Bled the radiator, a good amount of air came out. Topped the system back up to 1.3 bar and checked the other radiators on the same circuit were heating evenly. All fine on test.",
    ),
    Scenario(
        key="res-03", status=CaseStatus.RESOLVED,
        title="Loose handrail on the staircase",
        description="The handrail going up the stairs moves when you lean on it. Feels like the bracket is coming away from the wall.",
        location="Staircase", trade=Trade.OTHER,
        scope="Refix staircase handrail; check all brackets and plugs into masonry.",
        property_index=2, tenant_index=2, age_days=4.8, duration_hours=52.0, quote_pence=9000,
        report_text="Two of the four brackets had pulled out of soft plaster. Re-drilled into the masonry behind with longer fixings and refitted all four brackets. Handrail is solid, load tested by hand.",
    ),
    Scenario(
        key="res-04", status=CaseStatus.RESOLVED,
        title="Slow drain in the en-suite shower",
        description="The shower in the en-suite has started draining slowly, water pools around my feet by the end.",
        location="En-suite", trade=Trade.PLUMBING,
        scope="Clear shower waste and trap; check fall on the waste run.",
        property_index=3, tenant_index=3, age_days=3.9, duration_hours=26.5, quote_pence=8500,
        report_text="Cleared a substantial hair blockage from the trap and rodded the waste run to the stack. Ran the shower for five minutes on test, drained away freely. Advised the tenant on a drain guard.",
    ),
    Scenario(
        key="res-05", status=CaseStatus.RESOLVED,
        title="Front door draught excluder torn",
        description="The rubber strip along the bottom of the front door has torn and there is a cold draught coming in.",
        location="Front entrance", trade=Trade.OTHER,
        scope="Replace front door weather seal and adjust door closer.",
        property_index=0, tenant_index=0, age_days=2.6, duration_hours=16.0, quote_pence=4500,
        report_text="Replaced the full-length brush seal at the threshold and adjusted the hinges slightly so the door closes square. Draught gone on test with the door shut.",
    ),
    Scenario(
        key="res-06", status=CaseStatus.RESOLVED,
        title="Outside tap dripping continuously",
        description="The garden tap has started dripping and does not stop even when turned off hard.",
        location="Rear garden", trade=Trade.PLUMBING,
        scope="Replace outside tap washer or tap body; check isolation valve.",
        property_index=1, tenant_index=1, age_days=1.7, duration_hours=22.0, quote_pence=5500,
        report_text="Washer had perished. Isolated at the internal valve, replaced the washer and the tap spindle, then tested under full pressure for leaks. Dry after ten minutes.",
    ),
)

# Resolved 9-27 days ago: inside the 30-day average window, outside "this
# week". Without these the average is computed from six samples that all
# landed in the same few days, which is not a portfolio average at all.
_OLDER_RESOLVED: tuple[Scenario, ...] = (
    Scenario(
        key="res-07", status=CaseStatus.RESOLVED,
        title="Hallway light flickering",
        description="The hallway ceiling light flickers when it is first switched on, then settles after a minute.",
        location="Hallway", trade=Trade.ELECTRICAL,
        scope="Investigate flickering hallway light; check fitting, lamp and connections.",
        property_index=2, tenant_index=2, age_days=11.0, duration_hours=68.0, quote_pence=7500,
        report_text="Loose neutral at the ceiling rose. Remade the connection in a proper terminal block and replaced the lamp while there. Tested over ten minutes of switching, no flicker.",
    ),
    Scenario(
        key="res-08", status=CaseStatus.RESOLVED,
        title="Gutter overflowing at the side of the house",
        description="Water pours over the side of the gutter in heavy rain rather than going down the pipe.",
        location="Side elevation", trade=Trade.ROOFING,
        scope="Clear gutter run and downpipe on the side elevation; check falls.",
        property_index=3, tenant_index=3, age_days=14.5, duration_hours=96.0, quote_pence=18500, urgency="URGENT",
        report_text="Gutter was packed with moss and leaf litter for about four metres. Cleared the full run and flushed the downpipe. Re-set two brackets that had dropped so the fall runs to the outlet properly.",
    ),
    Scenario(
        key="res-09", status=CaseStatus.RESOLVED,
        title="Bedroom window will not stay open",
        description="The rear bedroom window drops shut on its own, the hinge friction seems to have gone.",
        location="Rear bedroom", trade=Trade.OTHER,
        scope="Adjust or replace friction stays on the rear bedroom window.",
        property_index=0, tenant_index=0, age_days=18.0, duration_hours=44.5, quote_pence=11000,
        report_text="Both friction stays were worn past adjustment. Fitted new stays of the correct length and tested the window holds at all positions including fully open.",
    ),
    Scenario(
        key="res-10", status=CaseStatus.RESOLVED,
        title="Boiler pressure dropping weekly",
        description="I have to top the boiler up every week or so, the pressure drops back to under 1 bar.",
        location="Kitchen", trade=Trade.PLUMBING,
        scope="Trace pressure loss; check expansion vessel, PRV and visible pipework.",
        property_index=1, tenant_index=1, age_days=21.0, duration_hours=139.0, quote_pence=24500,
        report_text="Expansion vessel had lost its charge and the PRV was weeping to the outside discharge. Recharged the vessel and replaced the PRV cartridge. Pressure held at 1.3 bar over a 48 hour check.",
    ),
    Scenario(
        key="res-11", status=CaseStatus.RESOLVED,
        title="Kitchen cupboard door hanging off",
        description="The cupboard door next to the sink has come away at the top hinge and hangs at an angle.",
        location="Kitchen", trade=Trade.OTHER,
        scope="Refit kitchen cupboard door; replace hinge and repair carcass fixing if stripped.",
        property_index=2, tenant_index=2, age_days=25.0, duration_hours=30.0, quote_pence=6000,
        report_text="Hinge plate screws had stripped out of the chipboard carcass. Plugged and re-drilled the fixings, fitted a new soft-close hinge and aligned the door against its neighbour.",
    ),
    Scenario(
        key="res-12", status=CaseStatus.RESOLVED,
        title="Damp patch on the chimney breast",
        description="A brown patch has appeared on the chimney breast in the front room and feels damp to touch.",
        location="Front room", trade=Trade.ROOFING,
        scope="Inspect chimney flashing and pointing; repair defect causing water ingress.",
        property_index=3, tenant_index=3, age_days=27.0, duration_hours=163.0, quote_pence=42500, urgency="URGENT",
        report_text="Lead flashing on the left side of the stack had lifted and the mortar fillet had cracked away. Dressed the lead back in and renewed the fillet. Checked the pot and cowl while up there, both sound.",
    ),
)

_AWAITING: tuple[Scenario, ...] = (
    Scenario(
        key="awa-01", status=CaseStatus.AWAITING_CONFIRMATION,
        title="Washing machine waste leaking under the sink",
        description="There is water under the kitchen sink whenever the washing machine drains.",
        location="Kitchen", trade=Trade.PLUMBING,
        scope="Reseal washing machine waste connection and check standpipe trap.",
        property_index=0, tenant_index=0, age_days=4.2, duration_hours=30.0, quote_pence=9500,
        report_text="Waste hose was not seated properly in the standpipe and the trap seal had perished. Renewed the trap and clipped the hose in correctly. Ran a full cycle, no water under the unit.",
    ),
    Scenario(
        key="awa-02", status=CaseStatus.AWAITING_CONFIRMATION,
        title="Bedroom socket not working",
        description="The double socket by the bed has stopped working. The other sockets in the room are fine.",
        location="Main bedroom", trade=Trade.ELECTRICAL,
        scope="Fault-find dead socket on the bedroom ring; repair connection.",
        property_index=1, tenant_index=1, age_days=3.1, duration_hours=25.0, quote_pence=8500,
        report_text="Broken conductor at the back of the socket where it had been over-tightened. Remade both legs of the ring into a new accessory and tested continuity around the circuit. Socket live and tested.",
    ),
    Scenario(
        key="awa-03", status=CaseStatus.AWAITING_CONFIRMATION,
        title="Loose ridge tile visible from the garden",
        description="One of the ridge tiles at the top of the roof looks like it has slipped out of line.",
        location="Main roof", trade=Trade.ROOFING,
        scope="Re-bed slipped ridge tile and check the remainder of the ridge line.",
        property_index=2, tenant_index=2, age_days=6.8, duration_hours=101.0, quote_pence=32500, urgency="URGENT",
        report_text="One ridge tile had lost its bedding entirely and two others were loose. Re-bedded all three in fresh mortar and pointed the ridge line. Checked the rest of the ridge, no other movement.",
    ),
    Scenario(
        key="awa-04", status=CaseStatus.AWAITING_CONFIRMATION,
        title="Toilet running constantly",
        description="The toilet keeps running into the pan long after flushing and you can hear it all night.",
        location="Bathroom", trade=Trade.PLUMBING,
        scope="Replace toilet fill valve and flush mechanism as required.",
        property_index=3, tenant_index=3, age_days=1.9, duration_hours=21.0, quote_pence=7000,
        report_text="Fill valve diaphragm had failed and the flush valve seal was passing. Replaced both, adjusted the water level to the fill line and checked for silent running over fifteen minutes.",
    ),
)

_ESCALATED: tuple[Scenario, ...] = (
    Scenario(
        key="esc-01", status=CaseStatus.ESCALATED,
        title="No access for boiler service on two attempts",
        description="Annual boiler service due. Tenant has not been in for either booked appointment.",
        location="Kitchen", trade=Trade.PLUMBING,
        scope="Annual boiler service and safety check.",
        property_index=0, tenant_index=0, age_days=16.0, duration_hours=210.0, quote_pence=11000,
        failed_outcome=VisitOutcome.NO_ACCESS,
        report_text="Attended at the agreed time and waited fifteen minutes. No answer at the door and no response by phone. Second attempt, same outcome. Not able to gain access to the appliance.",
        escalation_code="REPEATED_NO_ACCESS",
        escalation_reason="Two consecutive no-access visits on a statutory boiler service. Needs a human to contact the tenant directly and agree an access arrangement before a third visit is booked and charged.",
    ),
    Scenario(
        key="esc-02", status=CaseStatus.ESCALATED,
        title="Repair cost above the approved limit",
        description="Water staining spreading across the upstairs landing ceiling, getting worse each time it rains.",
        location="Landing", trade=Trade.ROOFING,
        scope="Investigate and repair water ingress above the landing; make good ceiling.",
        property_index=1, tenant_index=1, age_days=9.5, duration_hours=124.0, quote_pence=187500, urgency="URGENT",
        failed_outcome=VisitOutcome.BLOCKED,
        report_text="Opened up the ceiling to trace the ingress. The felt underlay has failed across a wide area, not a single slipped tile. This needs a section of the roof stripped and re-felted with scaffold access, which is well beyond the original scope and the approved limit.",
        escalation_code="COST_ABOVE_LIMIT",
        escalation_reason="Revised quote of GBP 1,875.00 exceeds the standing approval limit. A human must authorise the spend and confirm whether the landlord wants the full re-felt or a temporary repair first.",
    ),
    Scenario(
        key="esc-03", status=CaseStatus.ESCALATED,
        title="Tenant disputes that the leak was fixed",
        description="Reported the same leak again a week after it was signed off as complete.",
        location="Bathroom", trade=Trade.PLUMBING,
        scope="Re-investigate reported leak beneath the bathroom after previous repair signed off.",
        property_index=2, tenant_index=2, age_days=13.0, duration_hours=188.0, quote_pence=13500,
        failed_outcome=VisitOutcome.FAILED,
        report_text="Attended and could not reproduce the leak on test. Ran the bath, shower and basin for ten minutes each with the ceiling below open. Everything dry. Tenant is certain it is still happening intermittently.",
        escalation_code="CONTRADICTORY_EVIDENCE",
        escalation_reason="Contractor cannot reproduce the fault and the tenant maintains it is ongoing. Conflicting accounts need a human to arbitrate before the case is closed a second time or a different trade is sent.",
    ),
)

_ACTIVE: tuple[Scenario, ...] = (
    Scenario(
        key="act-01", status=CaseStatus.ACTIVE,
        title="Dripping shower mixer in the family bathroom",
        description="The shower mixer drips constantly even when it is fully off.",
        location="Bathroom", trade=Trade.PLUMBING,
        scope="Replace shower mixer cartridge; check isolation valves.",
        property_index=0, tenant_index=0, age_days=2.1, duration_hours=8.0, quote_pence=9500,
        upcoming_visit_in_hours=27.0,
    ),
    Scenario(
        key="act-02", status=CaseStatus.ACTIVE,
        title="Consumer unit tripping when the oven is used",
        description="The RCD trips whenever the oven and kettle are on together.",
        location="Kitchen", trade=Trade.ELECTRICAL,
        scope="Investigate RCD tripping under load; test oven circuit and insulation resistance.",
        property_index=1, tenant_index=1, age_days=1.4, duration_hours=5.0, quote_pence=16500, urgency="URGENT",
        upcoming_visit_in_hours=50.0,
    ),
    Scenario(
        key="act-03", status=CaseStatus.ACTIVE,
        title="Scaffold required for rear elevation repointing",
        description="Mortar is crumbling out of the brickwork on the rear wall at first floor level.",
        location="Rear elevation", trade=Trade.SCAFFOLDING,
        scope="Erect scaffold to rear elevation to allow repointing at first floor.",
        property_index=2, tenant_index=2, age_days=5.0, duration_hours=12.0, quote_pence=68000, urgency="URGENT",
        upcoming_visit_in_hours=96.0,
    ),
    Scenario(
        key="act-04", status=CaseStatus.ACTIVE,
        title="Second visit needed after parts were unavailable",
        description="Radiator valve in the front room is seized and weeping at the spindle.",
        location="Front room", trade=Trade.PLUMBING,
        scope="Replace seized thermostatic radiator valve on the front room radiator.",
        property_index=3, tenant_index=3, age_days=7.5, duration_hours=60.0, quote_pence=12500,
        failed_outcome=VisitOutcome.FAILED,
        report_text="Attended and isolated the radiator but the valve is an obsolete size and I did not have a compatible replacement on the van. Left the radiator isolated and safe. Need to return with the correct valve, ordered today.",
        upcoming_visit_in_hours=18.0,
    ),
)

_CANCELLED: tuple[Scenario, ...] = (
    Scenario(
        key="can-01", status=CaseStatus.CANCELLED,
        title="Duplicate report of the kitchen tap drip",
        description="Kitchen tap dripping. (Reported again by the same tenant the following day.)",
        location="Kitchen", trade=Trade.PLUMBING,
        scope="Replace kitchen tap washer.",
        property_index=0, tenant_index=0, age_days=8.0, duration_hours=4.0, quote_pence=0,
        cancel_reason="Duplicate of an existing open case for the same tap. Closed in favour of the original so the work is not booked twice.",
    ),
    Scenario(
        key="can-02", status=CaseStatus.CANCELLED,
        title="Tenant resolved the blocked gully themselves",
        description="The drain gully outside the back door is backing up when it rains.",
        location="Rear entrance", trade=Trade.OTHER,
        scope="Clear blocked gully at the rear entrance.",
        property_index=2, tenant_index=2, age_days=12.0, duration_hours=29.0, quote_pence=0,
        cancel_reason="Tenant cleared the leaf blockage themselves and asked us to cancel the visit before a contractor was dispatched.",
    ),
)

SCENARIOS: tuple[Scenario, ...] = (
    _RECENT_RESOLVED + _OLDER_RESOLVED + _AWAITING + _ESCALATED + _ACTIVE + _CANCELLED
)


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


@dataclass
class _Ctx:
    """Everything one case needs that comes from the database."""

    properties: list[PropertyModel]
    tenants: list[TenantModel]
    contractors_by_trade: dict[Trade, list[ContractorModel]]
    now: datetime


#: Slot start hours a letting agency actually books into.
_SLOT_HOURS = (8, 10, 13, 15)


def _working_slot(target: datetime, *, forward: bool = True) -> datetime:
    """Snap a datetime to a plausible weekday appointment slot.

    Offsets measured in bare hours from "now" produce bookings like
    22:31-00:31 and 04:31-06:31, which no contractor and no tenant would
    ever agree to.

    Direction matters. A visit still to come rounds *forward* to the next
    slot. A visit that already happened must round *backward*: rounding a
    past visit forward pushed it after the report that describes it, and
    sometimes past `now` altogether -- which `--validate` then caught as
    "events never go backwards in time" and "no event is in the future".
    """
    step = timedelta(hours=1) if forward else timedelta(hours=-1)
    candidate = target.replace(minute=0, second=0, microsecond=0)
    if not forward and candidate > target:
        candidate -= timedelta(hours=1)
    for _ in range(14 * 24):
        in_range = candidate >= target if forward else candidate <= target
        if candidate.weekday() < 5 and candidate.hour in _SLOT_HOURS and in_range:
            return candidate
        candidate += step
    return target  # unreachable in practice; never loop forever


def _slot_between(earliest: datetime, latest: datetime, preferred: datetime) -> datetime:
    """The weekday slot closest to `preferred` that fits in the window.

    A past visit is boxed in on both sides: it cannot precede the booking
    that arranged it, and it must leave room for the report, the
    completion and the resolution that follow it before the case closes.
    Snapping in one direction only satisfies one of those and breaks the
    other, so search the window and fall back to the unsnapped time rather
    than emit a timeline that contradicts itself.
    """
    if latest <= earliest:
        return preferred
    best: datetime | None = None
    candidate = earliest.replace(minute=0, second=0, microsecond=0)
    while candidate <= latest:
        if candidate >= earliest and candidate.weekday() < 5 and candidate.hour in _SLOT_HOURS:
            if best is None or abs(candidate - preferred) < abs(best - preferred):
                best = candidate
        candidate += timedelta(hours=1)
    # No slot fits (a very short case booked late in the day). Keep the
    # timeline valid and at least land on a whole hour rather than an
    # arbitrary 20:31.
    return best if best is not None else preferred.replace(minute=0, second=0, microsecond=0)


def _contractor_for(ctx: _Ctx, scenario: Scenario) -> ContractorModel:
    """Pick deterministically from the approved roster for the trade.

    Falls back to OTHER, then to any contractor at all: a generated case
    that cannot name a contractor is worse than one that names a plausible
    generalist, and the seeded roster covers every trade anyway.
    """
    pool = ctx.contractors_by_trade.get(scenario.trade) or ctx.contractors_by_trade.get(Trade.OTHER) or []
    if not pool:
        pool = [c for group in ctx.contractors_by_trade.values() for c in group]
    if not pool:
        raise RuntimeError("no approved contractors in the database; run `python -m app.seed` first")
    index = int(stable_id(f"contractor:{scenario.key}")[:8], 16) % len(pool)
    return pool[index]


class _CaseBuilder:
    """Accumulates the rows for a single generated case.

    Sequence numbers, event ordering and the "one orchestration run per
    decision" shape are enforced here rather than in each scenario builder,
    because those are exactly the invariants `--validate` checks and the
    case-flow graph in the UI depends on.
    """

    def __init__(self, scenario: Scenario, ctx: _Ctx, case_number: int) -> None:
        self.s = scenario
        self.ctx = ctx
        self.case_id = stable_id(f"case:{scenario.key}")
        self.issue_id = stable_id(f"issue:{scenario.key}")
        self.created_at = ctx.now - timedelta(days=scenario.age_days)
        self.case_number = case_number
        self.contractor = _contractor_for(ctx, scenario)
        self.rows: list[object] = []
        self.events: list[CaseEventModel] = []
        self._seq = 0
        self._last_event_id: str | None = None

    # -- primitives ------------------------------------------------------

    def event(
        self,
        event_type: str,
        *,
        at: datetime,
        actor_type: str,
        payload: dict,
        actor_id: str = "sample-operations",
    ) -> CaseEventModel:
        self._seq += 1
        row = CaseEventModel(
            id=stable_id(f"event:{self.s.key}:{self._seq}"),
            case_id=self.case_id,
            seq=self._seq,
            type=event_type,
            occurred_at=at,
            received_at=at,
            actor_type=actor_type,
            actor_id=actor_id,
            source_event_key=f"{MARKER}:{self.s.key}:{self._seq}",
            correlation_id=stable_id(f"corr:{self.s.key}"),
            causation_event_id=self._last_event_id,
            payload_version=1,
            payload=payload,
            provenance=Provenance.SIMULATED,
        )
        self._last_event_id = row.id
        self.events.append(row)
        self.rows.append(row)
        return row

    def run(self, trigger: CaseEventModel, *, summary: str, action: dict, started: datetime) -> None:
        """A coordinator wake that produced one proposal.

        `finished_at` is deliberately a few seconds after `started_at`: an
        earlier generator spread run start/finish across the case's whole
        headroom and produced a "took 192381.0s" model call on the Agent
        tab, which is not a thing that happens.
        """
        seconds = 8 + int(stable_id(f"dur:{self.s.key}:{trigger.seq}")[:4], 16) % 170
        self.rows.append(
            OrchestrationRunModel(
                id=stable_id(f"run:{self.s.key}:{trigger.seq}"),
                case_id=self.case_id,
                trigger_event_id=trigger.id,
                snapshot_version=1,
                model_id=MODEL_ID,
                # Explicit: the column defaults to RUNNING, and a generated
                # run left at that default makes the dashboard's
                # `agent_active` flag true forever -- a spinner asserting
                # the coordinator is mid-flight when nothing is running.
                state=OrchestrationRunState.SUCCEEDED,
                started_at=started,
                finished_at=started + timedelta(seconds=seconds),
                usage={"generated": True, "generator_version": GENERATOR_VERSION},
                proposal={
                    "case_id": self.case_id,
                    "expected_case_version": 1,
                    "trigger_event_id": trigger.id,
                    "decision_summary": summary,
                    "evidence_refs": [],
                    "action": action,
                },
                tool_calls=[],
                policy_result="SUCCEEDED",
                error_code=None,
            )
        )

    def action_record(self, kind: str, *, at: datetime, target_id: str | None, proposal: dict) -> str:
        action_id = stable_id(f"action:{self.s.key}:{kind}:{target_id or ''}")
        self.rows.append(
            ActionRecordModel(
                id=action_id,
                case_id=self.case_id,
                kind=kind,
                target_id=target_id,
                idempotency_key=f"{MARKER}:{self.s.key}:{kind}:{target_id or 'none'}",
                payload_hash=_hash(f"{self.s.key}:{kind}:{target_id}"),
                proposal=proposal,
                state=ActionState.SUCCEEDED.value,
                approval=None,
                result={"generated": True},
                created_at=at,
                updated_at=at,
            )
        )
        return action_id

    def risk(self, assessed_at: datetime) -> dict:
        """A no-hazard assessment.

        Every generated scenario is deliberately a routine repair. Nothing
        here may present as a gas, fire, flood or electrical-danger case:
        docs/19 forbids autonomous handling of those, and a generated
        emergency would be a fake one sitting in the operator's queue.
        """
        return {
            "urgency": self.s.urgency,
            "gas": "NO",
            "fire": "NO",
            "water_near_electrics": "NO",
            "structural_danger": "NO",
            "uncontrolled_flood": "NO",
            "vulnerability_concern": "NO",
            "evidence_refs": [],
            "uncertainties": [],
            "assessed_at": assessed_at.isoformat().replace("+00:00", "Z"),
        }


def _build_case(scenario: Scenario, ctx: _Ctx, case_number: int) -> list[object]:
    b = _CaseBuilder(scenario, ctx, case_number)
    s = scenario
    prop = ctx.properties[s.property_index % len(ctx.properties)]
    tenant = ctx.tenants[s.tenant_index % len(ctx.tenants)]
    end_at = b.created_at + timedelta(hours=s.duration_hours)

    terminal = s.status in (CaseStatus.RESOLVED, CaseStatus.CANCELLED)
    case = RepairCaseModel(
        id=b.case_id,
        case_number=case_number,
        property_id=prop.id,
        tenant_id=tenant.id,
        status=s.status,
        version=1,
        title=s.title,
        risk=b.risk(b.created_at + timedelta(minutes=12)),
        created_at=b.created_at,
        updated_at=end_at if terminal else ctx.now - timedelta(hours=2),
        owner_operator_id="operator",
        category=s.trade,
        escalation_reason=s.escalation_reason or None,
        resume_status=CaseStatus.ACTIVE if s.status == CaseStatus.ESCALATED else None,
        archive_batch_id=None,
    )
    b.rows.append(case)
    b.rows.append(
        RepairIssueModel(
            id=b.issue_id,
            case_id=b.case_id,
            description=s.description,
            location=s.location,
            started_at=b.created_at - timedelta(days=1),
            evidence_refs=[],
            tenant_resolution_confirmed_at=end_at if s.status == CaseStatus.RESOLVED else None,
            unresolved_concerns=[],
        )
    )

    # 1. Reported.
    created = b.event("CASE_CREATED", at=b.created_at, actor_type="OPERATOR", payload={"source": MARKER})

    if s.status == CaseStatus.CANCELLED:
        b.run(created, summary=f"Triage: {s.scope}", started=b.created_at + timedelta(minutes=9),
              action={"kind": "APPLY_TRIAGE", "risk": b.risk(b.created_at + timedelta(minutes=12)),
                      "issue_description": s.description, "suggested_trade": s.trade.value, "scope": s.scope})
        b.event("CASE_CANCELLED", at=end_at, actor_type="OPERATOR", payload={"reason": s.cancel_reason})
        b.rows.append(_note(b, f"Cancelled: {s.cancel_reason}"))
        return b.rows

    # 2. Triaged into a work order.
    triage_at = b.created_at + timedelta(minutes=14)
    b.run(created, summary=f"Triage: {s.scope}", started=b.created_at + timedelta(minutes=9),
          action={"kind": "APPLY_TRIAGE", "risk": b.risk(triage_at), "issue_description": s.description,
                  "suggested_trade": s.trade.value, "scope": s.scope})
    wo_id = stable_id(f"wo:{s.key}")
    wo_created = b.event("WORK_ORDER_CREATED", at=triage_at, actor_type="COORDINATOR",
                         payload={"work_order_id": wo_id, "scope": s.scope})

    # Work-order status has to match where the case actually got to, or the
    # ticket page contradicts its own header.
    if s.status == CaseStatus.RESOLVED or s.status == CaseStatus.AWAITING_CONFIRMATION:
        wo_status = WorkOrderStatus.COMPLETED
    elif s.status == CaseStatus.ESCALATED:
        wo_status = WorkOrderStatus.BLOCKED
    else:
        wo_status = WorkOrderStatus.SCHEDULED

    work_order = WorkOrderModel(
        id=wo_id, case_id=b.case_id, issue_id=b.issue_id,
        kind=WorkOrderKind.SCAFFOLD_INSTALL if s.trade == Trade.SCAFFOLDING else WorkOrderKind.REPAIR,
        trade=s.trade, scope=s.scope, status=wo_status,
        contractor_id=b.contractor.id, required_for_resolution=True,
        quote_pence=s.quote_pence or None, approved_limit_pence=None,
        completion_report_id=None,
        created_at=triage_at, updated_at=end_at if terminal else ctx.now - timedelta(hours=3),
    )
    b.rows.append(work_order)
    if s.quote_pence:
        b.rows.append(
            CostEntryModel(
                id=stable_id(f"cost:quote:{s.key}"), case_id=b.case_id, work_order_id=wo_id,
                kind=CostKind.QUOTE, amount_pence=s.quote_pence,
                description=f"Quoted: {s.scope}", incurred_at=triage_at,
                recorded_by=NOTE_AUTHOR, recorded_at=triage_at, archive_batch_id=None,
            )
        )

    # 3. A visit is booked.
    #
    # An ACTIVE case with no failed visit behind it has not been attended
    # yet -- that is *why* it is still active -- so it gets no past
    # appointment and no report, only the booking that is still to come
    # (handled at step 4b). Generating a FINISHED, COMPLETED visit and then
    # labelling the case ACTIVE would contradict itself on the ticket page,
    # and `appointments` has a UNIQUE (work_order_id, attempt_number) that
    # rejects the two-attempt-1 shape outright.
    has_past_visit = s.status != CaseStatus.ACTIVE or s.failed_outcome is not None

    if not has_past_visit:
        next_start = _working_slot(ctx.now + timedelta(hours=s.upcoming_visit_in_hours))
        action_id = b.action_record("SCHEDULE_VISIT", at=triage_at + timedelta(hours=1.5), target_id=wo_id,
                                    proposal={"kind": "SCHEDULE_VISIT", "work_order_id": wo_id,
                                              "contractor_id": b.contractor.id})
        b.run(wo_created, summary=f"Book a {s.trade.value.lower()} visit with {b.contractor.display_name}.",
              started=triage_at + timedelta(minutes=4),
              action={"kind": "SCHEDULE_VISIT", "work_order_id": wo_id, "contractor_id": b.contractor.id,
                      "slot_id": f"{MARKER}:{s.key}:1", "tenant_availability_ids": []})
        appt_id = stable_id(f"appt:{s.key}:1")
        b.rows.append(
            AppointmentModel(
                id=appt_id, case_id=b.case_id, work_order_id=wo_id, contractor_id=b.contractor.id,
                slot_id=f"{MARKER}:{s.key}:1", start_at=next_start,
                end_at=next_start + timedelta(hours=2),
                status=AppointmentStatus.PENDING, visit_outcome=None,
                connector=ConnectorType.MOCK, provider_booking_id=None, action_id=action_id,
                attempt_number=1, availability_revision=1, provenance=Provenance.SIMULATED,
            )
        )
        b.event("APPOINTMENT_CONFIRMED", at=triage_at + timedelta(hours=1.5), actor_type="EXECUTOR",
                payload={"appointment_id": appt_id, "start_at": next_start.isoformat(),
                         "contractor_id": b.contractor.id, "attempt_number": 1})
        return b.rows

    # `attempt` tracks re-attendance so the second booking on a
    # failed-first-visit case is attempt 2, not another 1.
    attempt = 1
    booked_at = triage_at + timedelta(hours=1.5)
    # This visit already happened. It has to sit after the booking that
    # arranged it and early enough to leave room for the report, the
    # completion and the resolution that follow, so pick a slot inside
    # that window rather than rounding in one direction and hoping.
    first_visit_start = _slot_between(
        earliest=booked_at + timedelta(minutes=30),
        latest=end_at - timedelta(hours=5),
        preferred=b.created_at + timedelta(hours=max(s.duration_hours * 0.45, 6.0)),
    )
    action_id = b.action_record("SCHEDULE_VISIT", at=booked_at, target_id=wo_id,
                                proposal={"kind": "SCHEDULE_VISIT", "work_order_id": wo_id,
                                          "contractor_id": b.contractor.id})
    b.run(wo_created, summary=f"Book a {s.trade.value.lower()} visit with {b.contractor.display_name}.",
          started=triage_at + timedelta(minutes=4),
          action={"kind": "SCHEDULE_VISIT", "work_order_id": wo_id, "contractor_id": b.contractor.id,
                  "slot_id": f"{MARKER}:{s.key}:1", "tenant_availability_ids": []})

    appt_id = stable_id(f"appt:{s.key}:1")
    appt_ended = first_visit_start + timedelta(hours=2)
    b.rows.append(
        AppointmentModel(
            id=appt_id, case_id=b.case_id, work_order_id=wo_id, contractor_id=b.contractor.id,
            slot_id=f"{MARKER}:{s.key}:1", start_at=first_visit_start, end_at=appt_ended,
            status=AppointmentStatus.FINISHED,
            visit_outcome=s.failed_outcome or VisitOutcome.COMPLETED,
            connector=ConnectorType.MOCK, provider_booking_id=None, action_id=action_id,
            attempt_number=attempt, availability_revision=1, provenance=Provenance.SIMULATED,
        )
    )
    booked_event = b.event("APPOINTMENT_CONFIRMED", at=booked_at, actor_type="EXECUTOR",
                           payload={"appointment_id": appt_id, "start_at": first_visit_start.isoformat(),
                                    "contractor_id": b.contractor.id, "attempt_number": attempt})
    window_ended = b.event("APPOINTMENT_WINDOW_ENDED", at=appt_ended, actor_type="SYSTEM",
                           payload={"appointment_id": appt_id})

    # 4. The contractor reports back.
    report_at = appt_ended + timedelta(minutes=40)
    report_id = stable_id(f"report:{s.key}:1")
    b.rows.append(
        ContractorReportModel(
            id=report_id, case_id=b.case_id, work_order_id=wo_id, appointment_id=appt_id,
            contractor_id=b.contractor.id, text=s.report_text or "Attended as booked.",
            observed_at=appt_ended - timedelta(minutes=20), received_at=report_at,
            # Must be an EvidenceRef, not a free-form dict. `source_ref` is
            # revalidated as one by `ContractorReport.model_validate` inside
            # `services.load_case_snapshot`, so a wrong shape here does not
            # fail on write -- it fails later, as a 500 on the ticket detail
            # page for every case that has a report.
            source_ref=evidence_ref_dict(
                SourceType.REPORT, report_id, Provenance.SIMULATED,
                observed_at=appt_ended - timedelta(minutes=20),
            ),
            interpreted_action_id=None, interpretation_status="APPLIED",
            provenance=Provenance.SIMULATED,
        )
    )
    report_event = b.event("CONTRACTOR_REPORT_RECEIVED", at=report_at, actor_type="OPERATOR",
                           payload={"report_id": report_id, "work_order_id": wo_id,
                                    "outcome": (s.failed_outcome or VisitOutcome.COMPLETED).value})

    if s.status == CaseStatus.ESCALATED:
        b.run(report_event, summary=f"Escalate: {s.escalation_code}.",
              started=report_at + timedelta(minutes=6),
              action={"kind": "ESCALATE", "reason_code": s.escalation_code,
                      "evidence_refs": [], "operator_message": s.escalation_reason})
        b.event("CASE_ESCALATED", at=end_at, actor_type="COORDINATOR",
                payload={"reason_code": s.escalation_code, "message": s.escalation_reason})
        b.rows.append(_note(b, f"Escalated ({s.escalation_code}): {s.escalation_reason}"))
        return b.rows

    if s.status == CaseStatus.ACTIVE:
        # Only reachable with a failed first visit (the no-visit case
        # returned at step 3), so this is always a re-attend: attempt 2.
        next_start = _working_slot(ctx.now + timedelta(hours=s.upcoming_visit_in_hours))
        action2 = b.action_record("SCHEDULE_VISIT", at=ctx.now - timedelta(hours=4),
                                  target_id=f"{wo_id}:2",
                                  proposal={"kind": "SCHEDULE_VISIT", "work_order_id": wo_id,
                                            "contractor_id": b.contractor.id})
        appt2 = stable_id(f"appt:{s.key}:2")
        b.rows.append(
            AppointmentModel(
                id=appt2, case_id=b.case_id, work_order_id=wo_id, contractor_id=b.contractor.id,
                slot_id=f"{MARKER}:{s.key}:2", start_at=next_start,
                end_at=next_start + timedelta(hours=2),
                # PENDING, not CONFIRMED: nothing has acknowledged this
                # booking. Writing CONFIRMED would assert a contractor
                # acknowledgment that never happened (docs/26, 2026-09-21).
                status=AppointmentStatus.PENDING, visit_outcome=None,
                connector=ConnectorType.MOCK, provider_booking_id=None, action_id=action2,
                attempt_number=2, availability_revision=1, provenance=Provenance.SIMULATED,
            )
        )
        b.run(report_event, summary=f"Re-book with {b.contractor.display_name}.",
              started=ctx.now - timedelta(hours=4, minutes=6),
              action={"kind": "SCHEDULE_VISIT", "work_order_id": wo_id,
                      "contractor_id": b.contractor.id,
                      "slot_id": f"{MARKER}:{s.key}:2", "tenant_availability_ids": []})
        b.event("APPOINTMENT_CONFIRMED", at=ctx.now - timedelta(hours=4), actor_type="EXECUTOR",
                payload={"appointment_id": appt2, "start_at": next_start.isoformat(),
                         "contractor_id": b.contractor.id, "attempt_number": 2})
        return b.rows

    # 5. RESOLVED / AWAITING_CONFIRMATION: the work completed.
    work_order.completion_report_id = report_id
    completed_at = report_at + timedelta(hours=1.2)
    b.run(report_event, summary="Accept the completion report and close the work order.",
          started=report_at + timedelta(minutes=5),
          action={"kind": "ACCEPT_REPORT", "report_id": report_id, "outcome": "COMPLETED",
                  "completion_evidence_refs": []})
    completed = b.event("WORK_ORDER_COMPLETED", at=completed_at, actor_type="COORDINATOR",
                        payload={"work_order_id": wo_id, "report_id": report_id})
    b.rows.append(
        CostEntryModel(
            id=stable_id(f"cost:invoice:{s.key}"), case_id=b.case_id, work_order_id=wo_id,
            kind=CostKind.INVOICE, amount_pence=s.quote_pence,
            description=f"Invoiced: {s.scope}", incurred_at=completed_at,
            recorded_by=NOTE_AUTHOR, recorded_at=completed_at, archive_batch_id=None,
        )
    )

    confirm_at = completed_at + timedelta(hours=1.0)
    b.run(completed, summary="Ask the tenant to confirm the repair resolved the issue.",
          started=completed_at + timedelta(minutes=7),
          action={"kind": "REQUEST_CONFIRMATION", "issue_id": b.issue_id,
                  "questions": ["Has the issue you reported been resolved?"]})

    if s.status == CaseStatus.AWAITING_CONFIRMATION:
        b.rows.append(_note(b, "Work completed; waiting for the tenant to confirm the repair held."))
        return b.rows

    tenant_confirmed = b.event("TENANT_CONFIRMATION_RECEIVED", at=confirm_at, actor_type="OPERATOR",
                               payload={"issue_id": b.issue_id, "confirmed": True})
    b.run(tenant_confirmed, summary="Tenant confirmed the fix; resolve the case.",
          started=confirm_at + timedelta(minutes=5),
          action={"kind": "RESOLVE_CASE", "issue_id": b.issue_id,
                  "confirmation_event_id": tenant_confirmed.id})
    b.event("CASE_RESOLVED", at=end_at, actor_type="COORDINATOR", payload={"issue_id": b.issue_id})
    return b.rows


def _note(b: _CaseBuilder, body: str) -> NoteModel:
    return NoteModel(
        id=stable_id(f"note:{b.s.key}"),
        subject_type=RecordSubject.CASE,
        subject_id=b.case_id,
        body=f"{body}\n\n[Generated by {MARKER} v{GENERATOR_VERSION}; simulated activity, not a real visit.]",
        author=NOTE_AUTHOR,
        created_at=b.ctx.now - timedelta(hours=1),
        updated_at=b.ctx.now - timedelta(hours=1),
        archive_batch_id=None,
    )


# --------------------------------------------------------------------------
# Apply / remove / status / validate
# --------------------------------------------------------------------------


def _case_ids() -> list[str]:
    return [stable_id(f"case:{s.key}") for s in SCENARIOS]


async def _load_ctx(session: AsyncSession) -> _Ctx:
    props = list(
        (await session.execute(
            sa.select(PropertyModel).where(PropertyModel.archive_batch_id.is_(None)).order_by(PropertyModel.id)
        )).scalars()
    )
    tenants = list(
        (await session.execute(
            sa.select(TenantModel).where(TenantModel.archive_batch_id.is_(None)).order_by(TenantModel.id)
        )).scalars()
    )
    contractors = list(
        (await session.execute(
            sa.select(ContractorModel).where(ContractorModel.archive_batch_id.is_(None)).order_by(ContractorModel.id)
        )).scalars()
    )
    if not props or not tenants:
        raise RuntimeError("no operational properties/tenants; run `python -m app.seed` first")

    by_trade: dict[Trade, list[ContractorModel]] = {}
    for c in contractors:
        for t in c.trades or []:
            try:
                by_trade.setdefault(Trade(t), []).append(c)
            except ValueError:
                continue
    return _Ctx(properties=props, tenants=tenants, contractors_by_trade=by_trade,
                now=datetime.now(timezone.utc))


#: Insert order, parents first.
#:
#: `app.models` declares no `relationship()` at all -- every association is
#: a bare `ForeignKey` column. SQLAlchemy derives cross-mapper flush order
#: from relationships, so with none declared it will happily emit the
#: `action_records` INSERT before the `repair_cases` row it points at and
#: trip SQLite's foreign-key enforcement. `app.archive.importer` solves the
#: same problem the same way, with staged flushes; this is that list, made
#: explicit so a new model added to a scenario has an obvious home.
_INSERT_ORDER: tuple[type, ...] = (
    RepairCaseModel,        # parent of everything below
    RepairIssueModel,       # -> repair_cases
    WorkOrderModel,         # -> repair_cases, repair_issues
    ActionRecordModel,      # -> repair_cases        (before appointments: they hold action_id)
    AppointmentModel,       # -> work_orders, action_records
    CaseEventModel,         # -> repair_cases, and itself via causation_event_id
    ContractorReportModel,  # -> appointments, work_orders
    OrchestrationRunModel,  # -> case_events
    CostEntryModel,         # -> repair_cases, work_orders
    NoteModel,              # subject_id is not an FK, but keep it last anyway
)

_COUNT_KEY = {
    RepairCaseModel: "cases", RepairIssueModel: "issues", WorkOrderModel: "work_orders",
    ActionRecordModel: "actions", AppointmentModel: "appointments", CaseEventModel: "events",
    ContractorReportModel: "reports", OrchestrationRunModel: "runs",
    CostEntryModel: "costs", NoteModel: "notes",
}


async def apply(session: AsyncSession) -> dict[str, int]:
    existing = set(
        (await session.execute(
            sa.select(RepairCaseModel.id).where(RepairCaseModel.id.in_(_case_ids()))
        )).scalars()
    )
    ctx = await _load_ctx(session)
    highest = (await session.execute(sa.select(sa.func.max(RepairCaseModel.case_number)))).scalar() or 0
    counts: dict[str, int] = {k: 0 for k in _COUNT_KEY.values()}
    counts["skipped"] = 0

    for scenario in SCENARIOS:
        case_id = stable_id(f"case:{scenario.key}")
        if case_id in existing:
            counts["skipped"] += 1
            continue
        highest += 1
        rows = _build_case(scenario, ctx, highest)
        unknown = {type(r) for r in rows} - set(_INSERT_ORDER)
        if unknown:
            raise RuntimeError(f"no insert-order position for {sorted(m.__name__ for m in unknown)}")
        for model in _INSERT_ORDER:
            # Within one model the builder's order is preserved, which is
            # what keeps `causation_event_id` pointing at an event that
            # already exists.
            batch = [r for r in rows if type(r) is model]
            if not batch:
                continue
            for row in batch:
                session.add(row)
            await session.flush()
            counts[_COUNT_KEY[model]] += len(batch)
    return counts


async def remove(session: AsyncSession) -> dict[str, int]:
    """Delete every row this generator wrote, children first.

    Ordered by foreign key so SQLite never has to be told to defer a
    constraint. `appointments` before `action_records` matters: the
    appointment holds the FK.
    """
    ids = _case_ids()
    counts: dict[str, int] = {}
    for model in (OrchestrationRunModel, ContractorReportModel, AppointmentModel,
                  ActionRecordModel, CostEntryModel, CaseEventModel, WorkOrderModel,
                  RepairIssueModel):
        result = await session.execute(sa.delete(model).where(model.case_id.in_(ids)))
        counts[model.__tablename__] = result.rowcount or 0
    result = await session.execute(
        sa.delete(NoteModel).where(NoteModel.subject_id.in_(ids), NoteModel.author == NOTE_AUTHOR)
    )
    counts["notes"] = result.rowcount or 0
    result = await session.execute(sa.delete(RepairCaseModel).where(RepairCaseModel.id.in_(ids)))
    counts["repair_cases"] = result.rowcount or 0
    return counts


async def validate(session: AsyncSession) -> list[tuple[bool, str, str]]:
    """Programmatic checks, in the spirit of `app.archive --validate`.

    These are the invariants that, when broken, produce a UI that
    contradicts itself: a RESOLVED case with no resolution event, an
    average computed over zero samples, a case counted as operational that
    accidentally carries an archive tag.
    """
    out: list[tuple[bool, str, str]] = []

    def check(ok: bool, label: str, detail: str = "") -> None:
        out.append((bool(ok), label, detail))

    ids = _case_ids()
    cases = list((await session.execute(
        sa.select(RepairCaseModel).where(RepairCaseModel.id.in_(ids))
    )).scalars())
    check(len(cases) == len(SCENARIOS), "every scenario present",
          f"{len(cases)}/{len(SCENARIOS)}")
    check(all(c.archive_batch_id is None for c in cases), "all rows operational (no archive tag)")
    check(all(c.category is not None for c in cases), "every case categorised")

    now = datetime.now(timezone.utc)
    events = list((await session.execute(
        sa.select(CaseEventModel).where(CaseEventModel.case_id.in_(ids))
    )).scalars())
    by_case: dict[str, list[CaseEventModel]] = {}
    for e in events:
        by_case.setdefault(e.case_id, []).append(e)

    check(all(by_case.get(c.id) for c in cases), "every case has an event log")
    monotonic = all(
        [e.seq for e in sorted(evts, key=lambda x: x.seq)] == list(range(1, len(evts) + 1))
        for evts in by_case.values()
    )
    check(monotonic, "event seq is 1..n per case")
    ordered = all(
        all(a.occurred_at <= b.occurred_at for a, b in zip(sorted(evts, key=lambda x: x.seq), sorted(evts, key=lambda x: x.seq)[1:]))
        for evts in by_case.values()
    )
    check(ordered, "events never go backwards in time")
    check(all(e.occurred_at <= now for e in events), "no event is in the future")
    check(all(e.provenance == Provenance.SIMULATED for e in events),
          "every generated event is marked SIMULATED")

    resolved = [c for c in cases if c.status == CaseStatus.RESOLVED]
    with_resolution = [
        c for c in resolved
        if any(e.type == "CASE_RESOLVED" for e in by_case.get(c.id, []))
    ]
    check(len(resolved) == len(with_resolution), "every RESOLVED case has a CASE_RESOLVED event",
          f"{len(with_resolution)}/{len(resolved)}")

    week_ago = now - timedelta(days=7)
    this_week = [
        c for c in resolved
        if any(e.type == "CASE_RESOLVED" and e.occurred_at >= week_ago for e in by_case.get(c.id, []))
    ]
    check(len(this_week) >= 1, "at least one case resolved inside the 7-day window",
          f"{len(this_week)} case(s)")

    durations = []
    for c in resolved:
        ev = [e for e in by_case.get(c.id, []) if e.type == "CASE_RESOLVED"]
        if ev:
            durations.append((max(e.occurred_at for e in ev) - c.created_at).total_seconds() / 3600)
    check(all(d > 0 for d in durations), "no zero-length resolution",
          f"min={min(durations):.1f}h max={max(durations):.1f}h" if durations else "none")

    escalated = [c for c in cases if c.status == CaseStatus.ESCALATED]
    check(all(c.escalation_reason for c in escalated), "every ESCALATED case says why",
          f"{len(escalated)} case(s)")

    appts = list((await session.execute(
        sa.select(AppointmentModel).where(AppointmentModel.case_id.in_(ids))
    )).scalars())
    future_confirmed = [a for a in appts if a.start_at > now and a.status == AppointmentStatus.CONFIRMED]
    check(not future_confirmed,
          "no future appointment claims CONFIRMED without an acknowledgement",
          f"{len(future_confirmed)} offender(s)")
    check(all(a.provenance == Provenance.SIMULATED for a in appts),
          "every generated appointment is marked SIMULATED")

    open_cases = [c for c in cases if c.status == CaseStatus.ACTIVE]
    with_future = {a.case_id for a in appts if a.start_at > now}
    check(all(c.id in with_future for c in open_cases),
          "every ACTIVE case has a visit still to come",
          f"{len(with_future & {c.id for c in open_cases})}/{len(open_cases)}")

    # A generated case must never cause the worker to act.
    from app.models import JobModel  # local: keeps the module importable without the worker
    jobs = (await session.execute(
        sa.select(sa.func.count()).select_from(JobModel).where(JobModel.case_id.in_(ids))
    )).scalar_one()
    check(jobs == 0, "no jobs enqueued for generated cases", f"{jobs} job(s)")

    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


async def _cmd_status() -> int:
    async with session_scope() as session:
        present = list((await session.execute(
            sa.select(RepairCaseModel.case_number, RepairCaseModel.status)
            .where(RepairCaseModel.id.in_(_case_ids()))
            .order_by(RepairCaseModel.case_number)
        )).all())
    if not present:
        print(f"Sample operations '{MARKER}': not applied.")
        return 0
    print(f"Sample operations '{MARKER}': {len(present)}/{len(SCENARIOS)} case(s) present.")
    counts: dict[str, int] = {}
    for _, status in present:
        key = status.value if hasattr(status, "value") else str(status)
        counts[key] = counts.get(key, 0) + 1
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")
    return 0


async def _cmd_dry_run() -> int:
    async with session_scope() as session:
        ctx = await _load_ctx(session)
        existing = set((await session.execute(
            sa.select(RepairCaseModel.id).where(RepairCaseModel.id.in_(_case_ids()))
        )).scalars())
    print(f"Would write {len(SCENARIOS) - len(existing)} case(s) "
          f"({len(existing)} already present):")
    for s in SCENARIOS:
        mark = "skip" if stable_id(f"case:{s.key}") in existing else "new "
        when = ctx.now - timedelta(days=s.age_days)
        print(f"  [{mark}] {s.status.value:<22} {s.key}  reported {when:%Y-%m-%d}  "
              f"{s.trade.value:<12} {s.title[:44]}")
    return 0


async def _cmd_apply() -> int:
    async with session_scope() as session:
        counts = await apply(session)
    total = counts.pop("skipped", 0)
    print(f"Sample operations applied ({counts['cases']} new case(s), {total} already present).")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")
    return 0


async def _cmd_remove() -> int:
    async with session_scope() as session:
        counts = await remove(session)
    if not counts.get("repair_cases"):
        print(f"No '{MARKER}' cases found; nothing removed.")
        return 0
    print(f"Sample operations removed: {sum(counts.values())} row(s).")
    for k in sorted(counts):
        if counts[k]:
            print(f"  {k}: {counts[k]}")
    return 0


async def _cmd_validate() -> int:
    async with session_scope() as session:
        results = await validate(session)
    passed = sum(1 for ok, _, _ in results if ok)
    print(f"Validation for '{MARKER}': {passed}/{len(results)} checks passed.")
    for ok, label, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    return 0 if passed == len(results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Operational sample workload (open and recently-closed cases).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="write the sample cases (idempotent)")
    group.add_argument("--remove", action="store_true", help="delete every row this generator wrote")
    group.add_argument("--status", action="store_true", help="report what is currently applied")
    group.add_argument("--dry-run", action="store_true", help="list what --apply would write")
    group.add_argument("--validate", action="store_true", help="run every programmatic check")
    args = parser.parse_args()

    if args.apply:
        sys.exit(run_cli(_cmd_apply()))
    if args.remove:
        sys.exit(run_cli(_cmd_remove()))
    if args.status:
        sys.exit(run_cli(_cmd_status()))
    if args.dry_run:
        sys.exit(run_cli(_cmd_dry_run()))
    sys.exit(run_cli(_cmd_validate()))


if __name__ == "__main__":
    main()
