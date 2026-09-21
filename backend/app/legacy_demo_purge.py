"""Removes the scripted demo workload a previous build seeded at startup.

The hackathon build's `app.seed` ran on every boot and inserted nine
fictional cases ("closed history", "upcoming visits", a scaffold dependency
story) together with their work orders, appointments, contractor reports,
dependencies, messages and action records. That generator is gone; this
module exists only so a database that already received those rows can be
cleaned without touching anything else.

Why an explicit id list rather than a heuristic: the fictional rows are the
only ones whose primary keys are `uuid5(NAMESPACE, label)` derivable, and
recomputing them is exact. A rule like "delete RESOLVED cases with no live
communication" would also delete genuine resolved work. Nothing here
deletes a row it cannot name in advance.

Real operator-created cases are untouched: their ids are random uuid4 and
cannot collide with any label below.

    python -m app.legacy_demo_purge --dry-run
    python -m app.legacy_demo_purge --apply
"""
from __future__ import annotations

import argparse
import uuid

import sqlalchemy as sa

from app.db import run_cli, session_scope

# Same namespace the retired seeder used. Do not change it: these two
# constants are the only record of which rows were synthetic.
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "repairflow.demo")

_CASE_LABELS = (
    "hist:cathedral:2023:plumbing",
    "hist:cathedral:2024:plumbing",
    "hist:cathedral:2025:electrical",
    "hist:gloucester:2023:roofing",
    "hist:gloucester:2024:other",
    "hist:gloucester:2025:roofing",
    "live:cathedral:boiler",
    "live:gloucester:gutter",
    "live:redcliffe:scaffold",
)


def _demo_id(label: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, label))


def scripted_case_ids() -> list[str]:
    """The nine case ids the retired seeder produced."""
    return [_demo_id(f"{label}:case") for label in _CASE_LABELS]


async def purge(*, apply: bool) -> dict[str, int]:
    """Counts (dry run) or deletes (apply) every row under those cases.

    Deletion order follows the foreign keys inwards-out; `PRAGMA
    foreign_keys=ON` is set on every connection, so getting the order wrong
    raises rather than silently orphaning.
    """
    from app.config import get_settings
    from app.models import (
        ActionRecordModel,
        AppointmentModel,
        AvailabilityWindowModel,
        CaseEventModel,
        CommunicationModel,
        ContractorReportModel,
        CostEntryModel,
        DependencyModel,
        DocumentModel,
        JobModel,
        MessageModel,
        NoteModel,
        OrchestrationRunModel,
        RepairCaseModel,
        RepairIssueModel,
        WorkOrderModel,
    )
    from app.schemas import RecordSubject

    case_ids = scripted_case_ids()
    counts: dict[str, int] = {}

    ordered = [
        DependencyModel,
        ContractorReportModel,
        AppointmentModel,
        AvailabilityWindowModel,
        MessageModel,
        CostEntryModel,
        CommunicationModel,
        JobModel,
        OrchestrationRunModel,
        CaseEventModel,
        WorkOrderModel,
        ActionRecordModel,
        RepairIssueModel,
        RepairCaseModel,
    ]

    async with session_scope() as session:
        present = (
            await session.execute(
                sa.select(RepairCaseModel.id).where(RepairCaseModel.id.in_(case_ids))
            )
        ).scalars().all()
        counts["cases_found"] = len(present)
        if not present:
            return counts

        # NoteModel/DocumentModel attach to a case via a generic
        # subject_type=CASE, subject_id=<case_id> pair with no foreign key
        # at all (models.py) -- the FK-ordered loop below, keyed on
        # `model.case_id`, cannot reach either of them, so a note or
        # document on one of these nine cases was never counted (not even
        # by --dry-run) and never deleted. Counted and, on --apply, deleted
        # here explicitly instead, using the same subject_type/subject_id
        # scoping app/archive/importer.py's remove_archive uses for its own
        # archive_batch_id-less tables. Nothing else has a foreign key onto
        # notes/documents, so there is no ordering constraint forcing this
        # before or after the loop below; it happens here because that is
        # where the equivalent `--dry-run` counts belong.
        note_condition = sa.and_(
            NoteModel.subject_type == RecordSubject.CASE, NoteModel.subject_id.in_(present)
        )
        counts["notes"] = (
            await session.execute(sa.select(sa.func.count()).select_from(NoteModel).where(note_condition))
        ).scalar_one()
        if apply and counts["notes"]:
            await session.execute(sa.delete(NoteModel).where(note_condition))

        doc_condition = sa.and_(
            DocumentModel.subject_type == RecordSubject.CASE, DocumentModel.subject_id.in_(present)
        )
        doc_rows = (await session.execute(sa.select(DocumentModel).where(doc_condition))).scalars().all()
        counts["documents"] = len(doc_rows)
        if apply and doc_rows:
            settings = get_settings()
            for doc in doc_rows:
                path = settings.documents_dir / doc.stored_name
                if path.exists():
                    path.unlink()
            await session.execute(sa.delete(DocumentModel).where(doc_condition))

        for model in ordered:
            column = RepairCaseModel.id if model is RepairCaseModel else model.case_id
            total = (
                await session.execute(
                    sa.select(sa.func.count()).select_from(model).where(column.in_(present))
                )
            ).scalar_one()
            counts[model.__tablename__] = total
            if apply and total:
                await session.execute(sa.delete(model).where(column.in_(present)))

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="count what would be deleted")
    group.add_argument("--apply", action="store_true", help="delete the scripted demo rows")
    args = parser.parse_args()

    counts = run_cli(purge(apply=args.apply))
    verb = "Deleted" if args.apply else "Would delete"
    if not counts.get("cases_found"):
        print("No scripted demo cases present; nothing to do.")
        return
    for table, count in counts.items():
        if table == "cases_found" or not count:
            continue
        print(f"{verb} {count:>4} row(s) from {table}")


if __name__ == "__main__":
    main()
