"""The single shared metric-definition module (CLAUDE.md: "Every number on
every screen must come from one place"). Every aggregate figure shown on
Overview, Insights, Reports (summary + CSV export) and Search is computed
here, once, as a pure-ish async query function taking `(session, **filters)`
and returning a plain dataclass. The routers in app/api/overview.py,
app/api/insights.py and app/api/reports.py are thin: they parse query
params, call functions in this module, and shape the response. A metric
must never be computed inline in a router -- that is what would let a
chart, a total, a detail table and a CSV export silently disagree.

--------------------------------------------------------------------------
THE ARCHIVAL RULE (models.py: RepairCaseModel.archive_batch_id and friends)
--------------------------------------------------------------------------
A row with a non-null `archive_batch_id` is synthetic archival history from
the sample-data import (see ArchiveBatchModel's docstring), not a real,
live case/cost/note/document.

- Operational figures (open cases, in-progress work, current workload,
  anything a person is expected to act on today) EXCLUDE archival rows
  unconditionally. These functions take no `include_archived` parameter --
  there is nothing to opt into. They may honestly return zero; that is
  never padded with archival rows to look more populated.
- Historical figures (resolved counts, average/median resolution time,
  spend by year, category mix, recurrence) MAY include archival rows, but
  only when the caller opts in via `include_archived: bool = True` (the
  historical default -- these views are more useful with the sample
  history included, but every payload that used it must say so). Callers
  that include archival rows must also report `archived_case_count`
  (see `archived_case_count` below) so the UI can label the scope honestly
  rather than silently blending real and synthetic numbers.

--------------------------------------------------------------------------
THE "QUOTED MONEY" RECONCILIATION RULE (docs/audit/06 Finding 1,
docs/audit/11 Finding 3, docs/26 2026-09-20)
--------------------------------------------------------------------------
There are two homes for a work order's quoted price: the
`WorkOrderModel.quote_pence` column (set automatically the moment policy
creates a work order; every operational case in this database has one and
NEVER gets a CostEntryModel row unless an operator opens the Costs tab) and
`CostEntryModel(kind=QUOTE)` rows (the append-only, editable, auditable
ledger the rest of the money model -- invoices, adjustments -- already
lives in exclusively). Nothing kept them in sync; Property Stats/History
read one, Insights/Reports/CSV read the other, and they disagreed on
screen (0p vs non-zero for every never-costed operational case; up to 3.4x
for archival cases whose importer only ever ledgered `work_orders[0]`).

`reconciled_quotes()` is the one function that decides, per work order,
which figure wins -- and it is now the ONLY place `WorkOrderModel.
quote_pence` is read for a "quoted" total anywhere in this codebase:

  * a work order with >=1 QUOTE CostEntryModel row of its own: use the sum
    of those rows (the ledger is authoritative once someone has logged a
    real number against this work order -- e.g. a requote).
  * a work order with none: fall back to its own `quote_pence` (this is
    what makes every existing operational case -- which has never been
    through the Costs tab -- show a correct, non-zero figure instead of a
    silent 0, with no migration/backfill required: it is computed live, so
    it can never go stale if quote_pence is edited later).
  * a CANCELLED work order never contributes, in either case (a called-off
    job's quote is money that will never be spent -- the same rule
    services._pick_primary_trade already applies for the identical
    reason).
  * a case-level QUOTE entry (CostEntryModel.work_order_id IS NULL, e.g. a
    site-visit estimate not tied to one trade) is always included verbatim
    -- there is no work order to reconcile it against.

Every screen that shows a "quoted" figure -- Property Stats/History
(app.api.cases's /history and /stats, computed here as
property_history_items/property_stats since domain/services.py is out of
scope for this change), the Costs tab (app.api.costs), and Insights/
Reports/CSV (case_detail_rows/spend_by_year below) -- now calls this one
function, which is what makes them reconcile instead of merely agreeing by
coincidence on today's data. One documented exception: property_stats/
property_history_items exclude case-level (work-order-less) QUOTE entries,
since neither has a trade to bucket them by and including them would break
that page's OWN chart/table self-consistency; Insights/Reports/CSV include
them (unchanged, pre-existing behaviour). No case in the current seed or
archive generator ever produces a case-level QUOTE entry, so this is a
documented, currently-inert edge case, not an active discrepancy.
"""
from __future__ import annotations

import dataclasses
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import services
from app.models import (
    ActionRecordModel,
    CaseEventModel,
    ContractorModel,
    CostEntryModel,
    PropertyModel,
    RepairCaseModel,
    TenantModel,
    WorkOrderModel,
)
from app.schemas import CaseStatus, CostKind, Trade, WorkOrderStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Case status predicates
# --------------------------------------------------------------------------

_CLOSED_STATUSES = {CaseStatus.RESOLVED, CaseStatus.CANCELLED}


def case_is_open(status: CaseStatus) -> bool:
    """True for ACTIVE, AWAITING_CONFIRMATION and ESCALATED: a case whose
    *current* status still represents outstanding work or a pending
    response. False for RESOLVED and CANCELLED.

    Note this is about current status, not state-machine reachability --
    transitions.py allows RESOLVED -> ESCALATED (a late reopen), so a
    RESOLVED case *can* become open again, but while it reads RESOLVED it
    is not open (docs/06 Resolution: "no outstanding required work").

    Deliberately a different, broader concept than the single-status
    "active" figure metrics.py's DashboardMetricsResponse and
    PropertyStatsResponse.active_count report (CaseStatus.ACTIVE literally,
    per that response's own "same strict reading ... not a broader open
    status" docstring) -- that strict count is reused as-is via
    `operational_status_counts` below rather than redefined here. This
    predicate exists for "is this case open at all" groupings such as
    `open_age_buckets`.
    """
    return status not in _CLOSED_STATUSES


