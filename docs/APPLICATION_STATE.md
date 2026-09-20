# Fixi — complete application state

**What this is.** One document covering everything the application has:
what exists, what works, what does not, what is left to fix, and the
decisions still open. Written 2026-09-20 after a full migration from the
hackathon build plus a twelve-part audit sweep.

**How to read it.** §1–§4 describe the system. §5 is the honest verdict
per area. §6 is the outstanding work, ranked. §7 is what needs a human
decision. Nothing in here is aspirational — where something is unverified
it says so.

Companion files: `docs/audit/` (the eleven raw audit reports, with
`file:line` evidence), `docs/UI2_IMPLEMENTATION_HANDOFF.md` (what the
migration did), `docs/UI2_TODO.md` (the queued work), `docs/26` (the
running corrections log).

---

## 1. What the application is

A repair-coordination tool for a small property portfolio. An operator
records a reported repair; an LLM coordinator proposes one next action at
a time; a deterministic policy decides whether that action can execute
automatically or needs approval; a durable job queue carries the work
across restarts. Cases persist across calls, visits and contractor
reports rather than living in a chat transcript.

**Stack.** FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + SQLite
(`backend/`). React + TanStack Router + Tailwind, built as a static SPA
and served by FastAPI (`frontend-fixi/`). Pydantic AI over Gemini for the
coordinator. ElevenLabs (with Twilio behind it) for voice. Tavily for
contractor research.

**Scale today**, measured 2026-09-20, not estimated: ~15,000 lines of
backend Python across 57 files; 17 frontend routes and 21 components;
73 HTTP routes (72 under `/api`, `/webhooks` and `/integrations`, plus
`/healthz`); **25** database tables; **203** backend tests; no frontend
tests.

---

## 2. What exists

### Backend

| Area | Modules | State |
| --- | --- | --- |
| Domain engine | `domain/{services,transitions,policy,dependencies,errors}.py` | Complete. Event-sourced: append-only `CaseEvent`, derived `CaseSnapshot`, typed action ledger. |
| Orchestration | `orchestration/{dispatcher,worker,executor,dedupe}.py` | Complete. Durable `JobModel` queue, leases, idempotency keys, one proposal per wake. |
| Agent | `agents/{coordinator,read_tools,instructions,dependencies}.py` | Complete. Gemini via Pydantic AI, scoped read-only tools, bounded retries, redacted snapshot. |
| Integrations | `integrations/{elevenlabs,tavily,booking,no_contact}.py` | ElevenLabs and Tavily complete; **booking is a mock that invents availability** (§5). |
| API | `api/` — 19 routers, 72 routes | Complete. |
| Analytics | `analytics.py` | Complete; **two money sources disagree** (§7). |
| Data commands | `seed.py`, `archive/`, `backfill_category.py`, `legacy_demo_purge.py` | Complete. |

### Frontend — eight destinations, 17 routes

`/` Overview · `/maintenance` + ticket detail (9 tabs) · `/properties` +
4 property tabs · `/contractors` + profile · `/tenants` + profile ·
`/insights` · `/messages` + thread · `/reports`.

### Database — 25 tables

Core: `properties`, `tenants`, `contractors`, `repair_cases`,
`repair_issues`, `work_orders`, `dependencies`, `appointments`,
`availability_windows`, `contractor_reports`, `contractor_candidates`,
`research_snapshots`, `communications`, `messages`, `webhook_receipts`,
`case_events`, `action_records`, `jobs`, `orchestration_runs`,
`mock_slots`, `mock_reservations`. Added by the migration:
`archive_batches`, `notes`, `documents`, `cost_entries`.

### Commands

