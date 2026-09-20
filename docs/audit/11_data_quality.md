# Data Quality Audit — archive, seed, backfill_category, legacy_demo_purge

Scope: `backend/app/archive/` (`dataset.py`, `importer.py`, `__main__.py`), `backend/app/seed.py`, `backend/app/backfill_category.py`, `backend/app/legacy_demo_purge.py`. Read-only; no server started; `backend/data/repairflow.db` was never opened for writing (only `cp`'d to the scratchpad). All findings below were produced by running the actual production code — `app.archive.importer.import_archive/remove_archive/validate`, `app.seed.seed`, `app.backfill_category.plan/apply_changes`, `app.legacy_demo_purge.purge`, and real ASGI requests against `app.main.app` via `httpx.ASGITransport` (no lifespan, no worker loop, no uvicorn) — against throwaway SQLite databases (`DATABASE_PATH`/`DOCUMENTS_DIR` repointed), plus independent raw-SQL checks written from scratch against the resulting files.

## Severity counts

CRITICAL: 0 · HIGH: 3 · MEDIUM: 1 · LOW: 1 · NIT: 1

## Verdict on the 13/13

I agree the archive's own `--validate` genuinely passes 13/13 — I reproduced every one of those 13 pass results independently in raw SQL against a fresh import (batch `b901bea4…`, 60 cases / 600 rows). But two of the thirteen check *names* promise more than their bodies check, and both gaps are real, reproducible data-quality bugs, not just naming nitpicks: `no_open_or_pending_work` only reads the `status` enum column and never asks whether a `COMPLETED` work order has any appointment evidencing that completion (25% of them don't), and `cost_totals_reconcile` only self-reconciles `CostEntryModel` against itself — it never reconciles against `WorkOrderModel.quote_pence`, which is the number `GET /properties/{id}/stats` actually charts (this is the archival instance of `docs/audit/06_analytics_metrics.md`'s CRITICAL #1, and the archive's validator doesn't catch its own copy of that bug).

## Top three

1. **HIGH** — 22/87 (25%) archival work orders are marked `COMPLETED` with zero backing `AppointmentModel` row ever created; one (`case #51`) has a work order `created_at` that falls *after* its own case's `archived_closed_at`. `no_open_or_pending_work` doesn't catch this because it only checks the status enum.
2. **HIGH** — `backfill_category` picks the wrong trade when a case's first-raised, `required_for_resolution=True` work order was later `CANCELLED` (misdiagnosis) and a different-trade work order actually resolved the case: reproduced live, it set `category=ELECTRICAL` on a case a plumber actually fixed, disagreeing with the codebase's own `_pick_primary_trade` (`services.py:1050-1072`), which explicitly excludes `CANCELLED` work orders "for this exact reason" per its own docstring.
3. **HIGH** — `cost_totals_reconcile` is a self-check, not a reconciliation: for 29/60 archival cases (48%), `WorkOrderModel.quote_pence` totals (what Property Stats charts) and `CostEntryModel(kind=QUOTE)` totals (what the cost ledger/Insights/Reports chart) disagree, sometimes by 3x (case #3: £1,199.93 vs £354.71), because costs are only ever generated from `case.work_orders[0]`.

Everything else I was asked to independently verify — `--remove` completeness (all 13 tables, `PRAGMA foreign_key_check`, all 12 document files, control-row survival, clean re-import), archival containment (proved live over HTTP on a mixed DB across the 5 named surfaces, with a deliberate `include_archived=true` sanity check that it *does* work), `app.seed` idempotency (3 runs, byte-identical), and `legacy_demo_purge` on a copy of the real dev database (exactly the 9 scripted cases removed, cases #1-5 and their 3 genuine LIVE ElevenLabs communications/transcripts untouched) — came back clean. Details below.

---

## CONFIRMED

### 1. HIGH — `COMPLETED` work orders with no attended visit; one work order created after its case closed

**Where:** `backend/app/archive/dataset.py:595-666` (`_fill_resolved_case`); validated (or rather, not caught) by `backend/app/archive/importer.py:538-553` (`no_open_or_pending_work`) and `:489-519` (`timestamps_ordered_and_past`).

**Root cause:** a resolved case gets 1-3 work orders (`rng.choices([1,2,3], weights=[55,35,10])`), all unconditionally set `status=WorkOrderStatus.COMPLETED`. But the appointment loop right below only ever books against `work_order_index` 0 or, with 50% probability, 1 — `work_order_index 2` is never referenced anywhere. Even for 2-work-order cases, there's only a coin-flip chance the second one gets an appointment at all. The result: a work order can be `COMPLETED` in the database while no contractor ever attended it in the fixture's own history.

**Query (independent, not the importer's own check):**
```sql
SELECT wo.id, wo.case_id, wo.status, wo.created_at
FROM work_orders wo
WHERE wo.status='COMPLETED'
  AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.work_order_id = wo.id);
```
**Actual output:** 22 rows (of 87 work orders total, 25.3%).

**Second symptom of the same flaw — a work order created after its own case was closed:**
```sql
SELECT wo.id, wo.case_id, wo.created_at, c.created_at AS case_created, c.archived_closed_at
FROM work_orders wo JOIN repair_cases c ON c.id = wo.case_id
WHERE c.archived_closed_at IS NOT NULL AND wo.created_at > c.archived_closed_at;
```
**Actual output:** 1 row — case #51 ("Socket outlet scorched behind the sofa"): `case.archived_closed_at = 2026-01-18T04:31:28Z`, but its second work order has `created_at = 2026-01-20T00:31:28Z` (2 days *after* the case closed), and that work order has zero appointments. `timestamps_ordered_and_past` doesn't catch it because it only ever compares the case's created_at against the *first* work order, never any work order against `archived_closed_at`.

**Fix:** generate appointments for every work order that will be marked `COMPLETED` (or, simpler, only ever mark `COMPLETED` a work order that an appointment loop actually attaches something to), and add an explicit check comparing every work order's `created_at`/`updated_at` against its case's `archived_closed_at`, not just the first one.

---

### 2. HIGH — `backfill_category` can derive the wrong trade (constructed reproduction)

**Where:** `backend/app/backfill_category.py:96-118` (`plan()`), compared against `backend/app/domain/services.py:1050-1072` (`_pick_primary_trade`), which the rest of the app (Property History/Stats) already uses for the identical judgment call.

`backfill_category.py`'s own docstring states the intent plainly: "A case's category is meant to describe what the *issue* is, not every trade it eventually touched." `_pick_primary_trade`'s docstring makes the same point even more explicitly: *"a CANCELLED work order is excluded first — work that was called off is not what the case is 'about' any more."* `backfill_category.plan()`'s SQL query selects `case_id, trade, required_for_resolution, created_at` from `work_orders` — **it never selects or filters on `status`**, so a `CANCELLED` work order is exactly as eligible to be "the earliest required work order" as a `COMPLETED` one.

**Reproduction** (throwaway DB, one case, `category=NULL`):
- WO1: `trade=ELECTRICAL`, `required_for_resolution=True`, `status=CANCELLED` (electrician found no electrical fault), `created_at=2024-01-01`
- WO2: `trade=PLUMBING`, `required_for_resolution=True`, `status=COMPLETED` (real cause — a leak — found and fixed), `created_at=2024-01-02`

**Actual output:**
```
_pick_primary_trade => Trade.PLUMBING   (excludes the cancelled ELECTRICAL WO; picks PLUMBING)

backfill_category.plan():
  case #1: would set category=ELECTRICAL  reason='2 trades; took the earliest required work order'

FINAL repair_cases.category = Trade.ELECTRICAL
_pick_primary_trade says     = Trade.PLUMBING
MISMATCH CONFIRMED
```
`backfill_category` sets the case's permanent `category` to the trade of the work someone called off, not the trade that actually resolved the case — and disagrees with what Property Stats/History would show for that same case via `_pick_primary_trade`.

**Fix:** filter `rows` to `status != 'CANCELLED'` before applying the "earliest required, else earliest" rule (mirroring `_pick_primary_trade` exactly — ideally by calling it, so the two rules can't drift again).

**Scope check (passed):** the `already_set`/`cases` queries both filter `RepairCaseModel.archive_batch_id.is_(None)`, and empirically, running `backfill_category.plan()` against a DB holding only fully-categorized archival cases reported 0 changes/0 skipped — it never touches archival rows. The "no work orders → stays NULL" guarantee is correct by inspection (`if not rows: skipped += 1; continue` — the case is never added to `changes`, so its NULL category is never written to).

---

### 3. HIGH — `cost_totals_reconcile` doesn't reconcile against the other "quoted" source the app actually charts

**Where:** `backend/app/archive/importer.py:650-665` (`_cost_reconciliation_check`) vs. `backend/app/domain/services.py:1183-1220` (`load_property_stats`, the source of `GET /properties/{id}/stats`'s trade-breakdown donut and yearly-quoted-total chart).

The check sums `CostEntryModel.amount_pence` three ways (flat / by category / by year) and confirms they agree — they always will, since all three are the same rows summed differently. It never compares against `WorkOrderModel.quote_pence`, which is what a different screen for the same cases actually displays. Root cause in the generator: `_fill_resolved_case` (`dataset.py:668-712`) only ever creates `CostEntryModel` rows from `case.work_orders[0]` — a case's 2nd/3rd work order (`quote_pence` set, up to £3,500 for roofing) never gets a matching cost-ledger row at all.

**Query:**
```sql
SELECT c.case_number,
  (SELECT COALESCE(SUM(wo.quote_pence),0) FROM work_orders wo WHERE wo.case_id=c.id AND wo.status!='CANCELLED') AS wo_quote_sum,
  (SELECT COALESCE(SUM(ce.amount_pence),0) FROM cost_entries ce WHERE ce.case_id=c.id AND ce.kind='QUOTE') AS ledger_quote_sum
FROM repair_cases c;
```
**Actual output:** 29 of 60 cases (48%) differ. Whole-DB totals: `sum(work_orders.quote_pence, non-cancelled) = £94,136.62` vs `sum(cost_entries WHERE kind='QUOTE') = £65,281.96` — a **£28,854.66** gap that exists only as a work-order field, never as a ledger row. Example, case #3: `wo_quote_sum=119993` (£1,199.93) vs `ledger_quote_sum=35471` (£354.71) — 3.4x apart for the same case.

This is the archival-data instance of `docs/audit/06_analytics_metrics.md`'s CRITICAL #1 ("Two unreconciled sources for 'quoted' money"), confirmed here specifically, and specifically not caught by the archive's own validator despite the check's name.

**Fix:** either generate a `CostEntryModel` QUOTE row per work order (not just index 0), or have `_cost_reconciliation_check` also assert `sum(WorkOrderModel.quote_pence WHERE status!=CANCELLED) == sum(CostEntryModel WHERE kind='QUOTE')` per case and fail loudly until the generator (or, more durably, the app itself per docs/audit/06) is fixed.

---

### 4. MEDIUM (plausibility) — seasonality is flat; a real roofing portfolio would show storm-season clustering

**Where:** `backend/app/archive/dataset.py:487-495` (`_pick_date_in_year`) — draws a uniform random second-offset across the *entire* calendar year, with no month weighting anywhere.

**Query:**
```sql
SELECT substr(created_at,6,2) AS month, COUNT(*) FROM repair_cases WHERE category='ROOFING' GROUP BY month;
```
**Actual output:** 1,1,-,2,-,2,3,1,2,2,-,1 across Jan-Dec (15 roofing cases spread almost evenly over 9 of 12 months). A UK residential landlord's roofing call-outs (flashing failures, slipped tiles, gutters, storm damage — which is literally what half these titles describe) cluster Oct-Feb in reality; this dataset shows no seasonal signal at all, in any trade. A demo dashboard's "cases by month" chart will look conspicuously random rather than storm-driven.

**Fix:** weight `_pick_date_in_year` toward autumn/winter for `Trade.ROOFING` (and, more weakly, plumbing for boiler season) the way `_YEAR_WEIGHTS` already weights years.

---

## SUSPECTED / minor

### 5. LOW (plausibility) — cost amounts are uniform-random within range, not right-skewed like real invoices; 2021 is thin

`_cost_amount` (`dataset.py:550-554`) draws `rng.randint(lo, hi)` flat within each trade's range, times a year multiplier. Real quotes cluster toward the low end with a long tail (lognormal-ish), not uniform. Not implausible on its own (no duplicate amounts anywhere — 0 exact duplicates across all 60 QUOTE entries — so nothing looks *fake*), just a simplification. Separately, 2021 got only 1 case against an ~11% year-weight that, over 60 draws, should average ~6.7 (`_YEAR_WEIGHTS=[3,4,5,6,6,3]`, seed-dependent sampling variance) — cosmetically the "portfolio's first year" looks almost empty next to 2022's 7.

### 6. NIT — `recurrence_grouping`'s threshold is far below what the fixture actually produces

`importer.py:633-648` asserts `properties_with_recurrence >= 3`; the actual fixture produces 8/8 (every property). Not wrong, just a check so loose it would still pass if the deliberate `recurring_trade`/`recurring_count` per-property injection (`dataset.py:238-289`) were removed entirely and only organic randomness were left — it isn't currently testing the thing that makes the dataset's recurrence story convincing.

---

## Verified CORRECT (no bug found — reported since these were explicitly asked for)

### Plausibility table

| Metric | Archive's value | Real portfolio expectation | Verdict |
|---|---|---|---|
| Cases per property per year | 1-4 (mean ~1.8), 8 properties, 2021-2026 | 1-3 typical for small residential portfolio | PLAUSIBLE |
| Category mix (n=60) | ELECTRICAL 18, ROOFING 15, PLUMBING 14, OTHER 8, SCAFFOLDING 5 | Debatable exact ranking, but no category dominates absurdly | PLAUSIBLE |
| Cost per trade (QUOTE, £) | ROOFING mean 2,506 (min 958, max 3,815, n=15); ELECTRICAL mean 788 (n=18); PLUMBING mean 558 (n=14); SCAFFOLDING mean 737 (n=5); OTHER mean 253 (n=8); 0 exact duplicate amounts | Right-skewed/lognormal in reality | PARTIALLY PLAUSIBLE — varied, no duplicates, but statistically flat not skewed (see #5) |
| Resolution time, RESOLVED cases (days) | n=56, min 3.6, p25 14.6, median 19.1, p75 22.8, max 34.7 | Days to a few weeks is typical for non-emergency UK landlord repairs | PLAUSIBLE |
| Seasonality (roofing/month) | Flat, 1-3/month across 9-12 months, no clustering | Real roofing call-outs cluster Oct-Feb | **NOT PLAUSIBLE** (finding #4) |
| Year distribution (n=60) | 2021:1, 2022:7, 2023:10, 2024:17, 2025:15, 2026:10 | Gradual growth is plausible; 2021 undersampled vs. its weight | MOSTLY PLAUSIBLE (finding #5) |
| Work orders `COMPLETED` with a real attended visit | 65/87 (75%) — 22/87 (25%) `COMPLETED` with **zero** appointment | Should be ~100% for a status literally called `COMPLETED` | **NOT PLAUSIBLE** (finding #1) |
| "Quoted" total agreement across screens, same case | 31/60 agree, 29/60 (48%) disagree, up to 3.4x | Should be 100% — same case, same money | **NOT PLAUSIBLE** (finding #3) |

### Independent re-derivation of the archive's own checks (raw SQL, fresh import, batch `b901bea4-2fbf-55b7-a188-84b51e568cfc`, 60 cases / 600 rows)

All of the following were written from scratch, not copied from `importer.py`, against every relevant timestamp/status column (not just the subset the archive's own checks touch):

- **Every timestamp ordered and in the past**: checked `created_at`/`updated_at`/`archived_closed_at` on `repair_cases`, `work_orders` (+ `updated_at >= created_at`), `appointments` (+ `end_at > start_at`), `cost_entries`, `notes`, `messages` (+ `read_at >= created_at`), `documents`, `action_records` — 0 violations except the one cross-table ordering bug already reported as finding #1 (a work order created after its case's `archived_closed_at`, which none of these single-table checks would surface).
- **No negative durations**: 0 appointments with `end_at <= start_at`.
- **No open work**: case status distribution `{CANCELLED: 4, RESOLVED: 56}`; work order status `{CANCELLED: 4, COMPLETED: 83}`; appointment status `{FINISHED: 75}`; action record state `{SUCCEEDED: 75}` — all terminal, confirming the check's literal claim (its weakness is what "COMPLETED" implies, not the status value itself — finding #1).
- **No jobs**: `SELECT COUNT(*) FROM jobs` → 0 (checked the whole table, not just scoped to batch case ids).
- **No future appointments**: 0.
- **No unread messages**: `read_at IS NULL` → 0; `delivery_state` is `INTERNAL_NOTE` for all 42 (no message ever claims `SENT`/`DELIVERED`).
- **Costs reconcile by category and year against the flat list**: flat=`£115,026.95`, by-category sum=`£115,026.95`, by-year sum=`£115,026.95` — reconcile exactly, but only within `CostEntryModel` itself (see finding #3 for what this doesn't catch).
- **Referential integrity**: `PRAGMA foreign_key_check` → 0 dangling rows.

### `--remove` completeness (task 4)

Imported into a fresh DB, planted 4 non-archival control rows (property/tenant/contractor/case) plus a control note, message and pending job on that case, then removed:

- All 8 tables with an `archive_batch_id` column (`properties`, `tenants`, `contractors`, `repair_cases`, `cost_entries`, `notes`, `documents`, `messages`) → 0 batch-tagged rows remaining.
- All 4 traversal-only tables (`repair_issues`, `work_orders`, `appointments`, `action_records`) → 0 rows (no non-archival rows ever existed there to protect, but confirmed none leaked in).
- `archive_batches` → 0 rows.
- `PRAGMA foreign_key_check` → 0 orphans.
- All 12 document files (`documents_written` from the import) → confirmed gone from disk (`Path.exists()` false for every one).
- Every control row (property, tenant, contractor, case + its note/message/job) → present and unchanged after removal.
- Re-importing immediately after → clean, same counts as the first import, `archive_batches` back to 1 row, total case count = 61 (60 archival + 1 control), no duplication.

### Archival containment (task 3) — proved live over HTTP, on a DB holding both kinds of row

Ran `seed()` → `archive --apply` → created one real operational case via `POST /api/v1/cases` through an in-process `httpx.ASGITransport` client (no server started, no lifespan/worker task):

| Surface | Result |
|---|---|
| `GET /api/v1/cases` (default) | 1 item (the new operational case only); `include_archived=true` correctly surfaces 19 archival items — confirms the filter is real, not accidentally-empty |
| `GET /api/v1/metrics/dashboard` | `total=1` |
| `GET /api/v1/overview` | `status_counts.total=1`, `property_count=4` (the 4 seeded operational properties; the 8 archival properties excluded) |
| `GET /api/v1/notifications` | 0 items (archival `ActionRecord`s are all `SUCCEEDED`, never `AWAITING_APPROVAL`; archival cases write no `CaseEvent` rows, so no `CASE_ESCALATED`) |
| Job queue (`SELECT * FROM jobs`) | 1 row, and it belongs to the new operational case (`case_archival=False`) — the archive import itself writes zero job rows, and nothing in the write paths (`cases.py`, `messaging.py`, `costs.py`, `documents.py`, `notes.py`, `contractors.py`) lets a mutation reach an archival case in the first place (all of them check `archive_batch_id is not None` and reject before anything could `enqueue_job`) |
| Agent wake path | Structurally can't fire for an archival case: `worker.claim_job` only ever reads the `jobs` table, which the above shows never gets an archival-case row |

**Routes that intentionally include archival rows, checked for honest labeling (not leaks):** `GET /api/v1/search` includes archival cases/properties with `is_archived=true` on every such row (by design — global search should find everything). `GET /api/v1/reports/summary` and `/reports/export.csv` default `include_archived=true` and label every row `record_source: "archival-sample"` vs `"operational"`, and report `archived_case_count` at the top level. Neither is on the audit's named-surface list, and both are transparent about what they include — not counted as leaks.

### `app.seed` idempotency (task 5)

Ran `seed()` three times against one throwaway DB: run 1 added 4 properties/4 tenants/6 contractors, runs 2 and 3 added 0/0/0. A full-row snapshot (`id, address_line, postcode, build_year, landlord_reference` / `id, property_id, display_name, phone_e164` / `id, display_name, approval_status`) was byte-identical across all three runs. Layered `archive --apply` on top afterward: 0 duplicate `case_number`s, 0 overlap between seed's and the archive's property ids (different `uuid5` namespaces — `repairflow.demo` vs `repairflow.archive` — as documented).

### `legacy_demo_purge` on a copy of the real dev database (task 7)

Copied `backend/data/repairflow.db` (never opened for writing) into the scratchpad and ran `create_all()` against the copy only (the real file predates 18 columns — a pre-existing dev-DB staleness already flagged in `docs/audit/06_analytics_metrics.md`, self-healed by `_add_missing_columns`, not a purge bug). Before purge: 14 cases; cases #1-5 have status `ACTIVE`, and 3 of them (`#3`, `#4`, `#5`) carry `provenance='LIVE'` `communications` rows with real `provider_conversation_id`s (`conv_5101m2xc9gwwf0gtscpg75bvb4m4`, `conv_1501m2xsp1ygfzq8cm3aa3fgnrjr`, plus one `REQUESTED` with none yet) and non-empty transcripts.

`purge(apply=True)`:
```
cases_found: 9, repair_cases: 9, work_orders: 10, appointments: 3, action_records: 4,
repair_issues: 9, dependencies: 1, contractor_reports: 1, messages: 5, (all else: 0)
```
- All 9 scripted ids (recomputed `uuid5(repairflow.demo, "<label>:case")`) matched cases #6-14 exactly (`hist:cathedral:2023:plumbing` → #6, … `live:redcliffe:scaffold` → #14) and were the only ones removed. Confirmed absent afterward.
- `PRAGMA foreign_key_check` → 0 orphans.
- Cases #1-5: present, unchanged (`case_number`/`title`/`status` identical before/after).
- The 3 `LIVE` communications: identical row-for-row before/after (`id`, `case_id`, `provenance`, `state`, `provider_conversation_id`, transcript length) — **untouched**.
- Second `apply` → `cases_found: 0`, a clean no-op.

(Side observation, out of this audit's scope: the real dev DB copy has 5,618 rows in `jobs` — worth a separate look at whether completed/failed job rows ever get pruned, but not part of archive/seed/backfill/purge.)

### Full interaction sequence (task 8)

`seed()` → `archive --apply` (60 cases, 600 rows, 12 docs) → `backfill_category.plan()`/`apply_changes()` (0 changes — nothing needed it yet, since backfill ran before the operational case existed and every archival case already carries a category) → `POST /api/v1/cases` via in-process ASGI client (201, case created, 1 `COORDINATE` job enqueued) → containment checks (above, all passed) → `archive --remove` (60/60/6/8/8/75/75/87/60/55/42/12/1 rows removed across the 13 tables, 12 document files deleted from disk). After removal: 1 case remains (the operational one, `status=ACTIVE`), 4 properties remain, 0 archive batches. No crashes, no assertion failures, no leftover files.