def case_is_resolved(status: CaseStatus) -> bool:
    """True only for CaseStatus.RESOLVED: a verified-fixed outcome with no
    outstanding required work (docs/06 "Resolution"). CANCELLED is a
    different terminal state (the case was called off, not fixed) and is
    never counted as resolved."""
    return status == CaseStatus.RESOLVED


def case_is_waiting(status: CaseStatus) -> bool:
    """True only for CaseStatus.AWAITING_CONFIRMATION: the case is waiting
    on an external response (tenant confirmation) rather than on
    agent/operator action. ESCALATED is not "waiting" in this sense -- it
    needs a human decision now, so it is surfaced separately, under
    needs_attention."""
    return status == CaseStatus.AWAITING_CONFIRMATION


# --------------------------------------------------------------------------
# Shared filter helper
# --------------------------------------------------------------------------


def _apply_case_filters(
    query,
    *,
    property_id: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    include_archived: bool,
    category: Trade | None = None,
):
    """Applies the one shared set of RepairCaseModel filters (property,
    category, created_at window, archival inclusion) used by every
    case-grouping function below, so their filter semantics can never
    drift apart from each other."""
    if not include_archived:
        query = query.where(RepairCaseModel.archive_batch_id.is_(None))
    if property_id is not None:
        query = query.where(RepairCaseModel.property_id == property_id)
    if category is not None:
        query = query.where(RepairCaseModel.category == category)
    if date_from is not None:
        query = query.where(RepairCaseModel.created_at >= date_from)
    if date_to is not None:
        query = query.where(RepairCaseModel.created_at < date_to)
    return query


# --------------------------------------------------------------------------
# Operational: portfolio counts, status counts, needs-attention, activity
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PortfolioCounts:
    property_count: int
    tenant_count: int
    approved_contractor_count: int


async def portfolio_counts(session: AsyncSession) -> PortfolioCounts:
    """Portfolio-size figures for Overview. Operational scope: a property
    created by the archive import (PropertyModel.archive_batch_id set) is
    not a real managed property, so it -- and any tenant only linked to
    it -- is excluded. Contractors have no archive_batch_id column (the
    import never fabricates contractor rows), so `approved_contractor_count`
    needs no such filter; it is simply every ContractorModel currently
    APPROVED.
    """
    property_count = (
        await session.execute(
            select(func.count()).select_from(PropertyModel).where(PropertyModel.archive_batch_id.is_(None))
        )
    ).scalar_one()
    tenant_count = (
        await session.execute(
            select(func.count())
            .select_from(TenantModel)
            .join(PropertyModel, PropertyModel.id == TenantModel.property_id)
            .where(PropertyModel.archive_batch_id.is_(None))
        )
    ).scalar_one()
    approved_contractor_count = (
        await session.execute(
            select(func.count()).select_from(ContractorModel).where(ContractorModel.approval_status == "APPROVED")
        )
    ).scalar_one()
    return PortfolioCounts(
        property_count=property_count, tenant_count=tenant_count,
        approved_contractor_count=approved_contractor_count,
    )


@dataclasses.dataclass(frozen=True)
class StatusCounts:
    active: int
    awaiting_confirmation: int
    resolved: int
    escalated: int
    cancelled: int
    total: int


async def operational_status_counts(session: AsyncSession) -> StatusCounts:
    """Per-status case counts, operational scope only (archive_batch_id IS
    NULL, unconditionally -- there is no include_archived escape hatch on
    an operational function). Same 5-value CaseStatus breakdown as
    metrics.py's DashboardMetricsResponse, recomputed the same way (not
    imported from there, since metrics.py is a separate, frozen endpoint)
    so the two can never disagree about what "active" etc. mean.
    """
    rows = (
        await session.execute(
            select(RepairCaseModel.status, func.count())
            .where(RepairCaseModel.archive_batch_id.is_(None))
            .group_by(RepairCaseModel.status)
        )
    ).all()
    counts = {status.value: 0 for status in CaseStatus}
    for status, count in rows:
        counts[status.value if hasattr(status, "value") else status] = count
    return StatusCounts(
        active=counts[CaseStatus.ACTIVE.value],
        awaiting_confirmation=counts[CaseStatus.AWAITING_CONFIRMATION.value],
        resolved=counts[CaseStatus.RESOLVED.value],
        escalated=counts[CaseStatus.ESCALATED.value],
        cancelled=counts[CaseStatus.CANCELLED.value],
        total=sum(counts.values()),
    )


@dataclasses.dataclass(frozen=True)
class AttentionItem:
    case_id: str
    case_number: int
    case_title: str
    reason: str  # "AWAITING_APPROVAL" | "ESCALATED" | "OVERDUE_FOLLOW_UP"
    detail: str
    occurred_at: datetime