```bash
# Run
cd backend && uv run uvicorn app.main:app --port 8000
cd frontend-fixi && rm -rf dist && npm run build     # FastAPI serves dist/ at /

# Test
cd backend && .venv/Scripts/python.exe -m pytest tests/ -q

# Optional data, all idempotent
python -m app.seed                      # sample portfolio (reference records only)
python -m app.archive --apply           # ~60 closed archival cases, 2021-2026
python -m app.archive --validate        # 13 integrity checks
python -m app.archive --remove          # removes exactly that batch
python -m app.backfill_category --apply # derive category from work-order trade
python -m app.legacy_demo_purge --apply # remove the old scripted demo cases

# End-to-end, against an isolated no-contact instance
FIXI_NO_CONTACT=1 OUTBOUND_CALLS_ENABLED=false OPERATOR_AUTH_ENABLED=false \
DATABASE_PATH=/tmp/v.db DOCUMENTS_DIR=/tmp/vdocs \
  python -m uvicorn app.main:app --port 8010
python scripts/verify_scenarios.py --base-url http://127.0.0.1:8010
```

---

## 3. The rules the system is built to keep

These are not aspirations; each is enforced somewhere specific, and the
audit checked each one.

| Rule | Where it lives |
| --- | --- |
| Archival sample history never enters operational counts, queues, notifications or agent wakes | `archive_batch_id IS NULL` filters across `analytics.py`, `cases.py`, `metrics.py`, `services.py` |
| Saving a message is not sending one | `MessageDeliveryState`; outward channels persist `DRAFT` with a stated reason |
| Recording an appointment is not a contractor confirming it | `POST /appointments/{id}/reschedule` writes PENDING, no provider booking id |
| A web candidate is not an approved contractor | `executor.py` rejects booking against a non-APPROVED contractor |
| No closure inferred from silence | `map_outcome` returns UNKNOWN without a USER turn |
| One action proposal per wake | `ToolOutput(ActionProposal)` |
| No DB transaction across a network or model call | three-phase commit-intent / call / apply-result in `dispatcher` and `executor` |
| Money is integer pence, end to end | every monetary column and computation |
| This process cannot contact anybody | `integrations/no_contact.py` (§4) |

---

## 4. The no-contact guarantee

The ElevenLabs + Twilio integration is real and configured. It is also
the single most dangerous thing in the repository, so it is guarded
twice.

`integrations/no_contact.py` reads the environment on **every** call and
never caches, so `get_settings()`'s `lru_cache` cannot leave it stale. It
self-enables under pytest, so the test suite cannot dial, message or
email anyone even by accident. The guard sits inside
`place_outbound_call()` — audited as the only function in the codebase
that reaches a person.

A harness may arm `provider_substitute()` so downstream call handling can
be exercised; the transport still refuses, so arming the flag without
patching the transport raises rather than dialling. That fail-closed
property has its own test.

**Verified with test doubles:** request acceptance, later completion,
conversation retrieval, transcript parsing, outcome mapping, duplicate
delivery, provider failure. Ten tests.

**Never verified live:** a real call, real audio, a real signed webhook.
Deliberately. To enable one you must unset `FIXI_NO_CONTACT`, set
`OUTBOUND_CALLS_ENABLED=true`, and put the recipient on
`OUTBOUND_CALL_ALLOWLIST` — all three.

An independent audit tried to defeat the guard via import order, the
settings cache, monkeypatching, a job-body bypass and the webhook routes,
and found no way through.

---

## 5. Verdict by area

Twelve auditors went over the system independently. Their raw reports,
with `file:line` evidence and reproductions, are in `docs/audit/`. This
is the summary.

### Works, and is verified

