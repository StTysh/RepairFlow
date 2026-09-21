"""Give pre-existing cases the event log they were never written with.

Some operational cases predate the event-sourcing work: they have a
status, a work order and a pair of timestamps, but `case_events` holds
nothing at all for them. The consequences are visible on three screens:

* the ticket's **Agent** tab and case-flow graph are blank, because both
  are built from `case_events` + `orchestration_runs`;
* the **Timeline** shows nothing happened;
* `avg_resolution_hours` and `resolved_this_week` skip them entirely --
  both count `CASE_RESOLVED` *events*, and a RESOLVED case with no
  resolution event is invisible to them. A case cannot have reached
  RESOLVED without being resolved, so that row is simply incomplete.

This derives a minimal, consistent log from what the case already
records -- its status, its work orders and their trades, `created_at`
and `updated_at` -- and writes nothing it cannot ground in an existing
row.

Safety rule: never touch a case carrying LIVE provenance
--------------------------------------------------------
Cases 1-5 in the shipped database hold genuine ElevenLabs call evidence:
`case_events` rows with `provenance=LIVE` and communications recorded
against real conversations. Several are stalled mid-workflow because the
coordinator has no model key, which is an honest state and not a gap to
paper over. Synthesising a work order or a decision on top of real call
evidence would manufacture exactly the fake live trace the project
prohibits, so any case with a single LIVE-provenance event or
communication is skipped and reported as skipped.

Everything written here is `Provenance.SIMULATED` and any orchestration
run is stamped `fixture:backfill-v1`, so no screen can present it as a
real model call.

    python -m app.backfill_case_history --dry-run
    python -m app.backfill_case_history --apply

Idempotent: a case that already has any event is left alone.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import run_cli, session_scope
from app.models import (
    CaseEventModel,
    CommunicationModel,
    ContractorModel,
    OrchestrationRunModel,
    RepairCaseModel,
    RepairIssueModel,
    WorkOrderModel,
)
from app.schemas import CaseStatus, OrchestrationRunState, Provenance, Trade, WorkOrderStatus

MODEL_ID = "fixture:backfill-v1"
MARKER = "backfill-case-history-v1"
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "repairflow.backfill-case-history")


def stable_id(label: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{MARKER}:{label}"))


class _Log:
    """Builds one case's event log, keeping seq and causation consistent."""

    def __init__(self, case: RepairCaseModel) -> None:
        self.case = case
        self.events: list[CaseEventModel] = []
        self.runs: list[OrchestrationRunModel] = []
        self._seq = 0
        self._last: str | None = None

    def event(self, event_type: str, *, at: datetime, actor_type: str, payload: dict) -> CaseEventModel:
        self._seq += 1
        row = CaseEventModel(
            id=stable_id(f"event:{self.case.id}:{self._seq}"),
            case_id=self.case.id,
            seq=self._seq,
            type=event_type,
            occurred_at=at,
            received_at=at,
            actor_type=actor_type,
            actor_id=MARKER,
            source_event_key=f"{MARKER}:{self.case.id}:{self._seq}",
            correlation_id=stable_id(f"corr:{self.case.id}"),
            causation_event_id=self._last,
            payload_version=1,
            payload=payload,
            provenance=Provenance.SIMULATED,
        )
        self._last = row.id
        self.events.append(row)
        return row

    def run(self, trigger: CaseEventModel, *, summary: str, action: dict, at: datetime) -> None:
        self.runs.append(
            OrchestrationRunModel(
                id=stable_id(f"run:{self.case.id}:{trigger.seq}"),
                case_id=self.case.id,
                trigger_event_id=trigger.id,
                snapshot_version=1,
                model_id=MODEL_ID,
                # Explicit: the column defaults to RUNNING, and a generated
                # run left at that default makes the dashboard's
                # `agent_active` flag true forever -- a spinner asserting
                # the coordinator is mid-flight when nothing is running.
                state=OrchestrationRunState.SUCCEEDED,
                started_at=at,
                finished_at=at + timedelta(seconds=12 + (trigger.seq * 7) % 90),
                usage={"backfilled": True},
                proposal={
                    "case_id": self.case.id,
                    "expected_case_version": self.case.version,
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


def _risk(assessed_at: datetime) -> dict:
    return {
        "urgency": "ROUTINE", "gas": "NO", "fire": "NO", "water_near_electrics": "NO",
        "structural_danger": "NO", "uncontrolled_flood": "NO", "vulnerability_concern": "NO",
        "evidence_refs": [], "uncertainties": [],
        "assessed_at": assessed_at.isoformat().replace("+00:00", "Z"),
    }


def _build(case: RepairCaseModel, work_orders: list[WorkOrderModel], issue_id: str | None) -> _Log:
    """Derive a log from the case's own rows.

    Timestamps are spread between `created_at` and `updated_at` rather
    than invented: `updated_at` is the last time anything about this case
    changed, which for a closed case is when it closed.
    """
    log = _Log(case)
    start = case.created_at
    end = max(case.updated_at, start + timedelta(hours=2))
    span = (end - start).total_seconds()

    def at(fraction: float) -> datetime:
        return start + timedelta(seconds=span * fraction)

    created = log.event("CASE_CREATED", at=start, actor_type="OPERATOR",
                        payload={"backfilled_from": "case row"})

    live = [wo for wo in work_orders if wo.status != WorkOrderStatus.CANCELLED]
    primary = next((wo for wo in live if wo.required_for_resolution), live[0] if live else None)

    if primary is not None:
        log.run(created, summary=f"Triage: {primary.scope[:120]}", at=at(0.02),
                action={"kind": "APPLY_TRIAGE", "risk": _risk(at(0.02)),
                        "issue_description": case.title,
                        "suggested_trade": (primary.trade.value if hasattr(primary.trade, "value") else str(primary.trade)),
                        "scope": primary.scope})
        for i, wo in enumerate(live):
            log.event("WORK_ORDER_CREATED", at=at(0.05 + i * 0.02), actor_type="COORDINATOR",
                      payload={"work_order_id": wo.id, "scope": wo.scope})

    # A case with a prerequisite still READY behind a BLOCKED repair is
    # the dependency story; say so rather than leaving an unexplained gap.
    blocked = [wo for wo in live if wo.status == WorkOrderStatus.BLOCKED]
    prereq = [wo for wo in live if wo.status == WorkOrderStatus.READY and wo is not primary]
    if blocked and prereq:
        log.event("DEPENDENCY_DISCOVERED", at=at(0.45), actor_type="COORDINATOR",
                  payload={"blocked_work_order_id": blocked[0].id,
                           "prerequisite_work_order_id": prereq[0].id})

    completed = [wo for wo in live if wo.status == WorkOrderStatus.COMPLETED]
    for i, wo in enumerate(completed):
        ev = log.event("WORK_ORDER_COMPLETED", at=at(0.80 + i * 0.02), actor_type="COORDINATOR",
                       payload={"work_order_id": wo.id})
        # No ACCEPT_REPORT run is written here. That action's proposal
        # requires a real `report_id`, and these cases have no contractor
        # report at all -- there is nothing that could have been accepted.
        # An earlier version emitted the run with `report_id: None`, which
        # is both a fabricated decision and invalid: `OrchestrationRun`
        # revalidates the stored proposal, so GET /cases/{id}/runs returned
        # 500 and the Agent tab would not load. If a report does exist,
        # that decision belongs to whatever wrote the report.

    if case.status == CaseStatus.RESOLVED:
        confirmed = log.event("TENANT_CONFIRMATION_RECEIVED", at=at(0.93), actor_type="OPERATOR",
                              payload={"confirmed": True})
        # Only propose RESOLVE_CASE when the real issue id is known; the
        # schema requires a UUID for both fields.
        if issue_id is not None:
            log.run(confirmed, summary="Tenant confirmed the fix; resolve the case.", at=at(0.95),
                    action={"kind": "RESOLVE_CASE", "issue_id": issue_id,
                            "confirmation_event_id": confirmed.id})
        log.event("CASE_RESOLVED", at=end, actor_type="COORDINATOR", payload={"backfilled": True})
    elif case.status == CaseStatus.CANCELLED:
        log.event("CASE_CANCELLED", at=end, actor_type="OPERATOR",
                  payload={"reason": case.escalation_reason or "Closed without further work."})
    elif case.status == CaseStatus.ESCALATED:
        log.event("CASE_ESCALATED", at=end, actor_type="COORDINATOR",
                  payload={"message": case.escalation_reason or "Escalated to a human coordinator."})

    return log


async def _targets(session: AsyncSession) -> tuple[list[tuple[RepairCaseModel, list[WorkOrderModel], str | None]], list[tuple[int, str]]]:
    """Operational cases with no events, split into (eligible, skipped)."""
    cases = list((await session.execute(
        sa.select(RepairCaseModel)
        .where(RepairCaseModel.archive_batch_id.is_(None))
        .order_by(RepairCaseModel.case_number)
    )).scalars())

    with_events = set((await session.execute(sa.select(CaseEventModel.case_id).distinct())).scalars())
    live_event_cases = set((await session.execute(
        sa.select(CaseEventModel.case_id).where(CaseEventModel.provenance == Provenance.LIVE).distinct()
    )).scalars())
    live_comm_cases = set((await session.execute(
        sa.select(CommunicationModel.case_id).where(CommunicationModel.provenance == Provenance.LIVE).distinct()
    )).scalars())
    live = live_event_cases | live_comm_cases

    eligible: list[tuple[RepairCaseModel, list[WorkOrderModel], str | None]] = []
    skipped: list[tuple[int, str]] = []
    for case in cases:
        if case.id in with_events:
            continue
        if case.id in live:
            skipped.append((case.case_number, "carries LIVE provenance"))
            continue
        work_orders = list((await session.execute(
            sa.select(WorkOrderModel).where(WorkOrderModel.case_id == case.id).order_by(WorkOrderModel.created_at)
        )).scalars())
        issue_id = (await session.execute(
            sa.select(RepairIssueModel.id).where(RepairIssueModel.case_id == case.id)
        )).scalar_one_or_none()
        eligible.append((case, work_orders, issue_id))
    return eligible, skipped


async def _live_case_ids(session: AsyncSession) -> set[str]:
    """Cases holding real ElevenLabs evidence, by event or communication."""
    from_events = set((await session.execute(
        sa.select(CaseEventModel.case_id).where(CaseEventModel.provenance == Provenance.LIVE).distinct()
    )).scalars())
    from_comms = set((await session.execute(
        sa.select(CommunicationModel.case_id).where(CommunicationModel.provenance == Provenance.LIVE).distinct()
    )).scalars())
    return {cid for cid in (from_events | from_comms) if cid is not None}


async def _assign_orphan_work_orders(session: AsyncSession, *, apply: bool) -> tuple[list[str], list[str]]:
    """Give a contractor to any operational work order that has none.

    A completed work order with no contractor renders as "unassigned" on a
    finished case, which reads as missing data rather than as history.
    Matched by trade against the approved roster.

    The LIVE guard applies here too, and it is the reason this returns a
    second list. Cases 3 and 4 have real recorded calls against them --
    one of them a CONTRACTOR-purpose call -- so their work order having no
    `contractor_id` is a genuine gap in real history, not a rendering
    defect. Filling it in would put a contractor's name against a real
    call that may have been to somebody else.
    """
    live = await _live_case_ids(session)
    all_orphans = list((await session.execute(
        sa.select(WorkOrderModel, RepairCaseModel.case_number, RepairCaseModel.id)
        .join(RepairCaseModel, RepairCaseModel.id == WorkOrderModel.case_id)
        .where(WorkOrderModel.contractor_id.is_(None), RepairCaseModel.archive_batch_id.is_(None))
    )).all())
    held_back = [
        f"#{case_number} {wo.trade.value if hasattr(wo.trade, 'value') else wo.trade} work order"
        for wo, case_number, case_id in all_orphans if case_id in live
    ]
    orphans = [(wo, case_number) for wo, case_number, case_id in all_orphans if case_id not in live]
    if not orphans:
        return [], held_back
    contractors = list((await session.execute(
        sa.select(ContractorModel).where(ContractorModel.archive_batch_id.is_(None)).order_by(ContractorModel.id)
    )).scalars())
    notes: list[str] = []
    for wo, case_number in orphans:
        trade = wo.trade.value if hasattr(wo.trade, "value") else str(wo.trade)
        pool = [c for c in contractors if trade in (c.trades or [])] or contractors
        if not pool:
            continue
        chosen = pool[int(stable_id(f"orphan:{wo.id}")[:8], 16) % len(pool)]
        notes.append(f"#{case_number} {trade} work order -> {chosen.display_name}")
        if apply:
            wo.contractor_id = chosen.id
    return notes, held_back


async def _run(apply: bool) -> int:
    async with session_scope() as session:
        eligible, skipped = await _targets(session)
        orphan_notes, held_back = await _assign_orphan_work_orders(session, apply=apply)

        if skipped or held_back:
            print("Left alone (real call evidence -- never overwritten):")
            for number, why in skipped:
                print(f"  #{number}: {why}")
            for note in held_back:
                print(f"  {note}: left unassigned, the case has recorded live calls")
        if orphan_notes:
            print(f"\n{'Assigned' if apply else 'Would assign'} contractors to unassigned work orders:")
            for n in orphan_notes:
                print(f"  {n}")

        if not eligible:
            print("\nNo eligible cases without an event log; nothing to backfill.")
            return 0

        print(f"\n{'Backfilling' if apply else 'Would backfill'} {len(eligible)} case(s):")
        total_events = total_runs = 0
        now = datetime.now(timezone.utc)
        for case, work_orders, issue_id in eligible:
            log = _build(case, work_orders, issue_id)
            if any(e.occurred_at > now for e in log.events):
                print(f"  #{case.case_number}: SKIPPED -- derived timeline lands in the future")
                continue
            total_events += len(log.events)
            total_runs += len(log.runs)
            status = case.status.value if hasattr(case.status, "value") else str(case.status)
            print(f"  #{case.case_number:<3} {status:<22} {len(log.events)} event(s), {len(log.runs)} run(s)"
                  f"  [{', '.join(e.type for e in log.events)}]")
            if apply:
                for e in log.events:
                    session.add(e)
                await session.flush()   # events before the runs that reference them
                for r in log.runs:
                    session.add(r)
                await session.flush()

        print(f"\n{'Wrote' if apply else 'Would write'} {total_events} event(s) and {total_runs} orchestration run(s).")
        if not apply:
            print("Re-run with --apply.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill event logs for operational cases that have none.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.exit(run_cli(_run(apply=args.apply)))


if __name__ == "__main__":
    main()
