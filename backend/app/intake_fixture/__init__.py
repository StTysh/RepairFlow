"""The real-intake cases, captured so a clone reproduces them exactly.

`app.seed`, `app.archive` and `app.sample_operations` GENERATE their data
from code, which is why a fresh clone already gets identical properties,
tenants, contractors and 85 cases. This package covers the remainder: the
fourteen cases that were created by driving the running application
rather than by a generator, and which therefore existed only in one
machine's `backend/data/repairflow.db`.

Those cases cannot be regenerated -- they are the record of what actually
happened, including eight genuine coordinator runs against Gemini. So
they are *captured* instead: exported row-for-row into `dataset.json`,
which is committed, and replayed on import.

**No personal data is carried.** `export.py` refuses to write a dataset
containing any, and the one value that ever qualified -- a real mobile
number, hand-edited into a single `tenants` row on one machine -- is out
of scope by construction: this fixture holds no `tenants` rows at all.
`app.seed` already creates every tenant, with a placeholder number and
deterministic ids, before this import runs.

Row ids are the ones the application originally generated, so importing
twice is a no-op and `--remove` deletes exactly what was imported and
nothing adjacent.
"""

from __future__ import annotations

import json
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import sqlalchemy as sa

from app.db import Base
from app.models import (
    UTCDateTime,
    ActionRecordModel,
    AppointmentModel,
    CaseEventModel,
    CommunicationModel,
    ContractorReportModel,
    DependencyModel,
    MessageModel,
    OrchestrationRunModel,
    RepairCaseModel,
    RepairIssueModel,
    WorkOrderModel,
)

DATASET_PATH = Path(__file__).with_name("dataset.json")

# Insert order matters and is not negotiable.
#
# app/models.py declares ZERO relationship() -- only bare ForeignKey
# columns -- so SQLAlchemy has no cross-mapper dependency graph to sort a
# flush by. It inserts in whatever order objects were added, and SQLite's
# foreign_keys pragma then rejects a child that arrives before its
# parent.
#
# The order is DERIVED from the schema rather than hand-listed.
# `Base.metadata.sorted_tables` is a topological sort of the real
# ForeignKey graph, which is the same information the hand-written list
# was trying to restate -- and got wrong: `dependencies` carries
# `discovered_from_report_id`, so it has to follow `contractor_reports`,
# not precede it. Deriving it means a new foreign key cannot silently
# invalidate this list.
#
# Deletion walks it in reverse.
_MODELS: tuple[type, ...] = (
    RepairCaseModel,
    RepairIssueModel,
    WorkOrderModel,
    DependencyModel,
    AppointmentModel,
    ContractorReportModel,
    CommunicationModel,
    MessageModel,
    OrchestrationRunModel,
    ActionRecordModel,
    CaseEventModel,
)


def _dependency_order(models: tuple[type, ...]) -> tuple[type, ...]:
    by_table = {m.__tablename__: m for m in models}
    ordered = [by_table[t.name] for t in Base.metadata.sorted_tables if t.name in by_table]
    # A model missing from the sort would silently never be imported.
    assert len(ordered) == len(models), "every fixture table must appear in the metadata sort"
    return tuple(ordered)


TABLE_ORDER: tuple[type, ...] = _dependency_order(_MODELS)

# How each table is reached from a case id. RepairCaseModel is the root.
CASE_COLUMN: dict[type, str] = {
    RepairCaseModel: "id",
    RepairIssueModel: "case_id",
    WorkOrderModel: "case_id",
    DependencyModel: "case_id",
    AppointmentModel: "case_id",
    ContractorReportModel: "case_id",
    CommunicationModel: "case_id",
    MessageModel: "case_id",
    OrchestrationRunModel: "case_id",
    ActionRecordModel: "case_id",
    CaseEventModel: "case_id",
}