| Area | Evidence |
| --- | --- |
| **No-contact enforcement** | An auditor attempted to defeat it five ways and could not. Ten tests. §4. |
| **Domain transition graph** | Matches `docs/07` edge for edge. Resolution gating, redaction coverage and ScheduleVisit's validate-before-write ordering all confirmed correct. |
| **Auth coverage** | All 69 route×method combinations checked empirically with no credentials. Only the two deliberate carve-outs (HMAC webhook, tool-secret routes) are open. |
| **Webhook signature verification** | HMAC-SHA256, constant-time compare, timestamp window, fails closed when the secret is empty. An unsigned webhook can never be accepted. |
| **Archival containment** | Proved live over HTTP on a mixed database across `GET /cases`, `metrics/dashboard`, `overview`, `notifications` and the job queue. |
| **Archive import / remove** | 13/13 integrity checks, independently re-derived in raw SQL. Removal leaves zero orphans and no debris; control rows survive. |
| **`legacy_demo_purge`** | Run against a copy of the real database: removed exactly cases #6–#14, left #1–#5 and their genuine ElevenLabs transcripts untouched. |
| **Integer-pence money** | No float anywhere in a monetary path. |
| **Largest-remainder percentages** | Every edge case sums to exactly 100. |
| **Supply chain** | `uv.lock` hash-pinned; `npm audit` clean; no secrets in the built bundle. |
| **Every visible control does something** | All interactive elements traced: no `console.log`-only buttons, no toast-without-a-write, no fabricated "Sent"/"Confirmed" strings. |
| **The fixes are pinned** | 24 regression tests (32 cases with parametrisation), each proven to fail when its fix is reverted. |
| **Money reconciles** | One figure across five reads of the same scope: property stats by trade, by year, property history rows, insights case detail, and the costs endpoint. |

### Fixed during this session

Found by audit, fixed, and covered by new regression tests:

- A stale job could wake the coordinator on an **escalated or cancelled**
  case and drive it to an outbound call.
- A hazard reported **after resolution** was silently ignored.
- The reconciliation sweep **never gave up** — 5,601 job rows in the real
  database from two DNS failures, invisible to every failure metric.
- The **worker loop could die silently**, stopping every job kind, with
  nothing supervising it.
- An action could **strand at `RUNNING` forever**, after which the
  idempotency key blocked all retries of that work order.
- **Two concurrent approvals** both passed the check; only an incidental
  UNIQUE constraint prevented a double execution, surfacing as a 500.
- A contractor report posted to one case's URL with **another case's work
  order** landed on the other case.
- **Archival cases could be resumed, reopened and cancelled** despite
  being read-only everywhere else.
- An uploaded **SVG was served inline from our own origin** with its
  script intact — same-origin stored XSS.
- A failed voice session returned **202 Accepted**.
- Escalating an **already-escalated** case stranded it permanently.
- The **Insights page crashed** and the **Overview page crashed** on
  field-name drift between the API and the UI.
- Every **URL filter flag was inert** — the router JSON-quoted the value
  and the reader never matched.
- The **Reports detail tables were permanently empty**.
- The **category donut** showed a blank 100% wedge.
- A **served build called the wrong backend** on any port but 8000.
- A real mobile number was **committed in a tracked doc** (redacted;
  still in three earlier commits).
- **The two money sources disagreed** on 29 of 60 archival cases, by up
  to 3.4×. Resolved — see below.
- **Four CLI commands crashed against a real database** (`no such table:
  cost_entries`) because only the FastAPI lifespan called `create_all()`.
- **The production database was missing all eight archival indexes**, so
  `WHERE archive_batch_id IS NULL` — the leading filter in nearly every
  analytics query — was a full table scan.
- **`_add_missing_columns` silently produced a wrong column** for a
  `nullable=False` + `server_default` addition; it now refuses loudly.
- **Message attachments were unopenable** (`/documents/undefined/content`).
- **Contractor work history rendered archival cases as live tickets.**
- **A dead invalidation key** meant Reports never refreshed after a cost
  was recorded.
- **There was no navigation at all below 1024px** — on a tablet every
  destination but the current one was unreachable.
- **The test suite read the developer's untracked `.env`**, so a result
  said more about one machine than about the code. This machine's `.env`
  sets `DEMO_SLOT_OFFSET_DAYS=1`, which combined with a tenant window
  that started a day late to fail 22 tests — but only after 09:00 UTC,
  and never on a fresh clone. Green every morning, red every afternoon.
- **A fresh clone got CORS failures from the only frontend served**: the
  default allow-list had `:5173`, the dev server binds `:5174`. Invisible
  here because the local `.env` had been fixed by hand.
