"""Capture the non-generated cases from a live database into dataset.json.

Run this on the machine whose database is the source of truth:

    uv run python -m app.intake_fixture --export

It finds every case that `app.archive` and `app.sample_operations` did
NOT create, pulls its rows out of the eleven case-scoped tables, and
writes them to `dataset.json` for committing.

## The personal-data gate

This writes a file into a PUBLIC repository, so it refuses rather than
asks. Before writing, every string in the payload is scanned for:

  - phone numbers that are not one of the placeholder ranges `app.seed`
    uses,
  - email addresses,
  - anything that looks like an API key or bearer token.

A hit aborts the export and names the table, column and row. There is
deliberately no override flag: if real data needs to ship, the fix is to
change the data, not to silence the check.

`tenants`, `properties` and `contractors` are never exported at all --
`app.seed` creates them deterministically, with the same ids, before
this import runs. That is what keeps the one value that has ever
tripped this gate (a real mobile hand-edited into a `tenants` row) out
of scope entirely.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import sqlalchemy as sa

from app.intake_fixture import CASE_COLUMN, DATASET_PATH, TABLE_ORDER
from app.models import RepairCaseModel


class PersonalDataFound(RuntimeError):
    """Raised instead of writing a dataset that carries personal data."""


# `app.seed` issues placeholder numbers in +4411xxxxxxxx. Anything else
# that looks like a phone number did not come from the generator.
_PLACEHOLDER_PHONE = re.compile(r"^\+4411\d{6,8}$")
_PHONE = re.compile(r"\+\d[\d\s().-]{7,}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
# sk-..., xi-..., AIza..., ghp_..., and long opaque bearer-ish blobs.
_SECRET = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|xi-[A-Za-z0-9]{16,})\b")


def _scan_value(value: Any) -> list[str]:
    """Return a list of reasons this value must not be committed."""
    if value is None:
        return []
    if isinstance(value, (dict, list)):
        text = json.dumps(value)
    elif isinstance(value, str):
        text = value
    else:
        return []

    reasons: list[str] = []
    for match in _PHONE.findall(text):
        compact = re.sub(r"[\s().-]", "", match)
        if not _PLACEHOLDER_PHONE.match(compact):
            reasons.append(f"non-placeholder phone number ending {compact[-4:]}")
    if _EMAIL.search(text):
        reasons.append("email address")
    if _SECRET.search(text):
        reasons.append("possible API key or token")
    return reasons


def scan_tables(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Every reason the payload must not be written, with a location."""
    problems: list[str] = []
    for table, rows in tables.items():
        for row in rows:
            for column, value in row.items():
                for reason in _scan_value(value):
                    problems.append(f"{table}.{column} (row id {str(row.get('id'))[:8]}...): {reason}")
    return problems


def _jsonable(value: Any) -> Any:
    """SQLAlchemy hands back datetimes, Decimals and Enums; JSON will not."""
    if value is None or isinstance(value, (str, int, float, bool, dict, list)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):  # enum
        return value.value
    return str(value)


async def collect(
    session_scope: Callable[[], Any],
    case_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}
    for model in TABLE_ORDER:
        column = getattr(model, CASE_COLUMN[model])
        async with session_scope() as session:
            result = await session.execute(sa.select(model).where(column.in_(case_ids)))
            rows = result.scalars().all()
            payload = []
            for row in rows:
                payload.append(
                    {c.name: _jsonable(getattr(row, c.name)) for c in model.__table__.columns}
                )
        if payload:
            # Stable order, so re-exporting an unchanged database produces
            # an identical file and an empty git diff.
            payload.sort(key=lambda r: str(r.get("id")))
            tables[model.__tablename__] = payload
    return tables


async def find_non_generated_case_ids(session_scope: Callable[[], Any]) -> list[str]:
    """Cases that neither generator produced.

    `app.archive` marks its own with `archive_batch_id`. `app.sample_operations`
    does not mark cases, so it is identified the only other way available:
    its rows are deterministic, so a case is "generated" if a freshly
    generated dataset claims its id.
    """
    from app.sample_operations import _case_ids

    generated = set(_case_ids())
    async with session_scope() as session:
        rows = (
            await session.execute(
                sa.select(RepairCaseModel.id).where(RepairCaseModel.archive_batch_id.is_(None))
            )
        ).scalars().all()
    return [r for r in rows if r not in generated]


async def export(
    session_scope: Callable[[], Any],
    path: Path | None = None,
    case_ids: list[str] | None = None,
) -> tuple[Path, dict[str, list[dict[str, Any]]]]:
    ids = case_ids if case_ids is not None else await find_non_generated_case_ids(session_scope)
    tables = await collect(session_scope, ids)

    problems = scan_tables(tables)
    if problems:
        raise PersonalDataFound(
            "Refusing to write dataset.json: it would publish personal data.\n  "
            + "\n  ".join(problems[:20])
            + (f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else "")
        )

    target = path or DATASET_PATH
    payload = {
        "note": (
            "Cases created by driving the running application, captured so a "
            "clone reproduces them. Generated by `python -m app.intake_fixture "
            "--export`; do not hand-edit. Contains no personal data -- the "
            "exporter refuses to write any."
        ),
        "case_count": len(tables.get("repair_cases", [])),
        "tables": tables,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    return target, tables
