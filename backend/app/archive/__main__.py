"""CLI for the synthetic historical archive.

    python -m app.archive --apply       # import (idempotent: no-op if already imported)
    python -m app.archive --remove      # delete every row/file this batch wrote
    python -m app.archive --status      # is it imported? row counts if so
    python -m app.archive --validate    # run every programmatic check, print pass/fail

Never run --apply/--remove/--validate against backend/data/repairflow.db
without meaning to -- point DATABASE_PATH (and, for a fully isolated dry
run, DOCUMENTS_DIR) at a throwaway location first.
"""
from __future__ import annotations

import argparse
import sys

import sqlalchemy as sa

from app.archive.dataset import DEFAULT_LABEL, DEFAULT_SEED
from app.archive.importer import import_archive, remove_archive, validate
from app.db import run_cli, session_scope
from app.models import ArchiveBatchModel


async def _apply(label: str, seed: int) -> int:
    result = await import_archive(session_scope, label=label, seed=seed)
    if result.skipped:
        print(f"Archive '{label}' already imported (batch {result.batch_id}); nothing written.")
        return 0
    total = sum(result.counts.values())
    print(f"Archive '{label}' imported: batch {result.batch_id}, {total} row(s) total.")
    for name, count in result.counts.items():
        print(f"  {name}: {count}")
    if result.documents_written:
        print(f"  document files written: {len(result.documents_written)}")
    return 0


async def _remove(label: str) -> int:
    result = await remove_archive(label)
    if not result.found:
        print(f"No archive batch labelled '{label}' found; nothing removed.")
        return 0
    total = sum(result.counts.values())
    print(f"Archive '{label}' removed: {total} row(s) deleted across {len(result.counts)} table(s).")
    for name, count in result.counts.items():
        print(f"  {name}: {count}")
    if result.documents_removed:
        print(f"  document files removed: {len(result.documents_removed)}")
    return 0


async def _status(label: str) -> int:
    async with session_scope() as session:
        batch = (
            await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == label))
        ).scalar_one_or_none()
        if batch is None:
            print(f"Archive '{label}': not imported.")
            return 0
        from app.models import RepairCaseModel, PropertyModel

        case_count = (
            await session.execute(
                sa.select(sa.func.count()).select_from(RepairCaseModel).where(RepairCaseModel.archive_batch_id == batch.id)
            )
        ).scalar_one()
        property_count = (
            await session.execute(
                sa.select(sa.func.count()).select_from(PropertyModel).where(PropertyModel.archive_batch_id == batch.id)
            )
        ).scalar_one()
        print(
            f"Archive '{label}': imported (batch {batch.id}, seed {batch.random_seed}, "
            f"generator {batch.generator_version}) at {batch.created_at.isoformat()}."
        )
        print(f"  properties: {property_count}, cases: {case_count}")
    return 0


async def _validate(label: str, seed: int) -> int:
    async with session_scope() as session:
        report = await validate(session, label=label, seed=seed)
    ok_count = sum(1 for c in report.checks if c.passed)
    print(f"Validation for archive '{label}': {ok_count}/{len(report.checks)} checks passed.")
    for c in report.checks:
        status = "PASS" if c.passed else "FAIL"
        print(f"  [{status}] {c.name}: {c.detail}")
    return 0 if report.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.archive", description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="Import the archive (idempotent).")
    group.add_argument("--remove", action="store_true", help="Remove a previously imported archive.")
    group.add_argument("--status", action="store_true", help="Report whether the archive is imported.")
    group.add_argument("--validate", action="store_true", help="Run every programmatic validation check.")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="Archive batch label (default: %(default)s).")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Generator seed (default: %(default)s).")
    args = parser.parse_args(argv)

    if args.apply:
        return run_cli(_apply(args.label, args.seed))
    if args.remove:
        return run_cli(_remove(args.label))
    if args.status:
        return run_cli(_status(args.label))
    if args.validate:
        return run_cli(_validate(args.label, args.seed))
    return 1  # unreachable: mutually exclusive group is required


if __name__ == "__main__":
    sys.exit(main())
