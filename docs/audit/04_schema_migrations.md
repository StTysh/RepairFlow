# Schema/Migrations Audit — persistence

Scope: `backend/app/models.py`, `backend/app/db.py`, `backend/alembic/`, and their relationship to `docs/17_DATABASE_DESIGN.md`. Cross-referenced against every query in `backend/app/analytics.py`, `backend/app/api/*.py`, `backend/app/domain/services.py`, and the deletion paths in `backend/app/archive/importer.py`, `backend/app/legacy_demo_purge.py`, `backend/app/api/documents.py`. Read-only; server never started. `backend/data/repairflow.db` was never opened for writing — every empirical claim below was run against a plain file copy in the scratchpad (`.../scratchpad/audit/repairflow_copy.db`), or against a brand-new throwaway SQLite file for the `alembic upgrade head` test.

## Severity counts
CRITICAL: 3 · HIGH: 5 · MEDIUM: 4 · LOW: 2 · NIT: 2

## Top three
1. **docs/17's own contract ("Enums have CHECK constraints") is false for the real schema — zero enum CHECK constraints exist anywhere**, because `enum_column()` never sets `create_constraint=True` and SQLAlchemy 2.0 defaults it to `False`. Confirmed by scanning all 22 tables in the live DB copy: only 3 CHECK constraints exist total, none of them enum-related.
2. **Standalone maintenance scripts (`legacy_demo_purge.py`, `backfill_category.py`, `app.archive`) crash against the actual current production database** — reproduced live: `python -m app.legacy_demo_purge --dry-run` against a verbatim copy of the real DB dies with `OperationalError: no such table: cost_entries`, because only `main.py`'s FastAPI lifespan calls `create_all()`; these scripts call `session_scope()` directly and never bootstrap the schema themselves.
3. **`_add_missing_columns` silently produces a nullable, default-less column when a new column is `nullable=False` with only a `server_default`** (reproduced: resulting SQLite column has `notnull=0`, `dflt_value=None`, and a raw INSERT omitting it stores `NULL`), and **never creates new indexes on existing tables** — confirmed by the real production DB missing all five `archive_batch_id` indexes the current model declares, which is why `WHERE archive_batch_id IS NULL` — the leading filter in nearly every `analytics.py` function — is a full table scan (`EXPLAIN QUERY PLAN` → `SCAN repair_cases`) today, not just at some future archival scale.

---

## Table inventory: models.py × Alembic

25 tables declared in `Base.metadata` (`backend/app/models.py`). Alembic, after all three revisions (`79a18de7e45a` → `496bf82ee3e9` → `dd3584cdf57b`), creates 21. **Empirically verified** by running `alembic upgrade head` against a brand-new empty SQLite file and diffing `sqlite_master`/`PRAGMA table_info` against `Base.metadata.tables` programmatically.

| Table | Alembic creates it? | Column drift (alembic vs current models.py) |
|---|---|---|
| properties | yes | missing `property_type`, `bedrooms`, `photo_key`, `archive_batch_id` |
| tenants | yes | missing `archive_batch_id` |
| contractors | yes | missing `archive_batch_id`, `workers` |
| repair_cases | yes | missing `category`, `archive_batch_id`, `archived_closed_at` |
| repair_issues | yes | none |
| work_orders | yes | none |
| dependencies | yes | none |
| appointments | yes | none |
| availability_windows | yes | none |
| contractor_reports | yes | none |
| contractor_candidates | yes | none |
| research_snapshots | yes | none |
| communications | yes | none |
| messages | yes (rev. `dd3584cdf57b`, minimal shape) | missing `channel`, `delivery_state`, `delivery_detail`, `queued_at`, `delivered_at`, `read_at`, `attachments`, `communication_id`, `archive_batch_id` |
| webhook_receipts | yes | none |
| case_events | yes | none |
| action_records | yes | none |
| jobs | yes | enum literal list for `kind` missing `PLACE_CALL` (see Finding 10 — functionally inert, documentation drift) |
| orchestration_runs | yes | none |
| mock_slots | yes | none |
| mock_reservations | yes | none |
| **archive_batches** | **no** | table absent entirely |
| **notes** | **no** | table absent entirely |
| **documents** | **no** | table absent entirely |
| **cost_entries** | **no** | table absent entirely |

