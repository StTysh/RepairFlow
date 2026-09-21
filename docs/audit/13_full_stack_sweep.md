# Full-stack sweep — what the twelve audits left behind

Date: 2026-09-21. Scope: the whole repository — `backend/app/{domain,orchestration,agents,api,integrations}`, `analytics.py`, `archive/`, `models.py`, `schemas.py`, `db.py`, `config.py`, `backend/tests/`, `backend/scripts/`, `frontend-fixi/src/{routes,hooks,lib,api,components}`, the documentation set, and the live `backend/data/repairflow.db`.

Read-only for the repository. The live database was **copied** to a scratch path and every query ran against the copy; a SHA256 comparison confirmed the original was untouched. One isolated backend instance was started on port 8010 against a scratch `DATABASE_PATH`, used for the HTTP evidence below, and shut down.

This is the thirteenth report in `docs/audit/`. Unlike 01–12, which each owned one slice, this one was run *after* the fix pass and asks a different question: **what survived it?**

## Severity counts

CRITICAL: 1 · HIGH: 4 · MEDIUM: 9 · LOW: 6 · Documentation errors: 8

## Verdict

The application genuinely works. Everything executable passed: 214 backend tests, 62 frontend tests, 41/41 end-to-end HTTP acceptance checks, eslint 0 errors / 5 warnings, `tsc` clean, a clean production build, and `integrity_check` + `foreign_key_check` clean on the live database. Every scale figure in `docs/APPLICATION_STATE.md` was independently recounted and matched. Ten struck rows were spot-checked and all ten are genuinely resolved.

The problems are one layer down, and they cluster into two patterns worth more than any individual finding:

**Pattern 1 — fixes were applied at the site where the bug was found, not across the bug's class.** Three defects are the same class as a defect already fixed elsewhere in this codebase (§A2, §A5, §A6). Someone reading the fix commits would reasonably believe the class was handled.

**Pattern 2 — the tracker lost findings the audits had already made.** `docs/audit/06` raised a CRITICAL that `APPLICATION_STATE.md` never recorded, and a HIGH that it struck on grounds addressing only half the finding (§B). Both are still live in the code today. This is the more serious of the two, because the tracker is the document everything else defers to.

---

# Part A — findings new in this sweep

## A1. CRITICAL — cancelled archival cases are counted as resolved

`backend/app/analytics.py:832-836` (`resolution_time_distribution`) and `:989-996` (`case_detail_rows`).

The `include_archived` branch ORs in `archive_batch_id IS NOT NULL AND archived_closed_at IS NOT NULL` with **no status predicate**. `case_detail_rows` does `closed_and_resolved = is_archived or case_is_resolved(case.status)`, where `is_archived` short-circuits the status check. Both sit two functions below `case_is_resolved`, whose docstring reads: *"CANCELLED is a different terminal state (the case was called off, not fixed) and is never counted as resolved."*

Reproduced by executing the generator directly:

```
total archival cases: 60
by status: {RESOLVED: 56, CANCELLED: 4}
CANCELLED with archived_closed_at set: 4
```

All four cancelled cases carry `archived_closed_at`, so with `include_archived` at its default they are averaged into resolution-time statistics with a fabricated `resolution_hours`, reaching Insights, the Reports summary, the drill-down rows and the CSV export.

**This is not a new finding.** See §B1 — it is `docs/audit/06` Finding 3, recorded as CRITICAL on 2026-09-20 with its own worked example, and never carried into the tracker.

## A2. HIGH — the frontend cannot parse the backend's primary error shape

`frontend-fixi/src/api/client.ts:106-118` (`readErrorDetail`) unwraps only a `detail` key, then falls through to `JSON.stringify(body)`. `backend/app/api/errors.py:32-37` returns `{"error":{"code","message","retryable","correlation_id"}}` for every `DomainError`.

Measured over live HTTP against a running instance:

| Request | Status | Content-Type | Body |
|---|---|---|---|
| `GET /api/v1/cases/<missing-uuid>` | 404 | `application/json` | `{"error":{"code":"NOT_FOUND",…}}` |
| `GET /api/v1/definitely-not-a-route` | 404 | `text/html` | the SPA shell |
| `POST /api/v1/cases` with `{}` | 422 | `application/json` | `{"detail":[…]}` |

