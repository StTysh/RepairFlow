"""Derive `repair_cases.category` for cases that predate the column.

`category` was added when the portfolio analytics landed. Every case
created before then has it NULL, which empties the category donut and the
recurrence grouping — both of which read this column and nothing else.

Those cases do already carry the information, one hop away: their work
orders each have a real `Trade`. This derives the case's category from
them, once, explicitly.

The derivation, and why:

* **Exactly one distinct work-order trade** → that trade. Unambiguous.
* **Several distinct trades** → the trade of the work order marked
  `required_for_resolution`, falling back to the earliest by
  `created_at`. A case's category is meant to describe what the *issue*
  is, not every trade it eventually touched; a roof leak that needed
  scaffolding is still a roofing case. The first-raised required work
  order is the closest honest proxy for the original diagnosis.
* **No work orders at all** → left NULL. There is nothing to derive it
  from. Guessing would push a fabricated classification into every count,
  donut segment and recurrence group that reads this column, which is
  exactly the failure this whole exercise is meant to avoid. The UI
  labels these "Uncategorised", which is true.

Never overwrites a category that is already set, and never touches an
archival case — the archive assigns its own categories deliberately and
rewriting them would desynchronise the dataset from its own validation.

Safe to re-run: a second pass reports zero changes.

    python -m app.backfill_category --dry-run
    python -m app.backfill_category --apply
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict

import sqlalchemy as sa

from app.db import session_scope


async def plan() -> tuple[list[tuple[str, int, str, str]], int, int]:
    """Returns (changes, skipped_no_work_orders, already_set).

    Each change is (case_id, case_number, trade, reason).
    """
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
                sa.select(
                    WorkOrderModel.case_id,
                    WorkOrderModel.trade,
                    WorkOrderModel.required_for_resolution,
                    WorkOrderModel.created_at,
                )
                .where(WorkOrderModel.case_id.in_(case_ids))
                .order_by(WorkOrderModel.created_at)
            )
        ).all()

    by_case: dict[str, list] = defaultdict(list)
    for row in work_orders:
        by_case[row.case_id].append(row)

    changes: list[tuple[str, int, str, str]] = []
    skipped = 0
    for case in cases:
        rows = by_case.get(case.id, [])
        if not rows:
            skipped += 1
            continue
        trades = {r.trade for r in rows}
        if len(trades) == 1:
            trade = next(iter(trades))
            reason = "single work-order trade"
        else:
            required = [r for r in rows if r.required_for_resolution]
            chosen = (required or rows)[0]  # rows are already created_at-ordered
            trade = chosen.trade
            reason = (
                f"{len(trades)} trades; took the earliest required work order"
                if required
                else f"{len(trades)} trades; none required, took the earliest"
            )
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

    changes, skipped, already_set = asyncio.run(plan())

    if not changes and not skipped:
        print(f"Nothing to do: every operational case already has a category ({already_set}).")
        return

    verb = "Would set" if args.dry_run else "Set"
    for _case_id, number, trade, reason in changes:
        print(f"  {verb} #{number:<5} -> {trade:<12} ({reason})")

    if args.apply:
        written = asyncio.run(apply_changes(changes))
        print(f"\n{written} case(s) updated.")
    else:
        print(f"\n{len(changes)} case(s) would be updated. Re-run with --apply.")

    if skipped:
        print(
            f"{skipped} case(s) left uncategorised: no work orders to derive a category from. "
            "They will show as \"Uncategorised\", which is accurate."
        )
    if already_set:
        print(f"{already_set} case(s) already had a category and were not touched.")


if __name__ == "__main__":
    main()