**Does `alembic upgrade head` on an empty database produce a working schema? No.** It produces a schema 4 tables and 17 columns short of what `models.py`/the running app requires. Every endpoint touching notes, documents, costs, or archive import would fail immediately (`no such table`). The only reason the app "works" in practice is that `main.py`'s lifespan (`backend/app/main.py:43`) always calls `create_all()` on boot, which both creates the 4 missing tables (the `if table.name not in existing_tables` branch in `_add_missing_columns`, `db.py:93`, is skipped for them — `Base.metadata.create_all` at `db.py:164` creates them directly) and backfills the missing columns on the 5 already-existing tables above. **Alembic is not a substitute for booting the app at least once; nothing in the repo states that dependency.**

---

## CONFIRMED

### 1. CRITICAL — docs/17's contract ("Enums have CHECK constraints") is false; zero enum-level CHECK constraints exist in the real schema, on either bootstrap path
`backend/app/models.py:74-79`, `backend/app/db.py` (both bootstrap paths), `docs/17_DATABASE_DESIGN.md:43` ("Enums have CHECK constraints.")

```python
def enum_column(py_enum, *, nullable: bool = False, default=None, name: str | None = None):
    return mapped_column(
        sa.Enum(py_enum, native_enum=False, validate_strings=True, length=40, name=name),
        nullable=nullable,
        default=default,
    )
```

No `create_constraint=True`. As of SQLAlchemy 2.0 (installed: **2.0.54**, verified via `python -c "import sqlalchemy; print(sqlalchemy.__version__)"`), `Enum`'s `create_constraint` default is `False` — a deliberate 1.4→2.0 behavior change. Scanning every table in the real production DB copy:

```
availability_windows -> HAS CHECK
dependencies -> HAS CHECK
repair_cases -> HAS CHECK
tables with any CHECK: 3 / 22
```