Only the third is readable by the client. Every domain failure — including the stale-version 409 that `use-case-actions.ts:21` states it handles — reaches the operator as a stringified JSON object in a toast.

`APPLICATION_STATE.md` row 10 files the envelope split as MEDIUM backend tidiness across "~30 routes". It is in fact user-visible, and wider than stated: `require_operator` (`api/deps.py:21,28`) raises a raw `HTTPException`, so all ~70 protected routes can also emit a third shape, `{"detail":"…"}`, on auth failure.

**Class note:** the same partial-fix pattern as Pattern 1. The API side of the envelope was scoped as a backend task; nobody checked the only consumer.

## A3. HIGH — a stale COORDINATE job can wake the coordinator on a RESOLVED case and reach an outbound call

`backend/app/orchestration/dispatcher.py:121-131` excludes only `ESCALATED` and `CANCELLED`. The comment explains the `RESOLVED` carve-out: a hazard reported after resolution must still be handled. But the carve-out is unconditional — *any* stale COORDINATE job on a resolved case reaches `coordinator.decide()`, and `services.request_information` / `request_confirmation` (`backend/app/domain/services.py:873-936`) never check `case.status` before enqueuing `PLACE_CALL`.

Nothing restricts the leniency to hazard-triggered wakes. The practical guard today is `no_contact.py` arming under pytest, which does nothing for a normally started server.

## A4. HIGH — `scripts/verify_scenarios.py`'s safety guard is decorative

`backend/scripts/verify_scenarios.py:4-6` states the script *"refuses to run"* against a non-isolated database. It does not. `check()` (line 30) appends to a list and prints; the only `sys.exit` in the file is `sys.exit(main())` at line 379. The "starting from an empty operational workspace" assertion records a FAIL and continues through all eight scenarios.

Pointed at a server backed by `backend/data/repairflow.db`, this script writes fictional properties, tenants, cases, notes and documents into the file holding the only genuine ElevenLabs call history — the single thing every handoff document marks as irreplaceable. The only real protection is how the *server* was started.

## A5. HIGH — `cancel_appointment` holds the domain transaction across the connector call

`backend/app/domain/services.py:843-845` calls `mock_booking_connector.cancel(session, …)` inline, inside the session the caller commits (`api/deps.py:35-40`, `api/cases.py:548`).

`backend/app/orchestration/executor.py:416-420` opens a **separate** `booking_session` for `book()` specifically so a provider call never sits inside an open transaction. Cancellation got no such split. Harmless while the connector is an in-process mock; a live breach of CLAUDE.md's "do not hold a DB transaction across any network call" the moment the §7.2 replacement lands.

**This must be fixed as part of the booking replacement, not after it.**

## A6. MEDIUM — two more instances of already-fixed bug classes

- **`OrchestrationRun` can strand at RUNNING forever.** `dispatcher.py:180-204` catches only `DomainError`/`StaleVersionError`; any other exception during `admit_proposal` leaves the row RUNNING with no recovery. `executor.py:426-456` handles the structurally identical case for `ActionRecord` with a deliberate broad `except Exception → UNKNOWN`. Same bug, fixed in one file, not the other.
- **`enqueue_job` TOCTOU.** `services.py:136-155` is a plain SELECT-then-INSERT against a `dedupe_key UNIQUE` column (`models.py:542`) with no `IntegrityError` handling. This is the same race that was found and closed for the approval path (`executor.py:229-243`, a conditional `UPDATE … WHERE state=AWAITING_APPROVAL`).

## A7. MEDIUM — `resolve_case` has no hazard gate

`services.py:939-974` checks status, tenant confirmation, unresolved concerns, required work and dependency edges — never risk. docs/06 lists "no unsafe flag" as a closure requirement, and `apply_triage` enforces `policy.is_hazard()` inline at `services.py:516`. The only hazard-on-resolution defence lives in the dispatcher's wake gate, which fires on a fresh COORDINATE job — not on the approval→execute path that actually calls `resolve_case`. A hazard recorded while AWAITING_CONFIRMATION, racing an already-queued ResolveCase approval, resolves a case with a live hazard on record.

## A8. MEDIUM — `escalate_to_human` silently mutates a CANCELLED case

