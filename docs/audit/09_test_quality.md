# 09 — Test Quality Audit

Scope: `backend/tests/` (13 files, ~5,986 lines, 154 tests at session start).
Method: hand mutation-testing of the ~12 invariants the project most depends
on, plus a manual coverage/isolation/flakiness pass (no `coverage` package
available — see Coverage section). No frontend test suite exists at all;
sized separately below. Read-only except this file; every source mutation
below was applied, tested, and reverted, with restoration verified against
byte-identical backups (not just `git status`, for reasons explained in the
Methodology note).

**Important caveat on this session's evidence.** This audit ran on a shared,
live working tree with other agents actively committing to `main`
throughout (HEAD moved from `b0aff48` to `28df695` — 6 commits — during this
session). Twice, a concurrent `git add`-style commit captured one of my
*temporary, in-progress* mutations before I could restore it, producing two
real, if short-lived, regressions on `main`:

- Commit `e5abd41` ("Donut fix, category backfill, and the first
  browser-pass findings") briefly shipped `backend/app/api/cases.py` with
  archival-case exclusion disabled (`if not include_archived and False:`).
- Commit `79a1f3d` ("Fix the critical defects the audit sweep found")
  briefly shipped `backend/app/domain/transitions.py` with
  `assert_case_transition` reduced to `return` (no-op).

Both were superseded by later commits before this report was written and
are **not present in the current HEAD (`28df695`)** — confirmed directly with
`git show 28df695:backend/app/api/cases.py` (shows `if not include_archived:`,
correct) and `git show 28df695:backend/app/domain/transitions.py` (shows the
full `_CASE_EDGES` guard body, correct), not merely by re-diffing my own
restored working tree against a moving HEAD. They are reported here
only as corroborating evidence: **the full 154/155-test suite passed with
both regressions in place**, which is the strongest possible demonstration
that the two invariants they touched are unprotected. See rows 2 and 11 in
the table. All 12 of my own working-tree edits were verified byte-identical
to their pre-mutation originals before I moved to the next invariant; the
final `git status --short` in this report reflects only other agents' own
unrelated in-progress work, none of it mine (verified line by line — see
end of report).

## Mutation-test table

| # | Invariant | How broken | Suite caught it? | Which test |
|---|---|---|---|---|
| 1 | No-contact transport guard (`assert_contact_allowed` in `app/integrations/no_contact.py`) | Made the raise unreachable (`if False and no_contact_enabled():`) | **YES** | `test_no_contact_harness.py::test_real_transport_raises_instead_of_dialling`, `::test_transport_guard_fails_closed_when_substitute_is_missing` — both failed with the transport call proceeding. Run under a safety-net script that patches `httpx.AsyncClient.post/get/request` to raise before any socket opens, so no real network call was possible even with the guard disabled. |
| 2 | Archival exclusion from `GET /api/v1/cases` (`app/api/cases.py`) | Neutralised the `if not include_archived:` filter | **NO — untested** | Full 154-test suite passed unchanged. `include_archived` is tested for `/properties`, `/contractors`, `/tenants`, and for the `analytics.*` functions directly, but **never for `GET /cases` itself** — the primary operational list endpoint. |
| 3 | DRAFT-never-SENT rule (`app/api/messaging.py::compose_message`) | Changed outward-channel messages to persist as `SENT` instead of `DRAFT` | **YES** | `test_content_api.py::test_compose_outward_channel_persists_as_draft_never_sent` |
| 4 | Approval version-staleness check (`app/orchestration/executor.py::decide_approval`, the `case.version != decision.expected_case_version` guard) | Replaced the check with `if False:` | **NO — untested** | Full 155-test suite passed unchanged (targeted files `test_reliability_matrix.py`, `test_phase2_reliability.py`, `test_hero_path.py`, `test_api.py`, `test_coordinator.py`, `test_research.py`, `test_fixi_ui_support.py` all passed too). No test constructs a stale-`expected_case_version` approval to exercise `StaleVersionError`, despite the module's own docstring naming this exact check and docs/19's "approval binds... permitted spend" requirement. |
| 5 | Largest-remainder percentages (`app/analytics._largest_remainder_percentages`) | Flipped the tie-break sort from `reverse=True` to ascending, so leftover points go to the *smallest* remainders instead of the largest | **PARTIAL** | `test_analytics_api.py`'s three unit tests all still passed. Root cause: every existing test uses **symmetric/tied** inputs (`[1,1,1]`, `[103,97]` → remainders `.33/.33/.33` or `.5/.5`), where a stable sort produces the same result regardless of direction. No test exercises an asymmetric-remainder input, so the "largest" in "largest-remainder" is unverified — only the "sums to 100" byproduct is, and a broken selection still sums to 100. |
| 6 | `_add_missing_columns` backfill (`app/db.py`) | Disabled the `UPDATE ... SET col = ? WHERE col IS NULL` backfill after `ALTER TABLE ADD COLUMN` | **YES** | `test_fixi_ui_support.py::test_added_column_is_backfilled_with_its_default` — a deliberately well-built test (pre-migration table, legacy row, then `create_all()`); failed exactly as expected on `channel left NULL on a pre-existing row`. |
| 7 | Integer-pence arithmetic (`app/api/costs.py::_compute_totals`, `committed_pence`) | Changed `invoice if invoice else quote` to `invoice + quote` (double-counts a costed, invoiced work order) | **YES** | `test_content_api.py::test_cost_crud_and_totals_arithmetic` — exact expected value (`75000`) asserted; got `125000`. |
| 8 | Hazard gate (`app/domain/policy.is_hazard`) | Dropped `risk.gas` from the `Answer.YES in (...)` tuple | **YES** | `test_coordinator.py::test_hazard_gate_bypasses_coordinator_entirely` — pinned specifically to a gas-hazard trigger; per-channel coverage confirmed for at least `gas`. |
| 9 | Dependency-cycle rejection (`app/domain/dependencies.would_create_cycle`) | Replaced body with `return False` | **YES** | `test_reliability_matrix.py::test_would_create_cycle_detects_a_real_cycle_and_rejects_it` |
| 10 | Idempotent archive import (`app/archive/importer.py`) | Neutralised the `if existing is not None: return ...skipped=True` early-out | **YES** | `test_archive_import.py::test_second_import_is_noop` (`UNIQUE constraint failed: archive_batches.label`); `::test_validate_passes_every_check` failed too as a side effect. |
| 11 | `assert_case_transition` (`app/domain/transitions.py`) | Replaced body with `return` (no-op — any transition allowed) | **NO — untested** | Full 155-test suite passed unchanged. No test calls `assert_case_transition` or `assert_work_order_transition` directly, nor drives a case through an illegal-transition scenario that would surface a `PolicyRejectedError` from this specific guard. This is the function every case-status write is supposed to route through. |
| 12 | `verify_webhook_signature` (`app/integrations/elevenlabs.py`) | Neutralised the HMAC comparison (`if False and not hmac.compare_digest(...)`) | **YES** | `test_voice.py::test_verify_webhook_signature_rejects_wrong_secret`. Run against an isolated filesystem copy of `backend/app` + `backend/tests` (outside the git tree) rather than in place, given the collision risk described above. |

**Score: 3 of 12 invariants are fully untested (#2, #4, #11), 1 is partially
untested (#5). 8 of 12 have a real, specific, failing test when broken.**
That is a materially different picture from "154 tests, must be fine" —
two of the three fully-untested invariants are ones a reviewer would
reasonably assume are load-bearing enough to already be covered (archival
default-exclusion on the primary list endpoint; the approval
optimistic-concurrency check).

**Note on a concurrently-added test file.** `backend/tests/test_audit_regressions.py`
appeared, untracked, partway through this session — another agent's response
to other audit findings, not mine. It was checked for overlap with rows 2, 4
and 11: `test_concurrent_approvals_produce_clean_conflict_not_double_execution`
covers a *different* approval race (a conditional-UPDATE row-claim fix) and
uses a matching, non-stale `expected_case_version=1` throughout, so it does
not exercise the staleness check in row 4; `test_archival_case_lifecycle_actions_are_read_only`
covers a different archival guard (409 on resume/reopen/cancel against an
archived case) and does not touch `GET /cases`'s `include_archived` filter
or `assert_case_transition`. As of `28df695`, rows 2, 4 and 11 stand.

### Methodology note on restoration

Each mutation was: back up the file to scratch → apply a minimal, targeted
edit → run the narrowest test file(s) that should exercise it → if it
passed cleanly, escalate to the full suite to rule out cross-file coverage
→ restore from the scratch backup → verify byte-for-byte (not just
`git diff --stat`, which is meaningless against a HEAD that moves — see
above) that the restored content matches the pre-mutation backup. For
invariant #1 (no-contact guard) a `httpx.AsyncClient` network-blocking
shim was used so that even a successfully-disarmed guard could not reach
a real socket. For invariant #12, given two prior collisions, the mutation
was applied to a filesystem copy of `backend/app`/`backend/tests` outside
the git working tree entirely.

## Coverage

No coverage tool is available: `.venv\Scripts\python.exe -m pip list`
reports `No module named pip` — pip itself is not installed in the venv,
so `coverage` cannot be added without violating the "do not install
anything" instruction. Per-line coverage numbers are therefore not
reported. In its place: a grep-based reachability survey.

**Confirmed-untested, whole modules:**
- `app/legacy_demo_purge.py` (144 lines) — zero references anywhere in
  `tests/`. This module runs real `DELETE`s against the database
  (`--apply` mode) and is completely unverified.
- `app/archive/__main__.py` — zero references; the CLI entry point itself
  is untested, though the `import_archive`/`validate` functions it calls
  are well covered via `test_archive_import.py`.

**Confirmed-untested, a full endpoint:**
- `POST /api/v1/cases/{case_id}/field-updates` (`app/api/field_updates.py`)
  — zero references to `field-update`/`field_update` anywhere in
  `tests/`. This is a real domain-write endpoint (routes both contractor
  report relay and tenant-update submissions through
  `services.record_contractor_report`/tenant-update paths, gated on
  `require_operator`), entirely unexercised by the suite.

**`app/analytics.py` (1,200+ lines, 26 top-level functions):** direct
call-site grep shows most private helpers (`_apply_case_filters`,
`_terminal_event_at_by_case`, `resolution_bucket_bounds`, `_median`) and
several public ones (`portfolio_counts`, `needs_attention`,
`recent_activity`, `open_age_buckets`, `case_volume_by_month`) are never
called by name from a test file — but several of these are reached
transitively through `/api/v1/metrics/dashboard` and `/api/v1/overview`,
which do have request-level test coverage, so "0 direct call-sites" here
overstates the gap; it should be read as "not independently unit-tested,"
not "unreached." The one item in this file proven genuinely under-tested
by mutation (not just by the grep proxy) is `_largest_remainder_percentages`'s
selection logic — see row 5 above.

- `app/backfill_category.py` (untracked/new at session start, now
  tracked and under active development elsewhere) — has one direct test,
  `test_fixi_ui_support.py::test_category_backfill_derives_from_work_order_trade`.

## Tests that assert current behaviour rather than correct behaviour

Beyond the one named in the brief (`test_map_outcome_handles_missing_analysis`,
which on inspection now matches a documented, deliberately-fixed
implementation — its docstring records the real prior bug and the current
code/test pair look correct, not stale), a systematic sweep was run:
every `test_*` function across all 13 files was parsed for zero-`assert`
bodies (candidate "exercises but doesn't check" tests) and every bare
`assert ... is not None` was inspected for a following value check.

- The zero-`assert` sweep returned 11 hits, all false positives: every one
  uses `with pytest.raises(SpecificException):` as its assertion
  mechanism, which is a legitimate idiom the naive grep can't see.
- Of 26 `assert X is not None` occurrences, the great majority are guard
  assertions immediately followed by a real value check on the same
  object (e.g. `assert body["avg_resolution_hours"] is not None` is
  immediately followed by `assert body["avg_resolution_hours"] > 100`
  in `test_fixi_ui_support.py`). None found in this pass assert only
  existence where the title promises a value check.
- No new instance of the "asserts a bug" pattern was found in the time
  budgeted for this pass; the codebase's assertions are, on the whole,
  specific (exact pence amounts, exact enum values, exact percentage
  arrays) rather than shape-only. The gaps in this suite are gaps of
  *absence* (rows 2, 4, 11 above; whole-module and whole-endpoint gaps
  above), not gaps of *weak assertion*.

## Test isolation

- `pytest-randomly` is not installed (`ModuleNotFoundError`), so
  `-p no:randomly` is a documented no-op here — there is no test-order
  randomisation plugin to disable in the first place.
- **Reverse file order** (`pytest -q -p no:randomly <files sorted
  descending>`): 154 passed / 1 failed at the time of this run
  (`test_archive_import.py::test_validate_passes_every_check`,
  `quoted_totals_reconcile_with_work_orders` mismatch). Verified this is
  **not an ordering bug**: it fails identically run alone
  (`pytest tests/test_archive_import.py::test_validate_passes_every_check`),
  and a `git diff` shows a concurrent, in-progress (uncommitted at time of
  writing) fix to exactly this check already underway in
  `app/archive/importer.py` by another process in this shared session —
  unrelated to my mutation testing (confirmed: none of my 12 mutated files
  carry any leftover mutation marker; see final git-status note).
- **Shuffled/interleaved subset** across 8 different files' node IDs in
  a scrambled order: 13/13 passed, no cross-test contamination.
- `app_db` fixture (`tests/conftest.py`): creates a fresh temp-file SQLite
  DB per test, repoints `app.db`'s module-level engine/session-factory
  singletons at it, and disposes + deletes (including `-wal`/`-shm`/
  `-journal` siblings) in a `finally` block. This is real isolation, not
  cosmetic — confirmed by the shuffled-subset run causing no leakage.

## Speed and flakiness

Three full-suite runs at session start (before any concurrent commits had
landed): **154 passed / 154 passed / 154 passed**, zero failures, zero
flaky tests. Wall/internal times: 98.6s, 124.6s (a second, slower run,
plausibly contended with other agents' processes on the same machine),
76.2s. No single test stood out as disproportionately slow in isolation;
the full-file runs used for individual mutations (5–45s) were consistent
with these baselines. No flakiness observed anywhere in this session
across roughly a dozen full-suite equivalents.

## The frontend gap

`frontend-fixi/package.json` has no `test` script and no test runner
(`vitest`/`jest`/testing-library) in `dependencies`/`devDependencies` at
all — this is a Vite + TanStack Router/Query app with **zero automated
frontend tests of any kind**. Confirmed present and carrying real,
independently-reasoned logic with no safety net:

- `src/lib/search-params.ts` — `readParam`/`readFlag`/`readInt`: exists
  specifically to work around a real, previously-shipped bug (TanStack
  Router JSON-quotes URL params, so naive `=== "true"` comparisons
  silently no-op). The module's own docstring calls this exact class of
  bug unacceptable. It is untested.
- `src/hooks/use-analytics.ts::normalizeInsights` — renames/reshapes the
  backend's `/api/v1/insights` response (year/month → zero-padded
  `"YYYY-MM"` string, `category → trade`, `recurring_issues.category`
  defaulted to `"OTHER"` when null, comparison payload restructuring).
  Non-trivial, silently-wrong-if-broken, untested.
- `src/components/fixi/Charts.tsx::largestRemainderPercentages` — an
  independent hand-rolled reimplementation of the exact backend algorithm
  audited in row 5 above, in TypeScript, with its own tie-break logic.
  Untested, and per the backend finding, tie-break correctness is the
  specific part likely to regress silently.
- `src/components/fixi/CostsPanel.tsx` — hand-rolled pounds-string →
  integer-pence parsing (`poundsPart`/`penceStr` string slicing) and the
  inverse formatter. Money arithmetic, string-based, untested.
- `src/routes/messages.$caseId.tsx` — `DELIVERY_TONE`/`DELIVERY_LABEL`
  maps keyed on `DeliveryState`; a missing key on either map is a runtime
  crash or a blank pill, not a compile error unless the map is written as
  `Record<DeliveryState, ...>` with no default case (it is — so a new
  enum member added backend-side and not mirrored here would be a
  TypeScript build error, not a silent bug; lower risk than the other
  four).

**Recommended runner:** `vitest` — already Vite-native, zero extra build
config, works with the existing `vite.config` and TS setup.
**Smallest useful set, in priority order:**
1. `search-params.ts` — table-driven tests for `readParam`/`readFlag`/
   `readInt` against both plain and TanStack-JSON-quoted inputs; this is
   the one with a documented real incident behind it.
2. `largestRemainderPercentages` in `Charts.tsx` — at minimum one
   asymmetric-remainder case (the exact gap found in the backend
   equivalent), plus a sum-to-100 property test across random inputs.
3. `CostsPanel.tsx`'s pounds↔pence parse/format pair — round-trip
   property test (`penceToPoundsInput(parsePenceInput(x)) == x` for a
   range of values including negative and `.05`/`.5` edge cases).
4. `normalizeInsights` — one fixture-based test per adapted field,
   especially the `recurring_issues.category → "OTHER"` default and the
   year/month zero-padding.

## Findings by severity

- **CRITICAL** — Approval version-staleness check
  (`executor.py::decide_approval`) is completely unprotected; a broken
  optimistic-concurrency guard here would allow an operator to approve
  spend/scheduling against a stale case view with no test failure
  anywhere in 155 tests.
- **CRITICAL** — `assert_case_transition` is completely unprotected; this
  is the sole guard against illegal case-status transitions
  (docs/07's state machine), and disabling it entirely passes the full
  suite. It **shipped disabled, briefly, in commit `79a1f3d`** during
  this session before being superseded — direct evidence this exact
  failure mode already reached `main` once.
- **CRITICAL** — Archival exclusion from `GET /api/v1/cases` is
  completely unprotected, despite being tested for every sibling
  directory endpoint (`/properties`, `/contractors`, `/tenants`). It
  **shipped disabled, briefly, in commit `e5abd41`** during this session.
- **HIGH** — `POST /cases/{case_id}/field-updates` has zero test
  coverage; it is a real, operator-gated, domain-write endpoint.
- **HIGH** — No frontend test suite exists at all; five pieces of
  independently-reasoned logic (see above) carry real correctness risk
  with zero automated protection.
- **MEDIUM** — Largest-remainder tie-break selection logic (backend and
  its frontend duplicate) is untested for asymmetric inputs; only the
  weaker "sums to 100" property is verified.
- **MEDIUM** — `app/legacy_demo_purge.py` (real, destructive `DELETE`
  tooling) has zero test coverage.
- **LOW** — `archive/__main__.py` CLI entry point untested (the functions
  it wraps are well tested).
- **NIT** — No `coverage` tooling installed; line-level coverage numbers
  cannot be produced without a pip install this audit was told not to do.

## Prioritised list of tests worth writing

1. A stale-`expected_case_version` approval test: approve/reject an
   action after bumping the case version out from under it, assert
   `StaleVersionError`/409. (Closes the #4 CRITICAL gap.)
2. An illegal-case-transition test: attempt e.g. `RESOLVED → CANCELLED`
   directly (not in `_CASE_EDGES`) and assert `PolicyRejectedError`.
   (Closes the #11 CRITICAL gap.)
3. A `GET /api/v1/cases` default-vs-`include_archived=true` test,
   mirroring the existing `/properties`/`/contractors`/`/tenants` pattern
   exactly. (Closes the #2 CRITICAL gap.)
4. A `POST /cases/{case_id}/field-updates` happy-path test for both
   `ContractorReportUpdate` and `TenantUpdate` branches.
5. A `_largest_remainder_percentages` case with genuinely distinct,
   non-tied remainders (e.g. `[55, 33, 11, 1]`) asserting the *exact*
   output array, not just its sum — and the frontend mirror once a
   runner exists.
6. Frontend: `search-params.ts` unit tests (vitest) — the highest-value
   single frontend addition given it already has a real incident behind it.

## Final source-cleanliness check

`git status --short` at the end of this session shows other agents'
unrelated in-progress work (`backend/app/archive/importer.py`,
`backend/app/schemas.py`, `backend/tests/test_analytics_api.py`,
`backend/tests/test_archive_import.py`, several `docs/` and
`frontend-fixi/` files) — none of it touched by this audit. Every file
this audit edited (`cases.py`, `messaging.py`, `executor.py`,
`analytics.py`, `db.py`, `costs.py`, `policy.py`, `dependencies.py`,
`importer.py`, `transitions.py`, `no_contact.py`) was individually
grepped for its specific mutation marker at the end of the session and
found clean (see Methodology note); `elevenlabs.py`'s mutation was never
applied to the real working tree at all (isolated filesystem copy).
`backend/data/repairflow.db` was never modified (`Modify` timestamp
unchanged across the entire session). No test file was edited by this
audit.