All 3 are the explicit `sa.CheckConstraint(...)` rows in `__table_args__` (`ck_case_version_positive`, `ck_dependency_not_self`, `ck_availability_window_order`) — **none are enum CHECKs**. Confirmed the exact same absence on a schema freshly built by `alembic upgrade head` (that revision's `op.create_table` calls also pass bare `sa.Enum(...)` with no `create_constraint=True`):

```sql
CREATE TABLE jobs ( ... kind VARCHAR(40) NOT NULL, ... )   -- no CHECK
```
```
INSERT INTO jobs (..., kind, ...) VALUES (..., 'PLACE_CALL', ...)
INSERT OK: PLACE_CALL accepted (no CHECK enforced)
```

The only remaining protection is `validate_strings=True`, which is **Python/ORM-side only** — confirmed by reproducing it: `JobModel(kind="NOT_A_REAL_KIND")` raises `StatementError(LookupError)` at `session.flush()`, before any SQL is sent. This protects ordinary ORM writes but not: raw SQL (`_add_missing_columns`'s `exec_driver_sql`), Core `insert()` calls that skip attribute-level validation, any future migration, or **reading back a legacy row whose stored value is no longer a declared enum member** — SQLAlchemy's `Enum` result-processing re-validates on read when `validate_strings=True`, so a row written under an older enum definition raises on SELECT, not silently. This is exactly the failure mode `schemas.py:236-242` already documents for `EventType` (a plain-string column, so no ORM-side check at all) — except every genuine `enum_column()` field carries the same risk with one added twist: the enum member could be *removed/renamed* later, and old rows referencing it would 500 on the very next read, not just on write of a new value.

**Failure scenario:** a future migration or backfill script writes a raw string into any `enum_column()`-typed column via `exec_driver_sql`/Core (as `_add_missing_columns` itself already does for its backfill `UPDATE`, currently safe only because it always derives the value from the column's own declared Python default). A typo or a soon-to-be-renamed member goes in silently; the row is unreadable through the ORM (and therefore through every API endpoint that touches it) from that point on.

**Smallest correct fix:** add `create_constraint=True` to `enum_column()` in `models.py:74-79`. This alone does not retroactively fix already-deployed tables (see Finding 3b — `_add_missing_columns` cannot add constraints to existing tables either); a reviewed Alembic revision would still be needed to backfill the CHECKs onto the live database via SQLite's `ALTER TABLE ... RENAME TO` + recreate dance (`render_as_batch=True`, already configured in `alembic/env.py`).

**No current data corruption found.** Grepped every write site for `CaseStatus`, `WorkOrderStatus`, `AppointmentStatus`, `CommState`, `ActionState`, `JobStatus`, `JobKind`, `MessageChannel`, `MessageDeliveryState`, `CostKind`, `RecordSubject`, and `EventType` across `backend/app/` — every one uses the Python enum member (or `.value` of one), never a bare literal that could diverge from the declared set. This finding is structural/latent, not evidence of an already-corrupted row.

---

### 2. CRITICAL — Standalone maintenance scripts crash against the real, currently-deployed database; only the FastAPI process ever bootstraps the schema
`backend/app/db.py:57-67` (`session_scope`, used by all three scripts below), `backend/app/db.py:159-167` (`create_all`, called only from `backend/app/main.py:43`), `backend/app/legacy_demo_purge.py`, `backend/app/backfill_category.py`, `backend/app/archive/__main__.py`.

Reproduced directly against a byte-for-byte copy of `backend/data/repairflow.db` (never the live file):

```
$ python -m app.legacy_demo_purge --dry-run
...
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table: cost_entries
[SQL: SELECT count(*) AS count_1 FROM cost_entries WHERE cost_entries.case_id IN (...)]
```

The real database (confirmed: 22 tables, no `archive_batches`/`cost_entries`/`documents`/`notes` — see the table inventory above) predates `CostEntryModel`. `session_scope()` never calls `create_all()`; only `main.py`'s `lifespan()` does. Any script built on `session_scope()` inherits whatever schema the file happens to be at, with no bootstrap of its own.

**Failure scenario:** an operator runs `python -m app.legacy_demo_purge --apply`, `python -m app.backfill_category --apply`, or `python -m app.archive --apply`/`--remove` against the real database (per the modules' own documented CLI usage) without having booted the FastAPI app since the last schema change — the exact situation this database is in right now — and gets a raw driver traceback instead of useful output. For `legacy_demo_purge.py` specifically this happens to be safe today (the crash occurs on a `SELECT count(*)` before any `DELETE` in that iteration runs — see Finding 4/CONFIRMED-clean below), but the general class of bug (a script that deletes some rows, then crashes on a later, schema-drifted table) is real and unguarded against.

**Smallest correct fix:** each of these three entry points should call `await create_all()` as its first action, exactly as `main.py`'s lifespan does.

---

### 3a. CRITICAL — `_add_missing_columns` silently drops NOT NULL and `server_default` for a new column that relies on `server_default` alone
`backend/app/db.py:92-127`, specifically:

```python
if not column.nullable and column.default is None and column.server_default is None:
    raise RuntimeError(...)          # only guards the *no default at all* case
ddl_type = column.type.compile(dialect=conn.dialect)
conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}')
```

`column.type.compile()` renders only the type (e.g. `VARCHAR(20)`) — never `NOT NULL`, never `DEFAULT`. Reproduced directly: built a column `nullable=False, server_default=sa.text("'ACTIVE'")`, ran the identical `ALTER TABLE` statement this function emits:

```
Executing: ALTER TABLE "t" ADD COLUMN "status" VARCHAR(20)
table_info after ALTER: [(0, 'id', ..., notnull=0, ...), (1, 'status', 'VARCHAR(20)', notnull=0, dflt_value=None, 0)]
row after insert with column omitted: [('row1', None)]
```

The guard at line 99 only fires when *no* default exists at all; a column with `server_default` set (but no Python-side `default=`) sails past it, and the ALTER TABLE that follows creates the column **nullable, with no DEFAULT clause whatsoever** — directly contradicting both the model's `nullable=False` and the intended `server_default`. A raw INSERT (or any Core statement) that omits the column gets `NULL`, not the intended default.

**Failure scenario:** the moment any future column is declared `nullable=False, server_default=...` (a natural pattern for "every row gets X unless overridden"), on any already-bootstrapped database it becomes a silently-nullable, default-less column instead. No current model column matches this exact shape, so there is no live corruption today — this is a proven latent trap for the next migration that uses this pattern.

**Smallest correct fix:** in `_add_missing_columns`, when `column.server_default is not None`, compile and append it to the ALTER TABLE DDL (`ADD COLUMN "{name}" {ddl_type} DEFAULT {compiled_server_default}`), and append `NOT NULL` when `not column.nullable` (SQLite permits this combination on `ALTER TABLE ADD COLUMN` as long as a non-null default is present).

### 3b. CRITICAL — `_add_missing_columns`/`create_all` never create indexes on an already-existing table; 5 declared indexes are missing from the real production database right now
`backend/app/db.py:92-127` (no index-diffing logic at all), `backend/app/models.py` (5 `index=True` columns).

`Base.metadata.create_all(checkfirst=True)` (the default, used at `db.py:164`) skips a table's entire DDL — including its indexes — once the table exists. `_add_missing_columns` only ever adds columns; it has no code path that inspects or creates indexes. Confirmed empirically: after running `create_all()` against the real DB copy (which correctly added the 17 missing columns from the table above), these 5 indexes the current model declares are **still absent**:

```
('properties', 'ix_properties_archive_batch_id', ['archive_batch_id'])
('tenants', 'ix_tenants_archive_batch_id', ['archive_batch_id'])
('contractors', 'ix_contractors_archive_batch_id', ['archive_batch_id'])
('repair_cases', 'ix_repair_cases_archive_batch_id', ['archive_batch_id'])
('messages', 'ix_messages_archive_batch_id', ['archive_batch_id'])
```

`RepairCaseModel.archive_batch_id` in particular is the leading filter of nearly every function in `analytics.py` (`_apply_case_filters`, `portfolio_counts`, `operational_status_counts`, `needs_attention`, `recent_activity`, `open_age_buckets`) via `.is_(None)`/`.is_not(None)`. Real `EXPLAIN QUERY PLAN` against the (already column-upgraded) copy:

```
EXPLAIN QUERY PLAN SELECT count(*) FROM repair_cases WHERE archive_batch_id IS NULL
  SCAN repair_cases
EXPLAIN QUERY PLAN SELECT count(*) FROM properties WHERE archive_batch_id IS NULL
  SCAN properties
```

**This is not a future-scale worry — it is the current, unindexed state of the actual production database**, and it will get materially worse as archival history grows past the stated 60+ case mark (each of these functions is called on every Overview page load).

**Smallest correct fix:** give `_add_missing_columns` (or a sibling pass in `create_all()`) an index diff: `inspector.get_indexes(table.name)` vs `table.indexes`, and issue `CREATE INDEX IF NOT EXISTS ...` for anything missing, mirroring how columns are already diffed.

---

### 4. HIGH — `needs_attention()`'s cross-case AWAITING_APPROVAL query full-scans `action_records`; the documented index can't serve it
`backend/app/analytics.py:239-247`, `docs/17_DATABASE_DESIGN.md:57` ("action_records | ... index case/state").

```python
select(ActionRecordModel, RepairCaseModel.case_number, RepairCaseModel.title)
    .join(RepairCaseModel, RepairCaseModel.id == ActionRecordModel.case_id)
    .where(ActionRecordModel.state == "AWAITING_APPROVAL", RepairCaseModel.archive_batch_id.is_(None))
```

`ix_action_case_state` is `(case_id, state)` — a composite whose leading column is `case_id`, so it cannot serve a query that filters on `state` alone across every case. Real EXPLAIN:

```
SCAN action_records
SEARCH repair_cases USING INDEX sqlite_autoindex_repair_cases_1 (id=?)
```

This runs on every Overview page load. The documented contract in docs/17 (which only prescribes the `(case_id, state)` composite) does not cover this cross-case access pattern.

**Smallest correct fix:** add a second index on `action_records(state)` (or `(state, case_id)`).

### 5. HIGH — `repair_cases.next_follow_up_at` has no index; the overdue-follow-up query full-scans
`backend/app/analytics.py:276-289`.

```python
select(RepairCaseModel).where(
    RepairCaseModel.next_follow_up_at.is_not(None),
    RepairCaseModel.next_follow_up_at < now,
    RepairCaseModel.archive_batch_id.is_(None),
    RepairCaseModel.status.notin_([CaseStatus.RESOLVED, CaseStatus.CANCELLED]),
)
```
Real EXPLAIN: `SCAN repair_cases`. Low absolute cost today (live case count is small), but it's on the hottest page (Overview) and there is no index that could serve it even partially.

**Smallest correct fix:** index `repair_cases(next_follow_up_at)`.

### 6. HIGH — `sweep_stale_live_calls()` full-scans `communications` on a permanent 5-second timer
`backend/app/orchestration/worker.py:148-176`.

```python
select(CommunicationModel).where(
    CommunicationModel.state.in_(["ACTIVE", "REQUESTED"]),
    CommunicationModel.provider_conversation_id.is_not(None),
    CommunicationModel.provenance == "LIVE",
    CommunicationModel.started_at < cutoff,
)
```
Only index on `communications` is `ix_communication_case` (`case_id`) — none of `state`/`provenance`/`started_at` is covered. Real EXPLAIN: `SCAN communications`. Harmless at today's 13 rows, but this runs unconditionally every `RECONCILE_SWEEP_INTERVAL_SECONDS` (5s) forever whenever ElevenLabs is configured — a standing cost that scales with cumulative call volume, not case volume, so it's on a different growth curve than the archival-case concern the brief called out.

**Smallest correct fix:** index `communications(state, started_at)` (covers the two most selective predicates together).

### 7. HIGH — `JobModel.case_id` has no index; the 5,618-row `jobs` table is scanned for any per-case lookup
`backend/app/archive/importer.py:560-566` (`validate()`'s `no_jobs` check):
```python
select(func.count()).select_from(JobModel).where(JobModel.case_id.in_(case_ids))
```
Real EXPLAIN: `SCAN jobs` (216 estimated cost units, on a table that already has 5,618 real rows). The only indexes on `jobs` are the composites `(status, run_at)` and `(lease_until,)` (plus the `dedupe_key` unique) — none serve a bare `case_id` filter. Not a hot path today (only runs from the archive validator), but it is the one place in the codebase that already demonstrates the cost at the stated 5,000+ row scale.

**Smallest correct fix:** index `jobs(case_id)`.

### 8. HIGH (confirmed, not a bug) — `alembic upgrade head` alone is materially incomplete; the app's own `create_all()` boot step is a silent, undocumented second migration stage
See the table inventory section above for the full empirical diff. Restated as its own finding because it directly answers the brief's question: **no**, running only the migrations does not produce a working schema — 4 tables and 17+ columns are missing, and nothing in `README`/`docs/17`/the alembic files states that a first application boot is a required second step. Anyone building a deploy/CI pipeline that runs `alembic upgrade head` and then points non-app tooling (a report script, a DB dump, a monitoring query) at the database before the app has booted at least once will observe exactly the same `no such table`/`no such column` failures reproduced in Findings 2 and the table inventory.

---

## MEDIUM

### 9. MEDIUM — `claim_job`'s LEASED-reclaim query bypasses `ix_job_lease_until`, sorts in a temp B-tree instead
`backend/app/orchestration/worker.py:59-63`:
```python
select(JobModel).where(JobModel.status == "LEASED", JobModel.lease_until < now).order_by(JobModel.lease_until).limit(1)
```
Real EXPLAIN:
```
SEARCH jobs USING INDEX ix_job_status_runat (status=?)
USE TEMP B-TREE FOR ORDER BY
```
SQLite picks the `(status, run_at)` composite to filter `status='LEASED'`, then sorts the matched rows by `lease_until` in a temporary B-tree rather than using the single-column `ix_job_lease_until` index, because that index alone doesn't also cover the `status` predicate. Harmless while few jobs are ever LEASED at once; degrades if reclaim ever backs up (e.g. after a crash leaves many jobs LEASED simultaneously).

**Smallest correct fix:** add a composite `jobs(status, lease_until)` index mirroring `ix_job_status_runat`.

### 10. MEDIUM — Alembic's literal enum-value list for `jobs.kind` is stale (missing `PLACE_CALL`) — documentation drift, confirmed functionally inert
`backend/alembic/versions/79a18de7e45a_initial_schema.py`:
```python
sa.Column('kind', sa.Enum('COORDINATE', 'EXECUTE_ACTION', 'FETCH_RECORDING', 'FOLLOW_UP', name='jobkind', ...), nullable=False),
```
`JobKind` in `schemas.py` also has `PLACE_CALL`. Verified this causes **no runtime symptom today**: per Finding 1, neither bootstrap path ever renders a CHECK constraint for enum columns, so the stale list is inert. It is still worth flagging as misleading documentation: anyone hand-reading the migration history to understand "what values are actually allowed" is told something false, and the moment Finding 1 is fixed (`create_constraint=True`), this specific migration would need to be regenerated or it would enforce the wrong (narrower) list on a database bootstrapped via Alembic.

### 11. MEDIUM — `portfolio_counts`'s docstring/logic assumes contractors have no archive lineage; that's no longer true
`backend/app/analytics.py:147-155` docstring: *"Contractors have no archive_batch_id column (the import never fabricates contractor rows)"* — but `backend/app/models.py:153-155` gives `ContractorModel` an `archive_batch_id` column, and `backend/app/archive/importer.py:198` sets it (`archive_batch_id=batch_id`) on every archival contractor row it creates. `approved_contractor_count`'s query never filters `archive_batch_id`:
```python
select(func.count()).select_from(ContractorModel).where(ContractorModel.approval_status == "APPROVED")
```
**Currently harmless**: the importer always sets archival contractors to `approval_status=PENDING` (never `APPROVED`), so no archival contractor is counted today. But this is an invariant enforced only by the importer's current behavior, not by this query — the metric would silently start blending archival and real contractors the moment that changes, and (per Finding 3b) there isn't even an index on `contractors.archive_batch_id` to make filtering it cheap.

### 12. MEDIUM — A naive-but-syntactically-valid ISO cursor 500s instead of 400ing `GET /cases`
`backend/app/api/cases.py:107-112`:
```python
try:
    cursor_dt = datetime.fromisoformat(cursor)
except ValueError:
    raise DomainError(f"cursor {cursor!r} is not a valid ISO-8601 timestamp")
query = query.where(RepairCaseModel.updated_at < cursor_dt)
```
`datetime.fromisoformat("2026-09-20T00:00:00")` (no UTC offset) **succeeds** — it produces a naive `datetime`, so the `except ValueError` guard never fires. The naive value then reaches `UTCDateTime.process_bind_param` (`backend/app/models.py:61-66`) during query execution:
```python
if value.tzinfo is None:
    raise ValueError("naive datetime rejected: all stored timestamps must be timezone-aware")
```
`backend/app/api/errors.py` registers a handler only for `DomainError` (line 28); a bare `ValueError` is unhandled and becomes a generic framework 500. Same shape exists in `backend/app/api/messaging.py:211`.

**Smallest correct fix:** after parsing, check `cursor_dt.tzinfo is None` and raise `DomainError` explicitly (mirroring the existing `except ValueError` branch), in both `cases.py` and `messaging.py`.

---

## LOW

### 13. LOW — A naive tenant-reported `started_at` is silently dropped, not interpreted or surfaced
`backend/app/domain/services.py:368-376`:
```python
elif fact.field == "started_at" and fact.value:
    try:
        parsed = datetime.fromisoformat(str(fact.value))
    except ValueError:
        pass
    else:
        if parsed.tzinfo is not None and parsed != issue.started_at:
            issue.started_at = parsed
```
A plain local date/time from a voice transcript (no UTC offset) parses successfully but is then silently discarded (`if parsed.tzinfo is not None`) — no error, no `unresolved_concerns` entry, no interpretation against `property.timezone`. Not a crash; a quiet data-loss path worth a one-line fix (append to `unresolved_concerns` when discarded) rather than a schema change.

### 14. LOW — Free-text case search is an inherent full scan; no index can help
`backend/app/api/cases.py` (`q` filter): `like = f"%{q}%"` — leading-wildcard `LIKE` defeats any B-tree index by construction. Not a missing-index bug so much as a documented scaling ceiling; `docs/17` doesn't mention a search strategy at all, so there's nothing to correct it against.

---

## NIT

### 15. NIT — Not every archive-import-populated table carries its own lineage column
`RepairIssueModel`, `WorkOrderModel`, `AppointmentModel`, `ActionRecordModel` have no `archive_batch_id`/`provenance-of-import` column of their own; `archive/importer.py`'s module docstring already documents this as deliberate (they're scoped via `case_id` traversal back to `RepairCaseModel.archive_batch_id` instead). Flagging only because the audit brief asked to check every table's archive lineage — this is a documented, intentional exception, not a bug.

### 16. NIT — Scope note
Nullability-vs-reality (brief item 6) and the "changed column type" / "new column on a table with a composite constraint" / "new table with an FK to a table created later" scenarios (brief item 2) were reasoned through against the actual `_add_missing_columns` code rather than reproduced, since no current model column matches those shapes yet:
- **Changed type**: `_add_missing_columns` only branches on `column.name in present` (`db.py:97-98`) — a column that already exists is never touched again, regardless of type change. SQLite's loose type affinity means this doesn't error; it silently leaves old rows in the old physical representation while new code assumes the new type.
- **New column on a table with a composite constraint**: `ALTER TABLE ADD COLUMN` cannot itself alter an existing `UNIQUE`/`CHECK`; the existing composite constraint is untouched (safe), but if the new column was meant to *join* that composite (e.g. widen a uniqueness rule), that never happens automatically — same class of gap as Finding 3b (indexes/constraints are never added to an existing table by either bootstrap path).
- **New table with an FK to a table created later**: ruled out as a real risk — `db.py:163-165` runs `Base.metadata.create_all` (which creates *all* missing tables, correctly topologically ordered) as a first pass, then `_add_missing_columns` as a second pass, so by the time any `ADD COLUMN` runs, every table `create_all` was going to create already exists.

---

## Confirmed clean / ruled out
- **Money**: exhaustive grep for `float(`, `/ 100`, `pence /` etc. across `backend/app/` found no float arithmetic or lossy division touching any `*_pence` column; `costs.py`, `analytics.py`, and `reports.py` stay integer pence end-to-end everywhere checked.
- **`_add_missing_columns`'s callable-default backfill is correct**: reproduced that SQLAlchemy wraps a bare 0-arg callable (`default=list`, `default=dict`, `default=new_uuid`, `default=utcnow`) so `column.default.arg(None)` returns the right value — confirmed with `list` returning `[]`.
- **`legacy_demo_purge.py`'s delete ordering is correct**: after bringing a copy's schema current (`create_all()`, copy only), ran `--dry-run` (found all 9 real scripted-demo cases still present in production) then `--apply` for real. `PRAGMA foreign_key_check` and `PRAGMA integrity_check` both clean afterward — zero orphans, zero dangling FKs.
- **`documents.py::delete_document` ordering is correct**: DB row delete + flush happens before the on-disk file unlink (`backend/app/api/documents.py:196-208`); worst case on a crash between the two is an orphan file, never a DB row pointing at a deleted file.
- **The untouched real database is internally consistent today**: `PRAGMA foreign_key_check` → 0 rows; `PRAGMA integrity_check` → `ok`.