`services.py:977-991`. When the status is CANCELLED the transition guard at line 979 skips, but `escalation_reason`, `bump_version(case)` and a `CASE_ESCALATED` event are written unconditionally at 983-990. A phantom escalation lands on a case docs/07 treats as terminal. Every sibling function (`resolve_case`, `add_prerequisite`, `accept_report`) raises `PolicyRejectedError` instead of silently no-opping.

## A9. MEDIUM — `legacy_demo_purge` cannot remove notes or documents

`backend/app/legacy_demo_purge.py:64-99`. The `ordered` deletion list omits `NoteModel` and `DocumentModel`. Both attach via a generic `subject_type=CASE, subject_id=<case_id>` with **no foreign key** back to `repair_cases`, and `api/notes.py` / `api/documents.py` place no restriction on the nine legacy case ids. Any note or document attached to a legacy case is never counted (not even by `--dry-run`), never deleted, and its file on disk is never unlinked.

`remove_archive` handles the equivalent correctly, via an `archive_batch_id` column on both tables — and has a test asserting zero orphans. The module's own safety claim ("getting the order wrong raises rather than silently orphaning") does not apply, because these two tables are never referenced at all.

## A10. MEDIUM — `record_field_update` has no tests whatsoever

`backend/app/api/field_updates.py:92`. Greps for `field_update`, `field-update` and `FieldUpdate` across all 17 test files return nothing. The endpoint handles three discriminated variants (`ContractorReportUpdate`, `TenantUpdate`, `AttendanceWindowEndedUpdate`), a future-timestamp rejection (`observed_at > recorded_at`), a cross-case appointment-ownership check, and operator-attribution provenance rules its own docstring frames as safety-relevant.

It is also the module that replaced a retired demo control, which makes it a migration-risk hotspot with zero coverage. **The highest-value untested function in the codebase.**

## A11. MEDIUM — live provider calls with no structural gate

`create_signed_session` (`api/voice.py:107`, `integrations/elevenlabs.py:84-96`) and `TavilyResearchAdapter.search()` (`integrations/tavily.py:83`) are real outbound network calls with no `no_contact` check. They are gated only by construction-time `elevenlabs_live` / `tavily_live` flags and by test authors remembering to monkeypatch — `PYTEST_CURRENT_TEST` does not stop them.

Neither reaches a person, so §4's guarantee holds exactly as worded. But §4 discusses only `place_outbound_call`, and never distinguishes "reaches a person" (structurally guarded) from "reaches a live provider" (not guarded, by design). That distinction should be written down.

**Positive result:** the phone-call guard itself was attacked five ways — import order, the `get_settings()` lru_cache, monkeypatching, a job-body bypass and the webhook routes — with no way through. §4's core claim is sound.

## A12. MEDIUM — `list_contractors` loads the entire table

`backend/app/api/contractors.py:178-202` calls `.scalars().all()` with no SQL `LIMIT`, then applies the trade filter and offset/limit pagination in Python. `properties.py:251-289` and `tenants.py:218-261` do the same listing correctly with SQL `LIMIT`/`OFFSET` plus a separate `COUNT`, so this is an inconsistency rather than a house pattern.

## A13. MEDIUM — no rate limiting anywhere

`ToolErrorCode.RATE_LIMITED` / HTTP 429 is defined in `schemas.py` and `errors.py` and never raised. docs/16 calls for rate-limiting public routes. The two surfaces that bypass operator auth — the HMAC webhook and the tool-secret routes — rely solely on secret verification with no throttling.

## A14. LOW — assorted

- `find_appointment_options` never checks `contractor_id` against the case's approved roster (`agents/read_tools.py:101-127`); every other read tool validates that the target row belongs to the case.
- `Settings.gemini_fallback_model` (`config.py:37`) is referenced nowhere. docs/13 describes a fallback path that does not exist.
- `GeminiCoordinator.decide` (`coordinator.py:113-126`) has no exception handling around `agent.run(...)`; docs/13's provider-failure contract calls for bounded backoff.
- `DecisionCard.tsx:75` uses `window.prompt()` for a rejection reason and does not `.trim()`, so whitespace is accepted as a reason.
- `WorkGraph.tsx` has no screen-reader alternative to its canvas, unlike `Charts.tsx` / `PropertyStatsCharts.tsx`, which pair every chart with an `sr-only` data list. The dependency graph is the one thing a keyboard-only operator cannot read.
- `documents.py:237-248` unlinks the file before the outer commit; a commit failure leaves a row whose file is already gone.
- Two parallel messaging systems address the same case: `use-case-messages.ts` (read-only, old endpoint) and `use-messaging.ts` (read/write, current). The ticket-detail comment claiming the send endpoint "doesn't exist yet" is false — `api/messaging.py:155-322` is live.
- `properties.$propertyId.history.tsx:60-88` mirrors URL state via raw `window.history.replaceState`, bypassing the router's history adapter — a third mechanism alongside the two already in use.

