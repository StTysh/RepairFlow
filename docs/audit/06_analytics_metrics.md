# Analytics/Metrics Audit — are the numbers right?

Scope: `backend/app/analytics.py`, `backend/app/api/insights.py`, `reports.py`, `overview.py`, `metrics.py`, and `backend/app/api/cases.py`'s `/properties/{id}/history` and `/stats` (implemented in `backend/app/domain/services.py:load_property_history`/`load_property_stats`). Read-only; no server started. All numbers below were computed by running the actual production code (`app.analytics`, `app.domain.services`) against an isolated in-memory SQLite fixture built with deliberately awkward pence amounts, or, where noted, against a throwaway copy of `backend/data/repairflow.db` in the scratchpad — the real file was never opened for writing.

**Context note (not a scored finding):** the on-disk `backend/data/repairflow.db` predates several current models (no `cost_entries`/`archive_batches`/`notes` tables, no `repair_cases.category`/`archive_batch_id`). `app/db.py:70-127` (`_add_missing_columns`) self-heals this on next app boot — verified by running `create_all()` against a copy, which correctly added 18 columns and created the 3 missing tables. This is ordinary local dev staleness (`data/` is gitignored), not a code defect, so it isn't scored, but it did mean the real DB had no usable cost/archival rows to mine — all worked examples below use the fixture instead, which is precise and reconciled against the real formulas.

## Severity counts
CRITICAL: 2 · HIGH: 2 · MEDIUM: 1 · LOW: 1 · NIT: 2

## Verdict
The numbers **do not currently reconcile** across screens for anything money-shaped or resolution-time-shaped: Property History/Stats and Insights/Reports/CSV compute "quoted" spend from two entirely different tables that are never kept in sync (Finding 1), and the default (`include_archived=True`) resolution-time distribution blends genuinely-fixed cases with archival cases that were only ever cancelled (Finding 3) — both are default-path, reachable-today defects, not rare edge cases. Within a single family (Insights ↔ Reports ↔ CSV, all backed by `case_detail_rows`), the numbers do reconcile exactly, in pence, including negative adjustments — that part is solid. Largest-remainder percentages and the zero-baseline period comparison are both correctly implemented with no counter-example found.

---

## Definitions table

| Metric | Formula as implemented | Source table(s) | Screens |
|---|---|---|---|
| Property "quoted" total/by-trade/by-year | `sum(WorkOrderModel.quote_pence)` where `status != CANCELLED`, no archival filter | `work_orders` (+ `repair_cases` for year) | Property History (`quoted_by_trade` donut, `quoted_by_year` bars, per-row `quoted_pence` column, client-side filtered total) |
| Insights/Reports "quoted" spend | `sum(CostEntryModel.amount_pence)` where `kind=QUOTE` | `cost_entries` | Insights (`spend_by_year`), Reports summary (`spend.quoted_pence`), CSV export |
| Insights/Reports "actual" spend | `sum(CostEntryModel.amount_pence)` where `kind IN (INVOICE, ADJUSTMENT)` | `cost_entries` | Insights, Reports summary (`spend.actual_pence`), CSV export |
| Row-level `quoted_pence`/`invoiced_pence` | Per-case `CostEntryModel` sums by kind | `cost_entries` | Insights drill-down (`/insights/cases`), Reports detail rows, CSV |
| `avg_resolution_hours` (dashboard) | mean(latest `CASE_RESOLVED` event `occurred_at` − `created_at`) for cases resolved in the last 30 days, operational only, no fallback | `case_events` + `repair_cases` | Overview/Dashboard header, also rendered on the Maintenance screen (`useDashboardMetrics`) |
| `resolution.average_hours`/`median_hours`/buckets (Insights/Reports) | mean/median of `resolution_hours()` over cases matched by filter window (RESOLVED real cases, any-status archival cases with `archived_closed_at`), falls back to `updated_at` when no terminal event | `repair_cases` + `case_events` | Insights, Reports summary, CSV, and the **same Maintenance screen** as the dashboard figure above |
| `category_breakdown` | `count(*)` grouped by `RepairCaseModel.category`, largest-remainder integer % | `repair_cases` | Insights, Reports summary |
| `case_volume_by_month` | `count(*)` grouped by `(created_at.year, created_at.month)`, UTC, no timezone conversion | `repair_cases` | Insights chart, feeds `case_volume_comparison` |
| Portfolio `recurring_issues` | `(property_id, category)` groups with count ≥ 2 | `repair_cases` | Insights, Reports summary |
| Property `recurring_issues` | `(primary_trade)` groups with count ≥ 2, from work orders' `_pick_primary_trade` | `repair_cases` + `work_orders` | Property History/Stats |
| Property `total_count`/`active_count` | `count(*)`/`count(status==ACTIVE)` over every case at the property, **no archival filter, no toggle** | `repair_cases` | Property History/Stats header |
| `period_comparison`/`case_volume_comparison` | % change current vs. immediately preceding window of equal length; 0-baseline special-cased | derived | Insights |
| `operational_status_counts`/`DashboardMetricsResponse` counts | `count(*)` grouped by status, `archive_batch_id IS NULL` | `repair_cases` | Overview, Dashboard |

