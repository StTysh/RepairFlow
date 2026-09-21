"""Bring an empty database up to the full shared workspace, in one command.

    uv run python -m app.bootstrap

This is the four generators plus the captured intake, in the only order
that works, followed by every validator. Each step is idempotent, so
running it twice is safe and running it against a partially-populated
database fills in what is missing.

    app.seed                  reference data: 12 properties (with photos),
                              12 tenants, 24 approved contractors
    app.intake_fixture        the 14 cases created by driving the running
                              application rather than by a generator
    app.archive               60 closed archival cases, 2021-2026
    app.sample_operations     25 open and recently-closed operational cases
    app.backfill_case_history event logs for any case that has none

Order is load-bearing in three separate ways.

`app.seed` must be first: every later step references its properties,
tenants and contractors by id, and those ids are deterministic (`uuid5`)
precisely so that this works.

`app.intake_fixture` must come before the two case generators. Its cases
carry the case_numbers they were originally issued -- 1 to 14 -- while
both generators allocate theirs as `MAX(case_number) + 1`. Import the
fixture last and the generators have already taken 1-85, so every
captured case collides on the `uq_case_number` UNIQUE constraint. Import
it first and the numbering reproduces exactly what the source database
has: intake 1-14, archive 15-74, operations 75-99.

The backfill must be last: it only touches cases that already exist and
have no events, so anything it runs before is a case it cannot see.

`--check` runs no writes and reports what is present, which is the fast
way to answer "does my database match everyone else's?".
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

# (module, args, human label). Order is load-bearing -- see the docstring.
STEPS: tuple[tuple[str, list[str], str], ...] = (
    ("app.seed", [], "Reference data (properties, tenants, contractors)"),
    ("app.intake_fixture", ["--apply"], "Captured real-intake cases (14)"),
    ("app.archive", ["--apply"], "Archival cases (60, 2021-2026)"),
    ("app.sample_operations", ["--apply"], "Operational cases (25)"),
    ("app.backfill_case_history", ["--apply"], "Event logs for cases that have none"),
)

VALIDATORS: tuple[tuple[str, list[str], str], ...] = (
    ("app.archive", ["--validate"], "Archive integrity"),
    ("app.sample_operations", ["--validate"], "Operational workload integrity"),
    ("app.intake_fixture", ["--validate"], "Captured intake integrity"),
)


def _run(module: str, args: list[str], *, quiet: bool) -> int:
    """Each step runs in its own process.

    They are separate CLIs with their own event loops and their own
    `run_cli` entry points; importing and awaiting them in one loop would
    mean sharing an engine across steps that each expect to own one.
    """
    proc = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=BACKEND_DIR,
        capture_output=quiet,
        text=True,
    )
    if proc.returncode != 0 and quiet:
        sys.stdout.write(proc.stdout or "")
        sys.stderr.write(proc.stderr or "")
    return proc.returncode


async def _counts() -> dict[str, int]:
    import sqlalchemy as sa

    from app.db import session_scope
    from app.models import (
        ContractorModel,
        PropertyModel,
        RepairCaseModel,
        TenantModel,
    )

    async with session_scope() as session:

        async def count(model, *where) -> int:
            return (
                await session.execute(sa.select(sa.func.count()).select_from(model).where(*where))
            ).scalar_one()

        return {
            "properties": await count(PropertyModel),
            "tenants": await count(TenantModel),
            "contractors": await count(ContractorModel),
            "cases (total)": await count(RepairCaseModel),
            "cases (operational)": await count(
                RepairCaseModel, RepairCaseModel.archive_batch_id.is_(None)
            ),
            "cases (archival)": await count(
                RepairCaseModel, RepairCaseModel.archive_batch_id.is_not(None)
            ),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.bootstrap", description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Write nothing; just report what is present."
    )
    parser.add_argument(
        "--skip-validate", action="store_true", help="Populate without running the validators."
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Only print the summary.")
    args = parser.parse_args(argv)

    from app.db import run_cli

    if args.check:
        counts = run_cli(_counts())
        print("Current database:")
        for name, value in counts.items():
            print(f"  {name:<22}{value:>6}")
        return 0

    for index, (module, step_args, label) in enumerate(STEPS, start=1):
        print(f"[{index}/{len(STEPS)}] {label}")
        code = _run(module, step_args, quiet=args.quiet)
        if code != 0:
            print(f"\nFAILED at step {index}: python -m {module} {' '.join(step_args)}", file=sys.stderr)
            return code

    if not args.skip_validate:
        print("\nValidating:")
        failures = 0
        for module, step_args, label in VALIDATORS:
            code = _run(module, step_args, quiet=True)
            print(f"  [{'PASS' if code == 0 else 'FAIL'}] {label}")
            failures += 1 if code else 0
        if failures:
            print(
                f"\n{failures} validator(s) failed. Re-run the one that failed without -q to see why.",
                file=sys.stderr,
            )
            return 1

    counts = run_cli(_counts())
    print("\nDatabase ready:")
    for name, value in counts.items():
        print(f"  {name:<22}{value:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