---

# Part B — findings the tracker lost

This is the section that matters most.

## B1. `docs/audit/06` Finding 3 was never tracked, and is still live

Recorded 2026-09-20 as **CRITICAL**, with a worked example and an explicit argument for why it is critical rather than high: *"there is no structural barrier keeping it from firing on the default, most-viewed path."*

`docs/audit/06`'s header carries an "Update, 2026-09-20" note marking **Finding 1** fixed. There is no such note for Finding 3. `APPLICATION_STATE.md` — the document CLAUDE.md designates as the tracker — contains no row for it in any form, struck or open. It is reproduced above as §A1 and is live in today's code.

## B2. `docs/audit/06` Finding 4 was struck on grounds that answer only half of it

`APPLICATION_STATE.md` row 9 reads: *"~~A late reopen reports stale `resolution_hours`.~~ **Was already correct** — `_terminal_event_at_by_case` takes MAX. Probed directly: 2,376h reported, not 48h. The row described a bug that did not exist."*

The MAX claim is true (`analytics.py:463`). But audit 06 Finding 4 made two claims, and the second was that `_terminal_event_at_by_case` recognises only `CASE_RESOLVED`/`CASE_CANCELLED`, after which `resolution_hours` silently substitutes `updated_at` — producing a duration indistinguishable downstream from an event-derived one, with `skipped_count` never firing for it.

`analytics.py:506` still reads `end = case.terminal_event_at or case.updated_at`. The fallback is untouched. Row 9 should be reopened for that half.

---

# Part C — documentation corrections

| Location | Claim | Truth |
|---|---|---|
| `CLAUDE.md`, `APPLICATION_STATE.md` §2 | "19 routers" | **18.** Only 18 files define and mount a router. The count reconciled only by including the untracked, unmounted `api/demo.py` — since deleted |
| `APPLICATION_STATE.md` §5 | "24 regression tests (32 cases)" | 35 functions, **43 cases** collected |
| `APPLICATION_STATE.md` | `category` backfilled | **NULL on all 14 cases.** The command exists and has never been run against this database |
| `APPLICATION_STATE.md` "One thing the docs got wrong" | the two failed LIVE calls came from "a DNS error" | No "dns" appears in any text column of the database. The stored reason is `"reconciliation abandoned"` after 1,806 and 3,795 attempts. Whatever the source, it is not this file |
| `APPLICATION_STATE.md` §5 | "the production database was missing all eight archival indexes" | **All 8 exist.** Stale — fixed |
| `APPLICATION_STATE.md` §5 row for the SPA fallback | "no longer silently depends on the `dist/404.html` copy either — both pinned by tests" | The status code is pinned; the body is not. `_spa_app(tmp_path)` builds a dist with **no** `404.html` by design, but the shipped `dist/` has one, so Starlette serves it and an unmatched `/api` path returns **404 with the SPA shell as the body** — measured over HTTP |
| `docs/17` §43 | "Enums have CHECK constraints" | False for the running schema, and unevenly false: `documents`, `notes` and `cost_entries` do have them; `repair_cases`, `work_orders`, `contractors`, `appointments`, `jobs`, `communications`, `action_records`, `case_events` do not. The deviation was never logged in `docs/26` |
| `CLAUDE.md` "Actual structure" | lists `domain/{transitions,policy,dependencies,services}` | omits `domain/errors.py`, which `APPLICATION_STATE.md` §2 correctly includes |
| `prompts/NEW_SESSION_HANDOFF.md` | "77 unpushed commits on `main` and that is intentional… Do not push" | Stale as of 2026-09-21. The work was pushed from another machine; `main` now tracks `origin/main` exactly |

