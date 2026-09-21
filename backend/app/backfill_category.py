"""Derive `repair_cases.category` for cases that predate the column.

`category` was added when the portfolio analytics landed. Every case
created before then has it NULL, which empties the category donut and the
recurrence grouping -- both of which read this column and nothing else.

Those cases do already carry the information, one hop away: their work
orders each have a real `Trade`. This derives the case's category from
them, once, explicitly.

The derivation is **not reimplemented here**. It delegates to
`services._pick_primary_trade`, the same rule the property-history and
property-stats views already use to answer "what kind of work is this
case about":

* CANCELLED work orders are excluded first -- work that was called off is
  not what the case is about any more. An earlier version of this file
  missed that and categorised a case ELECTRICAL when the electrical work
  order had been cancelled as a misdiagnosis and a plumber did the
  actual repair.
* Among what remains, the work order marked `required_for_resolution`
  wins (the primary repair, not a scaffold or access prerequisite
  discovered later); ties and absences fall back to the earliest by
  `created_at`.
* **No work orders, or every one cancelled** -> left NULL. There is
  nothing to derive it from, and guessing would push a fabricated
  classification into every count, donut segment and recurrence group
  that reads this column. The UI labels these "Uncategorised", which is
  true.

Sharing the rule is the point: a category derived here that disagreed
with the trade shown on the property-history screen would be worse than
no backfill at all.

Never overwrites a category that is already set, and never touches an
archival case -- the archive assigns its own categories deliberately and
rewriting them would desynchronise the dataset from its own validation.

Safe to re-run: a second pass reports zero changes.

    python -m app.backfill_category --dry-run
    python -m app.backfill_category --apply
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import sqlalchemy as sa

from app.db import run_cli, session_scope


async def plan() -> tuple[list[tuple[str, int, str, str]], int, int]:
    """Returns (changes, skipped, already_set).

    Each change is (case_id, case_number, trade, reason).
    """
    from app.domain.services import _pick_primary_trade
    from app.models import RepairCaseModel, WorkOrderModel

    async with session_scope() as session:
        already_set = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(RepairCaseModel)
                .where(
                    RepairCaseModel.category.is_not(None),
                    RepairCaseModel.archive_batch_id.is_(None),
                )
            )
        ).scalar_one()

        cases = (
            await session.execute(
                sa.select(RepairCaseModel.id, RepairCaseModel.case_number)
                .where(
                    RepairCaseModel.category.is_(None),
                    RepairCaseModel.archive_batch_id.is_(None),
                )
                .order_by(RepairCaseModel.case_number)
            )
        ).all()
        if not cases:
            return [], 0, already_set

        case_ids = [c.id for c in cases]
        work_orders = (
            await session.execute(
                sa.select(WorkOrderModel)
                .where(WorkOrderModel.case_id.in_(case_ids))
                .order_by(WorkOrderModel.created_at)
            )
        ).scalars().all()

    by_case: dict[str, list] = defaultdict(list)
    for wo in work_orders:
        by_case[wo.case_id].append(wo)

    changes: list[tuple[str, int, str, str]] = []
    skipped = 0
    for case in cases:
        rows = by_case.get(case.id, [])
        trade = _pick_primary_trade(rows)
        if trade is None:
            skipped += 1
            continue
        live = [wo for wo in rows if wo.status != "CANCELLED"]
        cancelled = len(rows) - len(live)
        distinct = {wo.trade for wo in live}
        if len(distinct) == 1:
            reason = "single live work-order trade"
        else:
            reason = f"{len(distinct)} live trades; primary-repair rule"
        if cancelled:
            reason += f" ({cancelled} cancelled excluded)"
        changes.append((case.id, case.case_number, getattr(trade, "value", trade), reason))

    return changes, skipped, already_set


async def apply_changes(changes: list[tuple[str, int, str, str]]) -> int:
    from app.models import RepairCaseModel

    if not changes:
        return 0
    async with session_scope() as session:
        for case_id, _number, trade, _reason in changes:
            await session.execute(
                sa.update(RepairCaseModel)
                # The NULL guard is repeated here, not just in the plan:
                # between planning and applying, something else could have
                # set a category, and this must never overwrite one.
                .where(RepairCaseModel.id == case_id, RepairCaseModel.category.is_(None))
                .values(category=trade)
            )
    return len(changes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="show what would change")
    group.add_argument("--apply", action="store_true", help="write the derived categories")
    args = parser.parse_args()

    changes, skipped, already_set = run_cli(plan())

    if not changes and not skipped:
        print(f"Nothing to do: every operational case already has a category ({already_set}).")
        return

    verb = "Would set" if args.dry_run else "Set"
    for _case_id, number, trade, reason in changes:
        print(f"  {verb} #{number:<5} -> {trade:<12} ({reason})")

    if args.apply:
        written = run_cli(apply_changes(changes))
        print(f"\n{written} case(s) updated.")
    else:
        print(f"\n{len(changes)} case(s) would be updated. Re-run with --apply.")

    if skipped:
        print(
            f"{skipped} case(s) left uncategorised: no live work order to derive a category "
            "from (none at all, or every one cancelled). They will show as "
            "\"Uncategorised\", which is accurate."
        )
    if already_set:
        print(f"{already_set} case(s) already had a category and were not touched.")


if __name__ == "__main__":
    main()