def load_dataset(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    target = path or DATASET_PATH
    if not target.exists():
        return {}
    with target.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload.get("tables", {})


def dataset_case_ids(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    return [row["id"] for row in tables.get("repair_cases", [])]


@dataclass
class ApplyResult:
    skipped: bool = False
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class RemoveResult:
    found: bool = False
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)



def _self_referential_columns(model: type) -> list[str]:
    """Columns whose ForeignKey points back at this model's own table.

    Only `case_events.causation_event_id` qualifies today. A table sort
    cannot help here: the ordering problem is between ROWS of one table,
    not between tables, so these are deferred to a second pass.
    """
    table = model.__table__
    return [
        c.name
        for c in table.columns
        if any(fk.column.table.name == table.name for fk in c.foreign_keys)
    ]


def _coerce(model: type, row: dict[str, Any]) -> dict[str, Any]:
    """Turn a JSON row back into what the column types expect.

    `UTCDateTime` is a TypeDecorator whose bind step calls
    `value.tzinfo`, so it must be handed a real aware `datetime`, not the
    ISO string JSON round-tripped it into. Everything else -- enums, JSON
    columns, ints -- SQLAlchemy coerces itself.
    """
    columns = model.__table__.columns
    out: dict[str, Any] = {}
    for key, value in row.items():
        column = columns.get(key)
        if column is None:
            # A key the running schema no longer has: a dataset captured
            # before a migration still imports afterwards.
            continue
        if isinstance(column.type, UTCDateTime) and isinstance(value, str):
            value = datetime.fromisoformat(value)
        out[key] = value
    return out


async def apply_fixture(
    session_scope: Callable[[], Any],
    tables: dict[str, list[dict[str, Any]]] | None = None,
) -> ApplyResult:
    """Insert every captured row. Idempotent: an id already present is left alone."""
    data = tables if tables is not None else load_dataset()
    if not data:
        return ApplyResult(skipped=True)

    case_ids = dataset_case_ids(data)
    async with session_scope() as session:
        existing = set(
            (
                await session.execute(
                    sa.select(RepairCaseModel.id).where(RepairCaseModel.id.in_(case_ids))
                )
            ).scalars()
        )
    if len(existing) == len(case_ids):
        return ApplyResult(skipped=True)

    counts: dict[str, int] = {}
    # One transaction per table, in dependency order. A single transaction
    # would be tidier, but the flush-ordering problem described above means
    # parent rows must be committed before children are even staged.
    for model in TABLE_ORDER:
        rows = data.get(model.__tablename__, [])
        if not rows:
            continue
        deferred = _self_referential_columns(model)
        async with session_scope() as session:
            present = set(
                (
                    await session.execute(
                        sa.select(model.id).where(model.id.in_([r["id"] for r in rows]))
                    )
                ).scalars()
            )
            written = 0
            for row in rows:
                if row["id"] in present:
                    continue
                values = _coerce(model, row)
                # Pass one: null out any pointer into this same table, so
                # a row can be inserted before the row it points at.
                for column in deferred:
                    values[column] = None
                session.add(model(**values))
                written += 1
            if written:
                counts[model.__tablename__] = written

        # Pass two: now that every row exists, restore the self-references.
        if deferred and written:
            async with session_scope() as session:
                for row in rows:
                    updates = {c: row.get(c) for c in deferred if row.get(c) is not None}
                    if not updates:
                        continue
                    await session.execute(
                        sa.update(model).where(model.id == row["id"]).values(**updates)
                    )
    return ApplyResult(skipped=False, counts=counts)


async def remove_fixture(
    session_scope: Callable[[], Any],
    tables: dict[str, list[dict[str, Any]]] | None = None,
) -> RemoveResult:
    """Delete exactly the captured rows, by id. Nothing adjacent."""
    data = tables if tables is not None else load_dataset()
    if not data:
        return RemoveResult(found=False)

    counts: dict[str, int] = {}
    found = False
    for model in reversed(TABLE_ORDER):
        ids = [r["id"] for r in data.get(model.__tablename__, [])]
        if not ids:
            continue
        async with session_scope() as session:
            result = await session.execute(sa.delete(model).where(model.id.in_(ids)))
            if result.rowcount:
                counts[model.__tablename__] = result.rowcount
                found = True
    return RemoveResult(found=found, counts=counts)


async def status(
    session_scope: Callable[[], Any],
    tables: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, tuple[int, int]]:
    """{table: (present, expected)} for everything the dataset describes."""
    data = tables if tables is not None else load_dataset()
    out: dict[str, tuple[int, int]] = {}
    for model in TABLE_ORDER:
        rows = data.get(model.__tablename__, [])
        if not rows:
            continue
        async with session_scope() as session:
            present = len(
                (
                    await session.execute(
                        sa.select(model.id).where(model.id.in_([r["id"] for r in rows]))
                    )
                )
                .scalars()
                .all()
            )
        out[model.__tablename__] = (present, len(rows))
    return out


async def validate(
    session_scope: Callable[[], Any],
    tables: dict[str, list[dict[str, Any]]] | None = None,
) -> Report:
    data = tables if tables is not None else load_dataset()
    report = Report()

    if not data:
        report.checks.append(Check("dataset_present", False, "dataset.json is missing or empty"))
        return report
    report.checks.append(
        Check(
            "dataset_present",
            True,
            f"{sum(len(v) for v in data.values())} row(s) across {len(data)} table(s)",
        )
    )

    counts = await status(session_scope, data)
    complete = [t for t, (p, e) in counts.items() if p == e]
    report.checks.append(
        Check(
            "every_captured_row_is_present",
            len(complete) == len(counts),
            f"{len(complete)}/{len(counts)} table(s) fully imported",
        )
    )

    case_ids = dataset_case_ids(data)
    async with session_scope() as session:
        # Not archival: these are live operational cases and must appear on
        # the operational surfaces, which filter on archive_batch_id IS NULL.
        archived = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(RepairCaseModel)
                .where(
                    RepairCaseModel.id.in_(case_ids),
                    RepairCaseModel.archive_batch_id.is_not(None),
                )
            )
        ).scalar_one()
        report.checks.append(
            Check(
                "no_case_is_marked_archival",
                archived == 0,
                f"{archived} case(s) carry an archive_batch_id",
            )
        )

        # Foreign keys pointing outside this fixture must resolve against what
        # app.seed created, or the import produced a case referring to a
        # property that does not exist.
        orphans = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(RepairCaseModel)
                .where(
                    RepairCaseModel.id.in_(case_ids),
                    RepairCaseModel.property_id.not_in(sa.select(sa.text("id from properties"))),
                )
            )
        ).scalar_one()
        report.checks.append(
            Check(
                "every_case_property_exists",
                orphans == 0,
                f"{orphans} case(s) point at a missing property",
            )
        )

        distinct_numbers = (
            await session.execute(
                sa.select(sa.func.count(sa.distinct(RepairCaseModel.case_number))).where(
                    RepairCaseModel.id.in_(case_ids)
                )
            )
        ).scalar_one()
        report.checks.append(
            Check(
                "case_numbers_are_unique",
                distinct_numbers == len(case_ids),
                f"{distinct_numbers} distinct number(s) for {len(case_ids)} case(s)",
            )
        )

    return report