async def needs_attention(session: AsyncSession, *, limit: int = 20) -> list[AttentionItem]:
    """Cases needing a person's attention today: an action awaiting
    approval, a case currently ESCALATED, or a case whose next_follow_up_at
    has passed and hasn't been closed out. Operational scope only -- every
    branch filters archive_batch_id IS NULL explicitly (belt-and-braces:
    an archival case can never actually have a pending ActionRecord or a
    live next_follow_up_at, but the filter keeps that true by construction
    rather than by accident of current data shape).
    """
    items: list[AttentionItem] = []

    pending = (
        await session.execute(
            select(ActionRecordModel, RepairCaseModel.case_number, RepairCaseModel.title)
            .join(RepairCaseModel, RepairCaseModel.id == ActionRecordModel.case_id)
            .where(ActionRecordModel.state == "AWAITING_APPROVAL", RepairCaseModel.archive_batch_id.is_(None))
            .order_by(ActionRecordModel.updated_at.desc())
            .limit(limit)
        )
    ).all()
    for action, case_number, title in pending:
        proposal = action.proposal or {}
        items.append(
            AttentionItem(
                case_id=action.case_id, case_number=case_number, case_title=title,
                reason="AWAITING_APPROVAL",
                detail=proposal.get("decision_summary") or f"{action.kind} awaiting approval",
                occurred_at=action.updated_at,
            )
        )

    escalated = (
        await session.execute(
            select(RepairCaseModel)
            .where(RepairCaseModel.status == CaseStatus.ESCALATED, RepairCaseModel.archive_batch_id.is_(None))
            .order_by(RepairCaseModel.updated_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    for case in escalated:
        items.append(
            AttentionItem(
                case_id=case.id, case_number=case.case_number, case_title=case.title,
                reason="ESCALATED", detail=case.escalation_reason or "Case escalated",
                occurred_at=case.updated_at,
            )
        )

    now = utcnow()
    overdue = (
        await session.execute(
            select(RepairCaseModel)
            .where(
                RepairCaseModel.next_follow_up_at.is_not(None),
                RepairCaseModel.next_follow_up_at < now,
                RepairCaseModel.archive_batch_id.is_(None),
                RepairCaseModel.status.notin_([CaseStatus.RESOLVED, CaseStatus.CANCELLED]),
            )
            .order_by(RepairCaseModel.next_follow_up_at.asc())
            .limit(limit)
        )
    ).scalars().all()
    for case in overdue:
        items.append(
            AttentionItem(
                case_id=case.id, case_number=case.case_number, case_title=case.title,
                reason="OVERDUE_FOLLOW_UP",
                detail=f"Follow-up was due {case.next_follow_up_at.isoformat()}",
                occurred_at=case.next_follow_up_at,
            )
        )

    return items


@dataclasses.dataclass(frozen=True)
class ActivityItem:
    event_id: str
    case_id: str
    case_number: int
    case_title: str
    event_type: str
    occurred_at: datetime


async def recent_activity(session: AsyncSession, *, limit: int = 20) -> list[ActivityItem]:
    """Latest CaseEventModel rows across every case, newest first, for
    Overview's activity feed. Operational scope: the archive import writes
    closed history directly (never through services.append_event), so
    archival cases naturally have no CaseEvent rows -- the archive_batch_id
    filter is included anyway so this stays true even if that changes."""
    rows = (
        await session.execute(
            select(CaseEventModel, RepairCaseModel.case_number, RepairCaseModel.title)
            .join(RepairCaseModel, RepairCaseModel.id == CaseEventModel.case_id)
            .where(RepairCaseModel.archive_batch_id.is_(None))
            .order_by(CaseEventModel.occurred_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        ActivityItem(
            event_id=event.id, case_id=event.case_id, case_number=case_number, case_title=title,
            event_type=event.type, occurred_at=event.occurred_at,
        )
        for event, case_number, title in rows
    ]


@dataclasses.dataclass(frozen=True)
class OpenAgeBucket:
    label: str
    count: int


_AGE_BUCKETS: list[tuple[str, float, float | None]] = [
    ("0-3 days", 0, 3),
    ("4-7 days", 4, 7),
    ("8-14 days", 8, 14),
    ("15-30 days", 15, 30),
    ("30+ days", 31, None),
]


async def open_age_buckets(session: AsyncSession, *, property_id: str | None = None) -> list[OpenAgeBucket]:
    """Age (whole days since created_at) of every currently-open case
    (case_is_open), bucketed. Operational scope only: an archival case is
    never "open" today (it is closed history), so archive_batch_id IS NULL
    unconditionally and there is no include_archived parameter."""
    query = select(RepairCaseModel.status, RepairCaseModel.created_at).where(
        RepairCaseModel.archive_batch_id.is_(None)
    )
    if property_id is not None:
        query = query.where(RepairCaseModel.property_id == property_id)
    rows = (await session.execute(query)).all()

    now = utcnow()
    bucket_counts = [0 for _ in _AGE_BUCKETS]
    for status, created_at in rows:
        if not case_is_open(status):
            continue
        age_days = (now - created_at).total_seconds() / 86400
        for i, (_label, lo, hi) in enumerate(_AGE_BUCKETS):
            if age_days >= lo and (hi is None or age_days <= hi):
                bucket_counts[i] += 1
                break
    return [OpenAgeBucket(label=label, count=count) for (label, _lo, _hi), count in zip(_AGE_BUCKETS, bucket_counts)]


# --------------------------------------------------------------------------
# Historical: resolution time, spend, category mix, recurrence, volume
# --------------------------------------------------------------------------


async def archived_case_count(
    session: AsyncSession, *, property_id: str | None = None, category: Trade | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None,
) -> int:
    """Count of archival cases matching the same filters as a historical
    query. Every response that sets includes_archived_history=True must
    also carry this, so the UI can say exactly how many of the cases behind
    a number are synthetic sample history rather than blending them in
    silently."""
    query = select(func.count()).select_from(RepairCaseModel).where(RepairCaseModel.archive_batch_id.is_not(None))
    if property_id is not None:
        query = query.where(RepairCaseModel.property_id == property_id)
    if category is not None:
        query = query.where(RepairCaseModel.category == category)
    if date_from is not None:
        query = query.where(RepairCaseModel.created_at >= date_from)
    if date_to is not None:
        query = query.where(RepairCaseModel.created_at < date_to)
    return (await session.execute(query)).scalar_one()


async def _terminal_event_at_by_case(session: AsyncSession, case_ids: list[str]) -> dict[str, datetime]:
    """Latest CASE_RESOLVED/CASE_CANCELLED CaseEvent.occurred_at per case
    id, for real (non-archival) cases only. Takes MAX per case: a
    resolved-then-reopened-then-resolved-again case can have more than one
    such event, and the most recent is the one that matches its *current*
    closed status."""
    if not case_ids:
        return {}
    rows = (
        await session.execute(
            select(CaseEventModel.case_id, func.max(CaseEventModel.occurred_at))
            .where(CaseEventModel.case_id.in_(case_ids), CaseEventModel.type.in_(["CASE_RESOLVED", "CASE_CANCELLED"]))
            .group_by(CaseEventModel.case_id)
        )
    ).all()
    return {case_id: occurred_at for case_id, occurred_at in rows if occurred_at is not None}


@dataclasses.dataclass(frozen=True)
class ResolutionInputs:
    """Exactly the fields resolution_hours() needs, bundled so the
    calculation itself is a pure function testable without a session.
    Callers build this from a RepairCaseModel row plus a terminal-event
    lookup (see _terminal_event_at_by_case)."""

    case_id: str
    created_at: datetime
    archive_batch_id: str | None
    archived_closed_at: datetime | None
    terminal_event_at: datetime | None
    updated_at: datetime


def resolution_hours(case: ResolutionInputs) -> float | None:
    """Hours between a case's created_at and its close.

    - Archival case (archive_batch_id is not None): archived_closed_at -
      created_at. Archival rows have no CaseEvent stream to read (see
      RepairCaseModel.archived_closed_at's docstring), so this is the only
      source of a close time for them.
    - Real case: the occurred_at of its terminal CaseEvent (CASE_RESOLVED
      or CASE_CANCELLED, whichever is later), falling back to updated_at
      when no terminal event is on record.

    Never negative. A negative duration means bad data (clock skew, a
    malformed archival row, ...) -- clamping it to zero would silently
    understate an average, so instead the case is excluded here (returns
    None); callers that aggregate over several cases must count a None as
    `skipped`, not as zero.
    """
    if case.archive_batch_id is not None:
        end = case.archived_closed_at
    else:
        end = case.terminal_event_at or case.updated_at
    if end is None:
        return None
    hours = (end - case.created_at).total_seconds() / 3600
    if hours < 0:
        return None
    return round(hours, 2)


@dataclasses.dataclass(frozen=True)
class ReconciledQuote:
    """One quoted-money contribution after reconciling CostEntryModel
    against WorkOrderModel.quote_pence -- see this module's docstring,
    "THE QUOTED MONEY RECONCILIATION RULE". `occurred_at` is the cost
    entry's own `incurred_at` when `from_cost_entry` is True, else the
    work order's `created_at` (the best available proxy for "when this
    figure came into being" when there is no ledger row to date it by)."""

    case_id: str
    work_order_id: str | None
    trade: Trade | None
    occurred_at: datetime
    quoted_pence: int
    from_cost_entry: bool


async def reconciled_quotes(session: AsyncSession, case_ids: list[str]) -> list[ReconciledQuote]:
    """THE quoted-money reconciliation rule, batched over a set of cases.
    Per live (non-CANCELLED) work order: its own QUOTE CostEntryModel
    row(s) if any exist, else its own `quote_pence` (never both -- this is
    what prevents double counting). Case-level QUOTE entries
    (work_order_id IS NULL) are always included on top, verbatim. See the
    module docstring for the full rationale; every "quoted" figure in this
    codebase should be built from this function's output, not from
    WorkOrderModel.quote_pence or CostEntryModel directly.
    """
    if not case_ids:
        return []
    work_orders = (
        await session.execute(select(WorkOrderModel).where(WorkOrderModel.case_id.in_(case_ids)))
    ).scalars().all()
    live_by_id = {wo.id: wo for wo in work_orders if wo.status != WorkOrderStatus.CANCELLED}

    cost_rows = (
        await session.execute(
            select(CostEntryModel).where(
                CostEntryModel.case_id.in_(case_ids), CostEntryModel.kind == CostKind.QUOTE,
            )
        )
    ).scalars().all()
    by_work_order: dict[str, list[CostEntryModel]] = defaultdict(list)
    case_level: list[CostEntryModel] = []
    for entry in cost_rows:
        if entry.work_order_id is not None:
            by_work_order[entry.work_order_id].append(entry)
        else:
            case_level.append(entry)

    result: list[ReconciledQuote] = []
    for wo_id, wo in live_by_id.items():
        entries = by_work_order.get(wo_id)
        if entries:
            for entry in entries:
                result.append(
                    ReconciledQuote(
                        case_id=wo.case_id, work_order_id=wo_id, trade=wo.trade,
                        occurred_at=entry.incurred_at, quoted_pence=entry.amount_pence, from_cost_entry=True,
                    )
                )
        elif wo.quote_pence is not None:
            result.append(
                ReconciledQuote(
                    case_id=wo.case_id, work_order_id=wo_id, trade=wo.trade,
                    occurred_at=wo.created_at, quoted_pence=wo.quote_pence, from_cost_entry=False,
                )
            )
    for entry in case_level:
        result.append(
            ReconciledQuote(
                case_id=entry.case_id, work_order_id=None, trade=None,
                occurred_at=entry.incurred_at, quoted_pence=entry.amount_pence, from_cost_entry=True,
            )
        )
    return result


@dataclasses.dataclass(frozen=True)
class YearSpend:
    year: int
    quoted_pence: int
    actual_pence: int


async def spend_by_year(
    session: AsyncSession, *, property_id: str | None = None, category: Trade | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None, include_archived: bool = True,
) -> list[YearSpend]:
    """Money grouped by calendar year (integer pence throughout -- see
    CostEntryModel's docstring on why no float ever touches money here).
    Returns `quoted_pence` and `actual_pence` as two separate figures per
    year -- never summed into one "spend" number, since a quote and an
    invoice answer different questions.

    `quoted_pence` comes from `reconciled_quotes()` (see this module's
    docstring), bucketed by each contribution's `occurred_at` year.
    `actual_pence` sums CostKind.INVOICE rows plus CostKind.ADJUSTMENT
    rows, unchanged -- there is no WorkOrderModel equivalent for "actual"
    money, so there is nothing to reconcile on that side. Judgment call (no
    field distinguishes an adjustment to a quote from one to an invoice):
    an ADJUSTMENT is treated as a correction to real billed money, which
    keeps `quoted_pence` an honest read of original estimates only.

    Case selection (property_id/category/include_archived) matches
    `_apply_case_filters` minus the date window -- `date_from`/`date_to`
    are applied to each contribution's own `occurred_at`, not the case's
    `created_at`, because spend has its own timeline (unchanged from this
    function's pre-reconciliation behaviour).
    """
    case_query = select(RepairCaseModel.id)
    case_query = _apply_case_filters(
        case_query, property_id=property_id, date_from=None, date_to=None,
        include_archived=include_archived, category=category,
    )
    case_ids = list((await session.execute(case_query)).scalars().all())

    quoted: dict[int, int] = defaultdict(int)
    for contribution in await reconciled_quotes(session, case_ids):
        if date_from is not None and contribution.occurred_at < date_from:
            continue
        if date_to is not None and contribution.occurred_at >= date_to:
            continue
        quoted[contribution.occurred_at.year] += contribution.quoted_pence

    actual_query = select(CostEntryModel.incurred_at, CostEntryModel.amount_pence).where(
        CostEntryModel.kind.in_([CostKind.INVOICE, CostKind.ADJUSTMENT])
    )
    if property_id is not None or category is not None:
        actual_query = actual_query.select_from(CostEntryModel).join(
            RepairCaseModel, RepairCaseModel.id == CostEntryModel.case_id
        )
        if property_id is not None:
            actual_query = actual_query.where(RepairCaseModel.property_id == property_id)
        if category is not None:
            actual_query = actual_query.where(RepairCaseModel.category == category)
    if not include_archived:
        actual_query = actual_query.where(CostEntryModel.archive_batch_id.is_(None))
    if date_from is not None:
        actual_query = actual_query.where(CostEntryModel.incurred_at >= date_from)
    if date_to is not None:
        actual_query = actual_query.where(CostEntryModel.incurred_at < date_to)

    actual: dict[int, int] = defaultdict(int)
    for incurred_at, amount in (await session.execute(actual_query)).all():
        actual[incurred_at.year] += amount

    years = sorted(set(quoted) | set(actual))
    return [YearSpend(year=y, quoted_pence=quoted.get(y, 0), actual_pence=actual.get(y, 0)) for y in years]


def _largest_remainder_percentages(counts: list[int]) -> list[int]:
    """Integer percentages that always sum to exactly 100 (when the total is
    > 0), using the largest-remainder (Hare quota) method. Plain
    independent `round(count / total * 100)` can overshoot or undershoot
    100 -- the bug this replaces printed 52% + 49% = 101% on a real
    category split. Ties in the remainder are broken by original list
    order (stable): deterministic, and there is no product requirement for
    a fancier tie-break. Returns all zeros when the total is 0.
    """
    total = sum(counts)
    if total == 0:
        return [0 for _ in counts]
    raw = [c / total * 100 for c in counts]
    floors = [int(r) for r in raw]
    remainder = 100 - sum(floors)
    order = sorted(range(len(counts)), key=lambda i: (raw[i] - floors[i]), reverse=True)
    result = floors[:]
    for i in order[:remainder]:
        result[i] += 1
    return result


@dataclasses.dataclass(frozen=True)
class CategoryCount:
    category: Trade | None
    count: int
    percentage: int


async def category_breakdown(
    session: AsyncSession, *, property_id: str | None = None, date_from: datetime | None = None,
    date_to: datetime | None = None, include_archived: bool = True,
) -> list[CategoryCount]:
    """Count of RepairCaseModel rows by `category` (a Trade) -- explicitly
    NOT by work-order trade (one case can spawn several differently-traded
    work orders; `category` is the single classification a case carries
    for its whole life -- see RepairCaseModel.category's docstring) and NOT
    weighted by cost. A case with category=None (triage hasn't run yet) is
    grouped under category=None rather than dropped, so the percentages
    describe the whole matched case set, not a subset of it. Sorted by
    count descending; percentages are integers summing to exactly 100 (see
    _largest_remainder_percentages).
    """
    query = (
        select(RepairCaseModel.category, func.count())
        .group_by(RepairCaseModel.category)
        # Deterministic tie-break: group by count descending (below), but
        # among equal counts always break ties the same way -- alphabetical
        # by category -- rather than leaving it to SQLite's unspecified
        # GROUP BY row order, which a test (or a user re-running the same
        # report) should never see change.
        .order_by(RepairCaseModel.category)
    )
    query = _apply_case_filters(
        query, property_id=property_id, date_from=date_from, date_to=date_to, include_archived=include_archived,
    )
    rows = (await session.execute(query)).all()
    rows = sorted(rows, key=lambda r: r[1], reverse=True)
    counts = [count for _, count in rows]
    percentages = _largest_remainder_percentages(counts)
    return [
        CategoryCount(category=category, count=count, percentage=pct)
        for (category, count), pct in zip(rows, percentages)
    ]


@dataclasses.dataclass(frozen=True)
class RecurringIssueGroup:
    property_id: str
    property_address: str
    category: Trade
    count: int
    last_occurred_at: datetime
    case_ids: list[str]


async def recurring_issues(
    session: AsyncSession, *, property_id: str | None = None, date_from: datetime | None = None,
    date_to: datetime | None = None, include_archived: bool = True, min_count: int = 2,
) -> list[RecurringIssueGroup]:
    """Groups cases by (property_id, category) with count >= min_count
    (default 2: "recurring" means it has happened more than once at the
    same property, in the same category). Cases with category=None are
    excluded -- "recurring category" is meaningless without one. Returns
    the contributing case ids per group so the UI can drill down to the
    actual cases behind a recurrence, not just a number. Sorted by most
    recent occurrence first.
    """
    query = (
        select(RepairCaseModel.id, RepairCaseModel.property_id, RepairCaseModel.category,
               RepairCaseModel.created_at, PropertyModel.address_line)
        .join(PropertyModel, PropertyModel.id == RepairCaseModel.property_id)
        .where(RepairCaseModel.category.is_not(None))
    )
    query = _apply_case_filters(
        query, property_id=property_id, date_from=date_from, date_to=date_to, include_archived=include_archived,
    )
    rows = (await session.execute(query)).all()

    groups: dict[tuple[str, Trade], list[tuple[str, datetime, str]]] = defaultdict(list)
    for case_id, prop_id, category, created_at, address in rows:
        groups[(prop_id, category)].append((case_id, created_at, address))

    result: list[RecurringIssueGroup] = []
    for (prop_id, category), items in groups.items():
        if len(items) < min_count:
            continue
        result.append(
            RecurringIssueGroup(
                property_id=prop_id, property_address=items[0][2], category=category,
                count=len(items), last_occurred_at=max(i[1] for i in items),
                case_ids=[i[0] for i in items],
            )
        )
    result.sort(key=lambda g: g.last_occurred_at, reverse=True)
    return result


_RESOLUTION_BUCKETS: list[tuple[str, float, float | None]] = [
    ("< 24h", 0, 24),
    ("1-3 days", 24, 72),
    ("3-7 days", 72, 168),
    ("1-2 weeks", 168, 336),
    ("> 2 weeks", 336, None),
]


def resolution_bucket_bounds() -> list[tuple[str, float, float | None]]:
    """The bucket edges, in hours, so a caller can express "cases in this
    bucket" as a real filter instead of re-deriving the boundaries from
    the labels. Returning them beats publishing only labels and letting
    the UI keep a second copy of this table that silently goes stale."""
    return list(_RESOLUTION_BUCKETS)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return round(ordered[mid], 2)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 2)


@dataclasses.dataclass(frozen=True)
class ResolutionTimeDistribution:
    buckets: list[tuple[str, int]]
    average_hours: float | None
    median_hours: float | None
    sample_count: int
    skipped_count: int


async def resolution_time_distribution(
    session: AsyncSession, *, property_id: str | None = None, category: Trade | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None, include_archived: bool = True,
) -> ResolutionTimeDistribution:
    """Distribution of resolution_hours() across currently-RESOLVED cases
    (plus, when include_archived, archival cases with a recorded
    archived_closed_at) matching the filters. `skipped_count` is the number
    of matched cases whose resolution_hours() came back None (a negative
    duration was excluded rather than clamped -- see that function's
    docstring); `sample_count` is the number that actually contributed to
    the buckets/average/median.
    """
    where_clause = RepairCaseModel.status == CaseStatus.RESOLVED
    if include_archived:
        where_clause = where_clause | (
            (RepairCaseModel.archive_batch_id.is_not(None)) & (RepairCaseModel.archived_closed_at.is_not(None))
        )
    query = select(RepairCaseModel).where(where_clause)
    query = _apply_case_filters(
        query, property_id=property_id, date_from=date_from, date_to=date_to,
        include_archived=include_archived, category=category,
    )
    cases = (await session.execute(query)).scalars().all()

    real_case_ids = [c.id for c in cases if c.archive_batch_id is None]
    terminal_map = await _terminal_event_at_by_case(session, real_case_ids)

    hours_list: list[float] = []
    skipped = 0
    for case in cases:
        inputs = ResolutionInputs(
            case_id=case.id, created_at=case.created_at, archive_batch_id=case.archive_batch_id,
            archived_closed_at=case.archived_closed_at, terminal_event_at=terminal_map.get(case.id),
            updated_at=case.updated_at,
        )
        hours = resolution_hours(inputs)
        if hours is None:
            skipped += 1
            continue
        hours_list.append(hours)

    bucket_counts = [0 for _ in _RESOLUTION_BUCKETS]
    for hours in hours_list:
        for i, (_label, lo, hi) in enumerate(_RESOLUTION_BUCKETS):
            if hours >= lo and (hi is None or hours < hi):
                bucket_counts[i] += 1
                break
    buckets = [(label, count) for (label, _lo, _hi), count in zip(_RESOLUTION_BUCKETS, bucket_counts)]

    average = round(sum(hours_list) / len(hours_list), 2) if hours_list else None
    return ResolutionTimeDistribution(
        buckets=buckets, average_hours=average, median_hours=_median(hours_list),
        sample_count=len(hours_list), skipped_count=skipped,
    )


@dataclasses.dataclass(frozen=True)
class MonthVolume:
    year: int
    month: int
    count: int


async def case_volume_by_month(
    session: AsyncSession, *, property_id: str | None = None, category: Trade | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None, include_archived: bool = True,
) -> list[MonthVolume]:
    """Case count grouped by calendar month of `created_at` (when a case
    was opened -- volume should reflect incoming demand, not when it later
    closed). Grouped in Python rather than with a SQL DATE_TRUNC/strftime
    expression so the same code path works identically against the
    in-memory test engine and the file-backed production one."""
    query = select(RepairCaseModel.created_at)
    query = _apply_case_filters(
        query, property_id=property_id, date_from=date_from, date_to=date_to,
        include_archived=include_archived, category=category,
    )
    rows = (await session.execute(query)).scalars().all()
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for created_at in rows:
        counts[(created_at.year, created_at.month)] += 1
    return [MonthVolume(year=y, month=m, count=c) for (y, m), c in sorted(counts.items())]


@dataclasses.dataclass(frozen=True)
class CaseDetailRow:
    """One row behind a chart/summary/CSV figure. This is the single
    row-level query used by Insights' drill-down (`/insights/cases`),
    Reports' summary detail tables (`/reports/summary`) and the CSV export
    (`/reports/export.csv`) -- they all call `case_detail_rows` with the
    same filters, which is what makes them reconcile exactly instead of
    each re-deriving the same numbers slightly differently.
    """

    case_id: str
    case_number: int
    title: str
    status: CaseStatus
    category: Trade | None
    property_id: str
    property_address: str
    created_at: datetime
    closed_at: datetime | None
    resolution_hours: float | None
    quoted_pence: int
    invoiced_pence: int
    contractor_name: str | None
    is_archived: bool


async def case_detail_rows(
    session: AsyncSession, *, property_id: str | None = None, category: Trade | None = None,
    status: CaseStatus | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
    include_archived: bool = True, limit: int | None = None,
) -> list[CaseDetailRow]:
    """Row-level case data backing every drill-down/detail table/export.
    `quoted_pence` is this case's total from `reconciled_quotes()` (see
    this module's docstring); `invoiced_pence` is this case's own
    CostEntryModel INVOICE+ADJUSTMENT total, unchanged (same split as
    spend_by_year -- there is no WorkOrderModel equivalent for "actual"
    money to reconcile). `resolution_hours`/`closed_at` are populated only
    for a case that is currently RESOLVED or is archival
    (case_is_resolved(status) or is_archived), matching
    resolution_time_distribution's inclusion rule -- a reopened case that
    was once RESOLVED shows neither, since it is not closed right now.
    """
    query = (
        select(RepairCaseModel, PropertyModel.address_line)
        .join(PropertyModel, PropertyModel.id == RepairCaseModel.property_id)
    )
    query = _apply_case_filters(
        query, property_id=property_id, date_from=date_from, date_to=date_to,
        include_archived=include_archived, category=category,
    )
    if status is not None:
        query = query.where(RepairCaseModel.status == status)
    query = query.order_by(RepairCaseModel.created_at.desc())
    if limit is not None:
        query = query.limit(limit)
    rows = (await session.execute(query)).all()
    cases = [c for c, _ in rows]
    case_ids = [c.id for c in cases]

    real_case_ids = [c.id for c in cases if c.archive_batch_id is None]
    terminal_map = await _terminal_event_at_by_case(session, real_case_ids)

    quoted_by_case: dict[str, int] = defaultdict(int)
    invoiced_by_case: dict[str, int] = defaultdict(int)
    if case_ids:
        for contribution in await reconciled_quotes(session, case_ids):
            quoted_by_case[contribution.case_id] += contribution.quoted_pence

        invoice_rows = (
            await session.execute(
                select(CostEntryModel.case_id, func.sum(CostEntryModel.amount_pence))
                .where(
                    CostEntryModel.case_id.in_(case_ids),
                    CostEntryModel.kind.in_([CostKind.INVOICE, CostKind.ADJUSTMENT]),
                )
                .group_by(CostEntryModel.case_id)
            )
        ).all()
        for case_id, total in invoice_rows:
            invoiced_by_case[case_id] += total or 0

    contractors_by_case = await services.assigned_contractors_for_cases(session, case_ids) if case_ids else {}

    result: list[CaseDetailRow] = []
    for case, address in rows:
        is_archived = case.archive_batch_id is not None
        closed_and_resolved = is_archived or case_is_resolved(case.status)
        if is_archived:
            closed_at = case.archived_closed_at
        elif closed_and_resolved:
            closed_at = terminal_map.get(case.id)
        else:
            closed_at = None

        hours = None
        if closed_and_resolved:
            inputs = ResolutionInputs(
                case_id=case.id, created_at=case.created_at, archive_batch_id=case.archive_batch_id,
                archived_closed_at=case.archived_closed_at, terminal_event_at=terminal_map.get(case.id),
                updated_at=case.updated_at,
            )
            hours = resolution_hours(inputs)

        contractor = contractors_by_case.get(case.id)
        result.append(
            CaseDetailRow(
                case_id=case.id, case_number=case.case_number, title=case.title, status=case.status,
                category=case.category, property_id=case.property_id, property_address=address,
                created_at=case.created_at, closed_at=closed_at, resolution_hours=hours,
                quoted_pence=quoted_by_case.get(case.id, 0), invoiced_pence=invoiced_by_case.get(case.id, 0),
                contractor_name=contractor.display_name if contractor else None, is_archived=is_archived,
            )
        )
    return result


# --------------------------------------------------------------------------
# Property History / Stats (app.api.cases's GET /properties/{id}/history
# and /stats). These live here rather than in app/domain/services.py --
# where their original, quote_pence-only implementations still exist as
# dead code, since that directory was out of scope for this change (see
# docs/26 2026-09-20) -- specifically so their "quoted" figures share
# reconciled_quotes() with everything else in this module instead of
# re-deriving money from WorkOrderModel.quote_pence a third way.
# --------------------------------------------------------------------------


async def property_history_items(session: AsyncSession, property_id: str) -> list["PropertyHistoryItem"]:
    """Property History screen: past (and current) cases for a property,
    each with an honest `outcome` when one is grounded in real data --
    never a fabricated summary. `contractor_name`/`trade` reuse the exact
    same selection rules the case-list endpoint uses
    (services.assigned_contractors_for_cases/services._pick_primary_trade)
    so this view can't disagree with those about "which trade"/"which
    contractor". `quoted_pence` is this module's reconciled figure
    (reconciled_quotes), restricted to work-order-backed contributions --
    see this module's docstring for why a case-level, work-order-less
    QUOTE entry is excluded here (keeps this page's own chart/table
    mutually consistent; not currently reachable with real data).
    """
    from app.models import ContractorReportModel
    from app.schemas import PropertyHistoryItem

    cases = (
        await session.execute(
            select(RepairCaseModel).where(RepairCaseModel.property_id == property_id)
            .order_by(RepairCaseModel.created_at.desc())
        )
    ).scalars().all()
    case_ids = [c.id for c in cases]
    contractors_by_case = await services.assigned_contractors_for_cases(session, case_ids)
    work_orders_by_case = await services._work_orders_by_case_id(session, case_ids)

    quoted_by_case: dict[str, int] = defaultdict(int)
    priced_case_ids: set[str] = set()
    for contribution in await reconciled_quotes(session, case_ids):
        if contribution.trade is None:  # case-level entry -- see docstring
            continue
        quoted_by_case[contribution.case_id] += contribution.quoted_pence
        priced_case_ids.add(contribution.case_id)

    items: list[PropertyHistoryItem] = []
    for case in cases:
        resolved_at = None
        outcome = None
        if case.status == CaseStatus.RESOLVED:
            resolved_event = (
                await session.execute(
                    select(CaseEventModel).where(
                        CaseEventModel.case_id == case.id, CaseEventModel.type == "CASE_RESOLVED",
                    ).order_by(CaseEventModel.occurred_at.desc()).limit(1)
                )
            ).scalars().first()
            if resolved_event is not None:
                resolved_at = resolved_event.occurred_at

        latest_completion_report = (
            await session.execute(
                select(ContractorReportModel)
                .join(WorkOrderModel, WorkOrderModel.id == ContractorReportModel.work_order_id)
                .where(
                    ContractorReportModel.case_id == case.id,
                    WorkOrderModel.status == WorkOrderStatus.COMPLETED,
                    WorkOrderModel.completion_report_id == ContractorReportModel.id,
                )
                .order_by(ContractorReportModel.received_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if latest_completion_report is not None:
            outcome = latest_completion_report.text

        contractor = contractors_by_case.get(case.id)
        items.append(
            PropertyHistoryItem(
                case_id=case.id, case_number=case.case_number, title=case.title, status=case.status,
                created_at=case.created_at, resolved_at=resolved_at, outcome=outcome,
                contractor_name=contractor.display_name if contractor else None,
                quoted_pence=quoted_by_case.get(case.id) if case.id in priced_case_ids else None,
                trade=services._pick_primary_trade(work_orders_by_case.get(case.id, [])),
            )
        )
    return items


async def property_stats(
    session: AsyncSession, property_id: str, build_year: int | None
) -> "PropertyStatsResponse":
    """Property Stats screen: "breakdown by trade" / "annual quoted total"
    / "recurring issues". `quoted_by_trade`/`quoted_by_year` both come from
    `reconciled_quotes()` (see this module's docstring), restricted to
    work-order-backed contributions for the same reason
    property_history_items excludes case-level entries -- this keeps the
    trade breakdown and the year breakdown summing to the same grand total,
    which is what "the chart and the total must reconcile" means on this
    one page. `quoted_by_year` buckets by the case's `created_at` year (not
    the contribution's own `occurred_at`), matching this function's
    pre-reconciliation behaviour -- unlike spend_by_year, property "annual
    quoted total" has always meant "the year the issue was reported", not
    "the year the money was incurred/quoted"; that distinction predates
    this change and is left as-is.

    recurring_issues heuristic (a judgment call -- there is no documented
    product spec for this): group the property's cases by
    services._pick_primary_trade, and report any trade with 2+ cases,
    most-recently-occurring first. "Occurred" is a case's created_at (when
    the issue was first reported), not its resolution date.
    """
    from app.schemas import PropertyStatsResponse, RecurringIssue, TradeQuoteBreakdown, YearlyQuoteTotal

    cases = (
        await session.execute(select(RepairCaseModel).where(RepairCaseModel.property_id == property_id))
    ).scalars().all()
    case_ids = [c.id for c in cases]
    cases_by_id = {c.id: c for c in cases}
    active_count = sum(1 for c in cases if c.status == CaseStatus.ACTIVE)
    total_count = len(cases)

    work_orders_by_case = await services._work_orders_by_case_id(session, case_ids)

    trade_totals: dict[Trade, int] = defaultdict(int)
    year_totals: dict[int, int] = defaultdict(int)
    for contribution in await reconciled_quotes(session, case_ids):
        if contribution.trade is None:  # case-level entry -- see docstring
            continue
        trade_totals[contribution.trade] += contribution.quoted_pence
        case = cases_by_id.get(contribution.case_id)
        if case is not None:
            year_totals[case.created_at.year] += contribution.quoted_pence

    trade_occurrences: dict[Trade, list[datetime]] = {}
    for case in cases:
        primary_trade = services._pick_primary_trade(work_orders_by_case.get(case.id, []))
        if primary_trade is not None:
            trade_occurrences.setdefault(primary_trade, []).append(case.created_at)

    grand_total = sum(trade_totals.values())
    quoted_by_trade = [
        TradeQuoteBreakdown(
            trade=trade, quoted_pence=amount,
            percentage=round(amount / grand_total * 100, 1) if grand_total else 0.0,
        )
        for trade, amount in sorted(trade_totals.items(), key=lambda kv: kv[1], reverse=True)
    ]
    quoted_by_year = [
        YearlyQuoteTotal(year=year, quoted_pence=amount) for year, amount in sorted(year_totals.items())
    ]
    recurring_issues = sorted(
        (
            RecurringIssue(trade=trade, occurrence_count=len(occurrences), last_occurred_at=max(occurrences))
            for trade, occurrences in trade_occurrences.items()
            if len(occurrences) >= 2
        ),
        key=lambda item: item.last_occurred_at, reverse=True,
    )

    return PropertyStatsResponse(
        property_id=property_id, active_count=active_count, total_count=total_count,
        quoted_by_trade=quoted_by_trade, quoted_by_year=quoted_by_year,
        recurring_issues=recurring_issues, build_year=build_year,
    )


# --------------------------------------------------------------------------
# Period-over-period comparison
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PeriodComparison:
    current: float
    previous: float
    change_pct: float | None
    is_new: bool


def period_comparison(current: float, previous: float) -> PeriodComparison:
    """Percentage change from `previous` to `current`, with an explicit
    zero-baseline rule instead of a division error or a fabricated number:

    - previous == 0 and current == 0 -> change_pct = 0.0, is_new = False
      (nothing happened in either window -- a real, honest 0%).
    - previous == 0 and current > 0 -> change_pct = None, is_new = True, so
      the UI renders "new"/"--" rather than a fake "inf%" or "100%".
    - otherwise -> the ordinary percentage change, rounded to 1dp.
    """
    if previous == 0:
        if current == 0:
            return PeriodComparison(current=current, previous=previous, change_pct=0.0, is_new=False)
        return PeriodComparison(current=current, previous=previous, change_pct=None, is_new=True)
    return PeriodComparison(
        current=current, previous=previous,
        change_pct=round((current - previous) / previous * 100, 1), is_new=False,
    )