- **Every unmatched `/api` path returned 200 with an HTML body** on
  Windows: Starlette hands the static mount a path already through
  `os.path.normpath`, so `/api/v1/x` arrived as `api\v1\x` and the
  `startswith("api/")` passthrough test matched nothing. A client would
  have parsed markup as JSON and seen success. Separators are normalised
  now, and the SPA deep-link fallback no longer silently depends on the
  `dist/404.html` copy either — both pinned by
  `tests/test_audit_regressions.py` section 16; see `docs/26`.

### Known broken or incomplete

Everything below survived the fix pass, and each row survived it for a
stated reason rather than by being missed. Struck rows are resolved and
kept for the record, because `docs/audit/` refers to them by number.
The four reasons, and which rows they cover:

- **Needs a product decision, not a patch** — rows 1 and 7. See §7.2
  and §7.5. Row 1 now has a researched recommendation attached; §7.2
  records it.
- **Needs infrastructure this build does not have** — rows 3, 16 and the
  live-call gap in "Never verified". An email/SMS transport and a real
  phone call both require outbound contact, which §4 forbids for this
  whole session. Writing an untestable transport is worse than not
  having one.
- **Correct but incomplete, and the incompleteness is now written down**
  — rows 5, 8, 9, 10, 11, 14, 22. Each needs real design work (a
  table-rebuild migration, an idempotency scheme, an error-envelope
  contract across ~30 routes, a job retention policy) that is a task of
  its own rather than a one-line fix.
- **Low value against the cost** — rows 6, 15, 18, 20.

If any of these should have been fixed instead of recorded, that is a
scope call to make explicitly — the work is scoped in §6.