---

## CONFIRMED

### 1. CRITICAL — Two unreconciled sources for "quoted" money: `WorkOrderModel.quote_pence` vs `CostEntryModel(kind=QUOTE)`
`backend/app/domain/services.py:1183-1250` (`load_property_stats`) and `services.py:1111-1180` (`load_property_history`) sum `WorkOrderModel.quote_pence`. `backend/app/analytics.py:472-523` (`spend_by_year`) and `analytics.py:791-874` (`case_detail_rows`, `quoted_pence`) sum `CostEntryModel` rows of `kind=QUOTE`. These are genuinely different concepts computed from different tables that nothing keeps in sync, shown on different screens for the same case/property.

**Root cause, side A (operational cases):** `WorkOrderModel.quote_pence` is set automatically by policy the moment a work order is created (`app/domain/policy.py:23-24`, `FICTIONAL_QUOTES`). `CostEntryModel` rows only ever come from two places: a human manually calling `POST /cases/{id}/costs` (`app/api/costs.py:165-185`) or the archive importer (`app/archive/importer.py:310-320`). **No code path ever creates a `CostEntryModel` from a real work order's `quote_pence`.** So for any operational case where an operator hasn't opened the Costs tab, property quoted totals are non-zero and Insights/Reports quoted totals are exactly zero.

Worked example (fixture Case A: RESOLVED, ROOFING, two work orders, no cost entries ever logged):
- Property Stats/History: **40,000p** (`10,000 + 30,000`, `wo_a1.quote_pence + wo_a2.quote_pence`)
- Insights/Reports (`spend_by_year`, same case): **0p**

**Root cause, side B (archival sample cases — even historical data disagrees):** `app/archive/dataset.py:675-685` (`_fill_resolved_case`) writes a single `CostEntryModel(kind=QUOTE)` sized to `case.work_orders[0].quote_pence` only — `primary_quote = case.work_orders[0].quote_pence or 0` — but a case can have 1-3 work orders (weights `[55, 35, 10]`, line 597), each with its own `quote_pence`. So ~45% of generated archival cases have a work-order-summed quoted total that exceeds the one `CostEntryModel` QUOTE row backing it.