Also undocumented: the live database carries a leftover `alembic_version` table stamped `dd3584cdf57b`, proving Alembic was once run against this exact file before the freeze decision. It is inert but will mislead anyone inspecting the schema.

---

# Part D — verified correct

Run, not read:

| Check | Result |
|---|---|
| `uv run pytest -q` | **214 passed**, ~26–33s |
| `npm test` | **62 passed** |
| `scripts/verify_scenarios.py` against an isolated instance | **41/41 checks passed** |
| `npx eslint .` | **0 errors, 5 warnings** — exactly as documented |
| `npx tsc --noEmit` | clean |
| `npm run build` | clean, 802ms |
| `PRAGMA integrity_check` / `foreign_key_check` on a DB copy | `ok` / 0 violations |

Confirmed sound by inspection: the no-contact guard (five attack vectors, no way through); integer-pence money with no float in any monetary path; the CORS wildcard-plus-credentials refusal and the Alembic opt-in guard; the dev-port base-URL resolution; every scale figure in `APPLICATION_STATE.md` §1; ten of the struck rows; the sub-1024px navigation drawer, which is genuinely fixed (`AppShell.tsx:172-254`, including a `matchMedia` listener that force-closes on return to desktop); and the absence of any fabricated status string, no-op control or toast-without-a-write across all 20 components.

The test suite deserves specific credit: no `unittest.mock` anywhere. Tests drive real DB, executor, dispatcher and HTTP layers, and `app_db` repoints the engine singleton at a temp file so `backend/data/repairflow.db` is genuinely unreachable from a test.

The #418 hydration mismatch now has a traced cause: `vite.config.ts`'s `tanstackStart({ spa: { prerender } })` bakes a static `index.html` at build time with no backend, so every panel branching on `.isLoading` diverges on first paint. Its "cosmetic" classification survives.

---

# Confidence

Not verified: any live provider call (deliberate); the "each regression test proven to fail when its fix is reverted" claim, which requires reverting production code; the runtime consequence of the `replaceState` router-desync concern, which needs a browser; and whether the `enqueue_job` race is frequently hit versus merely reachable, which depends on SQLite locking behaviour not examined in depth.

§A1's four-case leak was reproduced by executing the generator, and both consuming code paths were read directly, but the contaminated average was not observed against an imported database.

---

# Addendum — what was fixed, 2026-09-21

This report was written before the fix pass it prompted. Closed since,
each with a regression test proven to fail when the fix is reverted:

- **A2** — the client now parses all three error shapes; fixed once in
  `readErrorDetail` rather than in each of the six mutation hooks.
- **A11 (partly)** — not the guard itself, but the whole auth surface:
  sign-in is removed and `WWW-Authenticate` is gone. See below.
- **A13 / unbounded queries** — `?limit=-1` is rejected on both
  endpoints.
- **Missing catch-all handler** — an unmodelled crash now returns the
  typed envelope with a `correlation_id`.
- **Search** — global search is wired into the UI; `#4` and single-digit
  case numbers resolve.
- **Hidden capability** — `GET /cases/{id}/runs`, `approved_contractors`,
  `policy_snapshot` and the recording-retry endpoint are all surfaced.
- **Archive reports** — 107 generated, closing the "no write-ups on 60
  sample cases" fixture gap, with a 15th validation check.
- **Contractor roster** — 6 to 18; trade `OTHER` had none.

**Found after this report, and worse than anything in it:** with
`OPERATOR_AUTH_ENABLED` at its then-default of `True`, the app rendered
a permanently blank page — a `401 WWW-Authenticate: Basic` caused Chrome
to withhold the response from the SPA's auth probe, which never settled.
A fresh clone following README exactly hit this every time. It could
only be found by running the app in a browser, which is the lesson this
report opened with. Recorded in `docs/26`, 2026-09-21.

**Withdrawn:** a suspected hang on `/properties/{id}/history` was a
wedged automation tab, not an application fault. Two hypotheses were
tested and both were wrong; the page renders correctly in a fresh tab.
The change made on the strength of the wrong diagnosis was reverted.

**Still open from this report:** A1 (cancelled archival cases counted as
resolved — see also B1/B2, the findings the tracker lost), A3, A5, A6,
A7, A8, A9, A10, A12.