| # | Issue | Severity | Where |
| --- | --- | --- | --- |
| 1 | `MockBookingConnector` invents contractor availability. CLAUDE.md prohibits it outright. The coordinator's `SCHEDULE_VISIT` still books against fabricated slots. The UI now labels them "Simulated booking". | **HIGH** | `integrations/booking.py` |
| ~~2~~ | ~~Two money sources disagree.~~ **Resolved**: quoted is now reconciled per work order at read time — the cost ledger if entries exist, otherwise the work order's own quote. Never globally, so nothing double counts. Five reads of the same scope now return one figure; all 60 archival cases match. | — | `analytics.reconciled_quotes` |
| 3 | No email or SMS transport. Outward messages persist as drafts and say so. | **HIGH** | `api/messaging.py` |
| ~~4~~ | ~~Alembic is behind and produces a broken schema.~~ **Resolved by decision**: the chain is frozen. `env.py` now refuses to run without `REPAIRFLOW_ALLOW_ALEMBIC=1`. `create_all()` plus the additive column/index passes is the real bootstrap and now says so out loud, rather than leaving revisions that look authoritative and are not. | — | `alembic/env.py` |
| 5 | Enum CHECK constraints: `enum_column()` now passes `create_constraint=True`, but **this only protects tables created from now on**. The existing database gains nothing; retrofitting needs a table-rebuild migration, which was not attempted. | **MEDIUM** | `models.py` |
| 6 | 22 of 87 archival work orders are COMPLETED with no backing appointment; one has `created_at` after its case closed. Reproduced exactly on 2026-09-20 against a fresh `--apply`. The archive's own `no_open_or_pending_work` check reads the status enum only, so it cannot catch this. **This describes the dataset `python -m app.archive --apply` generates, not `backend/data/repairflow.db`, which currently holds zero archival rows.** | **MEDIUM** | `archive/dataset.py` |
| 7 | Archival seasonality is flat: measured 3–7 cases a month across all twelve, and roofing peaks in **July**, which is backwards for storm damage. Charts look synthetic on inspection. Same caveat as row 6 — this is the generated dataset, not the live database. | **MEDIUM** | `archive/dataset.py` |
| 8 | Property `/history` and `/stats` include archival cases with no disclosure field and no opt-out. | **MEDIUM** | `api/cases.py` |
| 9 | A late reopen (RESOLVED → ESCALATED → resumed) reports a stale `resolution_hours` — 48h reported against 2,376h true. | **MEDIUM** | `analytics.py` |
| 10 | Error envelopes are inconsistent: `DomainError` and FastAPI's `RequestValidationError` produce different shapes across ~30 routes. | **MEDIUM** | `api/errors.py` |
| 11 | No idempotency key on case creation — a double-submit creates two cases. | **MEDIUM** | `api/cases.py` |
| ~~12~~ | ~~Upload cap runs after the body is spooled.~~ **Resolved**: `MaxBodySizeMiddleware` rejects an over-sized `Content-Length` before a byte is read, and counts chunked bodies as they stream so omitting the header does not bypass it. It sits inside CORS on purpose, so a 413 still carries the headers a browser needs to read the status. | — | `app/middleware.py` |
| ~~13~~ | ~~No CORS guardrail against a wildcard with credentials.~~ **Resolved**: `Settings` refuses to construct on that combination, so it cannot be reached from configuration. The wildcard remains available with `CORS_ALLOW_CREDENTIALS=false`. The default allow-list also gained `:5174` — the only dev port actually served — which it had been missing. | — | `app/config.py` |
| 14 | `vulnerability_concern` is collected at intake and never read by any policy function, so docs/19's approval requirement for it is unenforced. | **MEDIUM** | `domain/policy.py` |
| 15 | Reports filters are not in the URL, so a filtered report is not linkable. | **LOW** | `routes/reports.index.tsx` |
| 16 | No browser voice panel. The original was a disabled placeholder; there was nothing to port. | **LOW** | — |
| ~~17~~ | ~~`docs/18`, `docs/04` and `docs/20` carry no superseded banner.~~ **Resolved**: all three were bannered in commit `5b2a07f`, as were `docs/16` and `docs/17`. This row was stale, not outstanding. | — | `docs/` |
| 18 | No frontend test suite at all, and no runner configured. | **MEDIUM** | — |
| ~~19~~ | ~~Three critical invariants have no test.~~ **Resolved**: `tests/test_audit_regressions.py` covers all three plus twelve more. Every one was proven to fail when its fix is reverted — a test that passes both ways guards nothing. |  — | `tests/test_audit_regressions.py` |
| 20 | Every page load produces a React hydration mismatch (error #418). React recovers by client-rendering, so it is cosmetic, but it is noise and can flicker. | **LOW** | prerendered shell |
| 22 | **The `jobs` table has no retention and holds 5,601 dead `FETCH_RECORDING` rows** — 5,618 jobs for 14 cases. They are the wreckage of the unbounded reconciliation sweep, each a distinct row with a timestamped dedupe key, all `DONE`. The sweep is bounded now (`RECONCILE_MAX_ATTEMPTS = 40`, counted by key prefix, so it fires correctly), but nothing ever deletes a finished job and no retention command exists. Harmless functionally; badly misleading to anyone who inspects the database. | **MEDIUM** | `orchestration/worker.py` |
| ~~21~~ | ~~Upload size cap runs after body spooling.~~ **Duplicate of row 12** — recorded twice by two different audits. Kept struck so the numbering in `docs/audit/` still resolves. |  — | — |

### Never verified

- **A real phone call.** Deliberate — see §4. The single biggest gap
  between "verified" and "known to work".
- **Real audio, a real signed webhook delivery.** `ELEVENLABS_WEBHOOK_SECRET`
  is empty and needs a reachable HTTPS `PUBLIC_BASE_URL` first.
- **A side-by-side pixel diff against the `liza.UI2` reference** — the
  reference cannot be run (no on-disk checkout, and the committed branch
  is missing the button primitive it needs to start).
- **Narrow-width layout.** Reasoned about, not measured.

### One thing the docs got wrong

The real database holds three `provenance=LIVE` communications. Two are
OUTBOUND and `FAILED`, with real
conversation IDs, empty transcripts and `recording.status=FAILED`
(`getaddrinfo failed` — a DNS error). A live call **was attempted and
failed**. The README, `docs/26` #20 and the migration handoff all frame
the live-voice gap purely as a deliberate never-attempted scope decision.
That is incomplete, and this document is the correction.

---

## 6. Outstanding work, in order

**Before this is exposed to any network**

1. Set `OPERATOR_AUTH_ENABLED=true`. It is currently `false` in the local
   `.env` *at the same time* as `OUTBOUND_CALLS_ENABLED=true` with one
   real number allowlisted. Off it, every route accepts any unauthenticated
   request, read and write, including voice session control.
2. HTTP Basic over plain HTTP is only defensible on localhost. Terminate
   TLS, or do not expose it.
3. ~~Decide the money-source question.~~ **Done** (§7.1, 2026-09-20):
   reconciled per work order at read time. Reporting now agrees across
   all five read paths.

**Correctness, highest value first**

4. Replace `MockBookingConnector`, or route all scheduling through the
   human-recorded reschedule path (§7).
5. ~~Bring Alembic current, or make it fail loudly.~~ **Done** (§7.4,
   2026-09-20): it now fails loudly. The chain is frozen behind
   `REPAIRFLOW_ALLOW_ALEMBIC=1`; `create_all()` is the real bootstrap.
6. Fix the archival dataset's orphaned completed work orders and flat
   seasonality.
7. Add `include_archived` + a disclosure field to property history/stats.
8. Recompute `resolution_hours` after a reopen.
9. Enforce `vulnerability_concern` in policy, or remove it from intake.
10. Normalise the error envelope across all routes.

**Then**

11. A frontend test suite — start with the search-param readers, the
    insights normaliser, largest-remainder, and pence parsing.
12. URL-backed Reports filters.
13. ~~Banner `docs/18`, `docs/04` and `docs/20` as superseded.~~ **Done**
    already — see row 17. This entry was stale when written.

---

## 7. Decisions that need a human

**1. ~~Which money source wins?~~ — decided 2026-09-20.** Reconcile
per work order at read time: a work order's quoted figure is its cost-
ledger QUOTE entries if any exist, otherwise its own `quote_pence`. Per
work order, never globally, so nothing double counts. Chosen over
"ledger only, backfill once" because the write path that sets
`quote_pence` still exists, so a one-time backfill would regress on the
next work order created; and over "two homes, never summed" because
QUOTE ledger rows a human has already logged would be orphaned. It needs
no migration and is correct both for the cases that have no cost entries
(all of the real ones) and for those that have both. Recorded in
`docs/26` entry 31; the reasoning and the proof are in
`docs/audit/06_analytics_metrics.md`.

**Still open here:** nothing in the UI yet distinguishes a figure that
came from the ledger from one estimated off a work-order quote. Both are
"quoted", but one is a real logged document and the other is an
estimate. Worth an indicator.

**2. What replaces the mock booking connector?** Either a real provider
integration, or make the human-recorded path (`POST
/appointments/{id}/reschedule`) the only way an appointment is created,
and have the coordinator propose a time for a human to arrange rather
than book one itself. The second is smaller and more honest; the first is
the product you probably want eventually.

**3. Clean the production database, or keep it?** `backend/data/repairflow.db`
still holds the nine scripted demo cases alongside five real ones with
genuine call history. `python -m app.legacy_demo_purge --dry-run` shows
exactly what would go. It has not been run.

**4. ~~Is Alembic alive?~~ — decided 2026-09-20: no.** The chain is
frozen behind `REPAIRFLOW_ALLOW_ALEMBIC=1` and refuses to run otherwise.
`create_all()` plus the additive column and index passes is the real
bootstrap. Revisit only if this ever needs a destructive migration —
renaming a column, retyping one, or adding the enum CHECK constraints to
existing tables — none of which the additive helper can do.

**5. How real does the archive need to look?** It is internally
consistent and passes 14 checks, but the cost distributions and
seasonality are flat enough to read as synthetic. That may be fine for a
sample dataset, or it may undermine the point of having one.