Worked example (fixture Case E: archival, ROOFING, 3 work orders — 12,345p / 6,789p / 4,444p-CANCELLED):
- Property Stats: **19,134p** (`12,345 + 6,789`, cancelled work order correctly excluded on both sides)
- Insights/Reports (`spend_by_year`): **12,345p** (only `work_orders[0]`'s QUOTE row exists)

**Recommendation:** `CostEntryModel` (integer pence, signed adjustments, explicit `kind`) is the more honest/auditable model and is already what `docs/17`-style spend reporting is built on — it should win. Smallest correct fix: stop reading `WorkOrderModel.quote_pence` for money display entirely; have `load_property_stats`/`load_property_history` read from `CostEntryModel` the same way `analytics.spend_by_year`/`case_detail_rows` do (there is already a shared, tested code path — reuse it rather than adding a third). Migration: backfill one `CostEntryModel(kind=QUOTE)` row per priced, non-cancelled `WorkOrderModel` (operational and archival) so historical totals don't silently drop when the read path switches, then keep the archive generator's cost-writing loop symmetric with its work-order loop (write a QUOTE row per work order, not just `work_orders[0]`).

### 2. HIGH — Property `/history` and `/stats` include archival sample data unconditionally, with no `include_archived` parameter and no disclosure field
`backend/app/domain/services.py:1183-1206` (`load_property_stats`) and `services.py:1111-1121` (`load_property_history`): both query `select(RepairCaseModel).where(RepairCaseModel.property_id == property_id)` with **no `archive_batch_id` filter at all**, and `PropertyStatsResponse`/`PropertyHistoryItem`/`PropertyHistoryResponse` (`app/schemas.py:1303-1372`) carry no `includes_archived_history`/`archived_case_count`/`is_archived` field of any kind — the exact opposite of `analytics.py`'s own documented house rule (`analytics.py:11-30`): "every payload that used [archival rows] must say so."

**Reachability, checked precisely (this is what keeps it at HIGH rather than CRITICAL):** the archive importer (`app/archive/importer.py:169-177`, `dataset.property_id()` at `app/archive/dataset.py:215-219`) only ever attaches an archival `RepairCaseModel` to a `PropertyModel` created in the *same* import batch, which itself always carries `archive_batch_id=batch_id` (`importer.py:171-177`). So today, an archival case can never attach to an operational property (`archive_batch_id IS NULL`) — a real property's `/history`/`/stats` page cannot currently be contaminated by fake cases, because the underlying data never mixes them. The bug is real but currently only bites when a user deliberately views an *archival* property: `GET /properties` defaults to `include_archived=False` (`app/api/properties.py:256-261`) but has a toggle, and the properties **list** page does render an archival badge (`frontend-fixi/src/routes/properties.index.tsx:208`, `p.is_archived`). Once a user drills into such a property, though, the History route (`frontend-fixi/src/routes/properties.$propertyId.history.tsx`) never fetches or renders `PropertyModel.is_archived` at all — it calls only `usePropertyHistory`/`usePropertyStats`, neither of which carries the flag — so every number on that page reads as if it were live operator data with zero indication it is 100% synthetic sample history.

Verified mechanically (fixture, not dependent on the importer invariant): seeded 1 real ACTIVE case + 2 archival RESOLVED cases at one property → `load_property_stats(...).total_count == 3`, `active_count == 1`, and `load_property_history` returns all 3 rows with no `is_archived` field on any of them (contrast `analytics.CaseDetailRow.is_archived`, which exists specifically so Insights/Reports/CSV can label this honestly). The function itself enforces nothing — the separation holds only because of how the importer happens to be written today, which is a latent-risk pattern, not a guarantee.

**Smallest correct fix:** add `include_archived: bool = True` to both functions' signatures (mirroring every function in `analytics.py`), filter `archive_batch_id IS NULL` when `False`, add `is_archived` to `PropertyHistoryItem` plus `archived_case_count`/`includes_archived_history` to `PropertyStatsResponse`/`PropertyHistoryResponse`, and have the History route fetch/display `PropertyModel.is_archived` (already returned by `GET /properties/{id}`) so an archival property's page is honestly labelled.

### 3. CRITICAL — `resolution_time_distribution`'s archival branch has no status filter: CANCELLED archival cases are blended into real cases' "resolution time" by default
`backend/app/analytics.py:693-697`:
```python
where_clause = RepairCaseModel.status == CaseStatus.RESOLVED
if include_archived:
    where_clause = where_clause | (
        (RepairCaseModel.archive_batch_id.is_not(None)) & (RepairCaseModel.archived_closed_at.is_not(None))
    )
```
For real cases this correctly requires `status == RESOLVED`. For archival cases it requires only `archive_batch_id IS NOT NULL AND archived_closed_at IS NOT NULL` — **no status check** — so an archival case with `status == CANCELLED` (the sample generator produces these at a fixed 10% rate: `app/archive/dataset.py:870`, `weights=[90, 10]`) is included too, directly contradicting `case_is_resolved`'s own documented contract three functions above it in the same file (`analytics.py:87-92`: "CANCELLED... is never counted as resolved"). The identical bug is in `case_detail_rows`'s `closed_and_resolved = is_archived or case_is_resolved(case.status)` (`analytics.py:847`), so the same contamination reaches the drill-down table, Reports rows, and the CSV — self-consistent across those three, but all equally wrong.

Worked example (fixture: 1 archival RESOLVED case taking 48h to fix, 1 archival CANCELLED case taking 2h to give up):
- Correct average (RESOLVED only): **48.0h**, sample_count=1
- Actual (`resolution_time_distribution`, `include_archived=True`, the default): **25.0h**, sample_count=2 — a cancelled case that was never fixed is blended in as if it were a fast resolution, understating the true average by 48% in this example.

This is CRITICAL rather than HIGH because, unlike Finding 2, there is no structural barrier keeping it from firing on the default, most-viewed path: `include_archived=True` is the default on both `GET /insights` and `GET /reports/summary`, real RESOLVED cases and archival cases of any status are combined into **one** average/median/bucket set (not shown side by side, not separable after the fact), and the archive generator produces CANCELLED cases at a fixed, non-trivial 10% rate (`dataset.py:870`) — so any portfolio with the sample history loaded and `include_archived` left at its default will show a contaminated resolution-time KPI out of the box.

**Smallest correct fix:** add `& (RepairCaseModel.status == CaseStatus.RESOLVED)` to the archival half of `where_clause` (`analytics.py:695-697`), and change `case_detail_rows`'s `closed_and_resolved` (`analytics.py:847`) to `(is_archived and case.status == CaseStatus.RESOLVED) or case_is_resolved(case.status)`.

### 4. HIGH — `_terminal_event_at_by_case` only recognizes `CASE_RESOLVED`/`CASE_CANCELLED`; a "late reopen" (RESOLVED → ESCALATED → resumed) reports a stale or fabricated resolution time
`backend/app/analytics.py:403-418` (`_terminal_event_at_by_case`) looks only for `CASE_RESOLVED`/`CASE_CANCELLED` event types. `backend/app/analytics.py:436-462` (`resolution_hours`) then does `end = case.terminal_event_at or case.updated_at` — silently substituting `updated_at` ("whenever the row was last touched") when no such event exists, with no distinction downstream from a real event-derived duration. `skipped_count` (`analytics.py:678`, incremented at line 718) only increments on a *negative* duration; it never fires for this fallback, so a fabricated-looking duration is indistinguishable from a real one.

This is not a hypothetical DB-integrity edge case — it is reachable today through an existing, documented feature. `case_is_open`'s own docstring (`analytics.py:70-72`) notes "transitions.py allows RESOLVED -> ESCALATED (a late reopen)". Tracing that path: `escalate_to_human` (`services.py:967-974`) stashes `case.resume_status = case.status` (which is `RESOLVED` for a late reopen) before flipping to `ESCALATED`, writing a `CASE_ESCALATED` event. `POST /cases/{id}/resume` (`app/api/cases.py:413-439`) later sets `case.status = target` back to `RESOLVED` (line 431) but writes only a `CASE_RESUMED` event (lines 434-436) — **never a new `CASE_RESOLVED`**. `_terminal_event_at_by_case` has no `CASE_RESUMED` branch, so it either falls back to a *stale* pre-escalation `CASE_RESOLVED` timestamp (if one exists) or, if none does, to `updated_at`.

Verified mechanically (fixture): a case created 100 days ago, resolved after 48h (`CASE_RESOLVED` at `created_at+48h`), escalated 90 days later, then resumed back to RESOLVED 1 day before "now" (99 days after the original resolution):
- Reported (`case_detail_rows`/`resolution_time_distribution`): `closed_at` = the *original* resolution timestamp, `resolution_hours = 48.0`, counted in `sample_count`, not in `skipped_count`.
- True elapsed time to the case's actual current resolved state: **2,376.0h** (99 days).
- A 49x understatement, reported with no caveat, on a case whose event log literally has two later events (`CASE_ESCALATED`, `CASE_RESUMED`) after the timestamp being shown as "closed".

Negative-duration exclusion itself is correctly implemented — verified separately (terminal event 1h before `created_at`) returns `None` and is excluded from `sample_count`/`average_hours`/buckets, not clamped to 0. The plain "resolved, never had any event at all" fallback (no escalation involved) is also mechanically real but, absent the late-reopen path, has no other known trigger under the current write paths (`services.py:955-963` is the only place a case reaches `RESOLVED` via its normal first resolution, and it writes `CASE_RESOLVED` atomically in the same transaction).

**Smallest correct fix:** either (a) have `resume_case` write a fresh `CASE_RESOLVED` (or a new terminal-equivalent type `_terminal_event_at_by_case` also recognizes) whenever `target == CaseStatus.RESOLVED`, so the event log's terminal timestamp always matches the case's actual current closure, or (b) have `resolution_hours`/`ResolutionInputs` return a tri-state (e.g. `is_estimated: bool`) instead of silently trusting a stale/absent terminal event, and count both the stale-event and no-event cases in a new `estimated_count` distinct from `skipped_count` so the UI can caveat them.

### 5. MEDIUM — Date-window and month/year bucketing use naive UTC, not Europe/London; wrong (but self-consistently wrong) near BST boundaries
`backend/app/api/insights.py:26-41` and `backend/app/api/reports.py:33-45` (two independent, currently-identical copies of `_window()`) combine a bare `date` query param with UTC midnight: `datetime.combine(date_to, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)`. `analytics.py:744-762` (`case_volume_by_month`) then buckets by `created_at.year`/`.month` on the raw UTC-aware datetime, with no timezone conversion anywhere.

Verified: a case with `created_at = 2026-03-31T23:30:00Z` — which is `2026-04-01T00:30` in Europe/London once BST (UTC+1) is in effect — is bucketed into **March**, not April, everywhere: `case_volume_by_month`'s chart, and any `date_from`/`date_to` window a London user picks expecting local calendar days. The window itself is also off by up to 1 hour at both ends during BST (both boundaries computed as if UTC == local time), so a `date_from=2026-03-01`/`date_to=2026-03-31` request leaks the first local hour of April 1st in and excludes the first local hour of March 1st.

This **is** internally consistent — Insights, Reports and the CSV all call the exact same `_window()`/`case_volume_by_month`, so they never disagree with each other — but all three are wrong relative to the stated Europe/London user base for roughly 7 months of the year (late March–late October).

**Smallest correct fix:** parse `date_from`/`date_to` as Europe/London calendar dates and convert to UTC at the boundary (e.g. via `zoneinfo.ZoneInfo("Europe/London")`) instead of assuming UTC == local; bucket `case_volume_by_month` on the London-local month, not the UTC month. De-duplicate the two copies of `_window()` while at it (see Finding 7).

### 6. LOW — A second, independently-computed "average resolution hours" disagrees with Insights/Reports', and both render on the same screen
`backend/app/domain/services.py:1327-1358` (`average_resolution_hours`, feeding `DashboardMetricsResponse.avg_resolution_hours` via `metrics.py:64,79`) computes mean hours over cases resolved in a **fixed 30-day rolling window**, operational-only, strictly from `CASE_RESOLVED` events with **no `updated_at` fallback** (a case with no matching event is simply absent from `recent`, never substituted). This is a third, differently-scoped implementation of "resolution time" alongside `analytics.resolution_hours`/`resolution_time_distribution` (Finding 4's subject) — different window (30 days vs. the ~24-month/custom Insights window), different archival policy (never vs. default-include), and different fallback behavior (exclude vs. silently substitute `updated_at`). The frontend renders both on the Maintenance route: `metrics.data.avg_resolution_hours` from `/metrics/dashboard` (`frontend-fixi/src/routes/maintenance.index.tsx:176-179`) alongside the Reports summary's `resolution.average_hours` from the same page's `/reports/summary` call — two "average resolution time" numbers, computed two different ways, next to each other, that will not match except by coincidence.

**Smallest correct fix:** not necessarily a bug (a 30-day rolling KPI and an all-time/filtered distribution are legitimately different questions), but the two should be visually distinguished on the page (different labels: "last 30 days" vs. "in selected range") rather than both reading as "avg resolution hours" with no scope indicator.

### 7. NIT — `_window()` is duplicated verbatim in `insights.py` and `reports.py`
`backend/app/api/insights.py:26-41` and `backend/app/api/reports.py:33-45` are byte-for-byte identical functions. Currently harmless (Finding 5 affects both equally because they're identical), but nothing enforces that they stay identical — a future edit to one and not the other would silently make Insights and Reports/CSV disagree on date-window semantics, defeating the module's own stated purpose (`analytics.py:1-9`: "a metric must never be computed inline in a router"). **Fix:** move `_window()` into `analytics.py` alongside the functions it feeds.

### 8. NIT — Recurring-issue groups don't label their own archival/operational split
`backend/app/analytics.py:602-641` (`recurring_issues`) correctly groups `(property_id, category)` across archival and operational cases together and returns the exact contributing `case_ids` — verified: seeding one operational ROOFING case + one archival ROOFING case at the same property produced `count=2` with `case_ids` containing exactly those two, and the operational-only PLUMBING pair (2 real cases) also matched exactly. `InsightsResponse` does carry a top-level `archived_case_count`, but `RecurringIssueResponse` itself has no per-group archival count, so "ROOFING recurred twice at this property" reads as two real incidents unless the caller separately cross-references `/insights/cases` for each `case_id`'s `is_archived`. Cosmetic; not scored as a correctness bug since the underlying `case_ids` are exact and joinable.

---

## Also verified CORRECT (no counter-example found)

- **Largest-remainder percentages** (`analytics.py:526-545`): tested 3-equal-thirds (`[34,33,33]`), 51.5/48.5 (`[52,48]`), a single 100% group (`[100]`), seven equal groups (`[15,15,14,14,14,14,14]`), two variants with a 0%-count group present (`[50,50,0]`, `[34,33,33,0]`), and an all-zero-total input (`[0,0,0]`) — every case summed to exactly 100 (or exactly 0 for the all-zero case). No overshoot/undershoot found.
- **Reconciliation within the `CostEntryModel` family** (item 2 of the brief): using the odd-pence fixture (12,345p quote / 11,111p invoice / -333p adjustment across a multi-work-order archival case), `spend_by_year`'s totals, `case_detail_rows`' summed `quoted_pence`/`invoiced_pence`, and a CSV built the same way `reports.py:201-240` builds it all matched **exactly**, in pence, including the negative adjustment. No float ever touches the sums.
- **`period_comparison` zero-baseline** (`analytics.py:890-907`): verified `(0,0)→0.0%/is_new=False`, `(5,0)→None/is_new=True`, `(0,5)→-100.0%/is_new=False` — matches the documented contract exactly.
- **Operational scope in `analytics.py`'s own functions** (`portfolio_counts`, `operational_status_counts`, `needs_attention`, `recent_activity`, `open_age_buckets`): every one explicitly filters `archive_batch_id IS NULL`; no accidental archival leakage found on the Overview/Dashboard side. The leakage found (Finding 2) is specific to `cases.py`'s property stats/history, which live in `services.py` and were not written to `analytics.py`'s documented archival convention.
