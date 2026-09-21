"""CLI for the captured real-intake cases.

    python -m app.intake_fixture --apply     # import (idempotent)
    python -m app.intake_fixture --remove    # delete exactly what it imported
    python -m app.intake_fixture --status    # how much of the dataset is present
    python -m app.intake_fixture --validate  # run every programmatic check
    python -m app.intake_fixture --export    # re-capture from THIS database

`--export` is the only one that reads your database and writes into the
source tree; the other four behave like `app.archive`'s. Run `--export`
on the machine whose database is the source of truth, then commit the
resulting `dataset.json`.

Never run --apply/--remove against backend/data/repairflow.db without
meaning to -- point DATABASE_PATH at a throwaway location first.
"""

from __future__ import annotations

import argparse
import sys

from app.db import run_cli, session_scope
from app.intake_fixture import (
    apply_fixture,
    load_dataset,
    remove_fixture,
    status,
    validate,
)


async def _apply() -> int:
    result = await apply_fixture(session_scope)
    if result.skipped:
        data = load_dataset()
        if not data:
            print("No dataset.json in app/intake_fixture; nothing to import.")
            return 0
        print(f"All {len(data.get('repair_cases', []))} captured case(s) already present; nothing written.")
        return 0
    total = sum(result.counts.values())
    print(f"Captured intake imported: {total} row(s).")
    for name, count in sorted(result.counts.items()):
        print(f"  {name}: {count}")
    return 0


async def _remove() -> int:
    result = await remove_fixture(session_scope)
    if not result.found:
        print("No captured intake rows present; nothing removed.")
        return 0
    total = sum(result.counts.values())
    print(f"Captured intake removed: {total} row(s) across {len(result.counts)} table(s).")
    for name, count in sorted(result.counts.items()):
        print(f"  {name}: {count}")
    return 0


async def _status() -> int:
    counts = await status(session_scope)
    if not counts:
        print("No dataset.json in app/intake_fixture.")
        return 0
    complete = all(p == e for p, e in counts.values())
    print("Captured intake:", "fully imported" if complete else "PARTIALLY imported")
    for name, (present, expected) in sorted(counts.items()):
        flag = "" if present == expected else "   <-- incomplete"
        print(f"  {name}: {present}/{expected}{flag}")
    return 0


async def _validate() -> int:
    report = await validate(session_scope)
    for c in report.checks:
        print(f"  [{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}")
    return 0 if report.passed else 1


async def _export() -> int:
    from app.intake_fixture.export import PersonalDataFound, export

    try:
        path, tables = await export(session_scope)
    except PersonalDataFound as exc:
        print(str(exc), file=sys.stderr)
        return 2
    total = sum(len(v) for v in tables.values())
    print(f"Captured {len(tables.get('repair_cases', []))} case(s), {total} row(s) -> {path}")
    for name, rows in sorted(tables.items()):
        print(f"  {name}: {len(rows)}")
    print("\nCommit that file so a clone reproduces these cases.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.intake_fixture", description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="Import the captured cases (idempotent).")
    group.add_argument("--remove", action="store_true", help="Remove exactly the captured cases.")
    group.add_argument("--status", action="store_true", help="Report how much of the dataset is present.")
    group.add_argument("--validate", action="store_true", help="Run every programmatic check.")
    group.add_argument("--export", action="store_true", help="Re-capture from this database into dataset.json.")
    args = parser.parse_args(argv)

    if args.apply:
        return run_cli(_apply())
    if args.remove:
        return run_cli(_remove())
    if args.status:
        return run_cli(_status())
    if args.validate:
        return run_cli(_validate())
    if args.export:
        return run_cli(_export())
    return 1  # unreachable: the group is required


if __name__ == "__main__":
    sys.exit(main())
