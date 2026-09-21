# Fixi — complete application state

**What this is.** One document covering everything the application has:
what exists, what works, what does not, what is left to fix, and the
decisions still open. Written 2026-09-20 after a full migration from the
hackathon build plus a twelve-part audit sweep.

**How to read it.** §1–§4 describe the system. §5 is the honest verdict
per area. §6 is the outstanding work, ranked. §7 is what needs a human
decision. Nothing in here is aspirational — where something is unverified
it says so.

Companion files: `docs/audit/` (the twelve raw audit reports, with
`file:line` evidence), `docs/UI2_IMPLEMENTATION_HANDOFF.md` (what the
migration did), `docs/UI2_TODO.md` (the queued work), `docs/26` (the
running corrections log).

---

## 0. Picking this up on another machine

Everything you need is tracked in git. Nothing else carries over.

**Read, in this order:** this document; then `README.md` for what it is
and how to run it; then `CLAUDE.md` if you are an AI agent, which points
back here. The numbered `docs/00`–`docs/26` are the original
specification — useful for *why* a contract is shaped the way it is, but
several are superseded and say so at the top. Where a numbered spec and
the code disagree, the code is usually right. `docs/26`'s newest entries
are the authority on every deliberate deviation.

**What a clone does not give you**, because `.gitignore` excludes it:

| Missing | Consequence | What to do |
|---|---|---|
| `backend/data/` | **No database.** No cases, no call history. | The app creates and migrates one on first boot. `python -m app.seed` adds reference data; `python -m app.archive --apply` adds 60 closed sample cases; `python -m app.sample_operations --apply` adds 25 open/recently-closed operational cases so the dashboard counters are not all zero. |
| `frontend-fixi/dist/` | The SPA is **not built**, and `main.py` only mounts it `if FRONTEND_DIST.is_dir()` — checked once at import. | `npm ci && npm run build` **before** starting the backend. Building afterwards does not fix a running process; restart it. |
| `backend/.venv/`, `node_modules/` | Nothing installed. | `uv sync --frozen`, `npm ci`. `uv` is the one prerequisite this repo does not install for you. |
| `backend/.env` | No provider keys. Operator auth defaults **on**. | Optional — every setting has a working default. Sign in with `operator` / `repairflow-demo`. |

The full sequence, verified from a bare checkout on 2026-09-20, is in
README's *Running locally, from a fresh clone*. The 214-test backend suite
passes on a clone with no `.env` and no database.

**The existing data does not travel.** `backend/data/repairflow.db` on
the old machine holds 14 real cases and the only three `LIVE`
communications that exist, including two genuine failed call attempts.
Copying that file by hand is the only way to bring them; a clone starts
empty, which is a supported state.

---

## 0b. What changed on 2026-09-21

The rest of this document was written on 2026-09-20. A later session
drove the application in a real browser and changed what is true. Read
this section before trusting anything below it; `docs/26`'s
2026-09-21 entry has the full reasoning.

**Operator sign-in no longer exists.** `OPERATOR_AUTH_ENABLED` now
defaults **False**, `LoginGate.tsx` and `use-auth.ts` are deleted, and
the API is open. This was not a preference: with auth on (the old
default, and what a fresh clone got), `require_operator` returned
`401 WWW-Authenticate: Basic`, Chrome hijacked the response to raise its
own credentials dialog, the SPA's auth probe never settled, and **the
documented bootstrap rendered a permanently blank page**. The owner
elected to remove the login rather than repair it.

> **This build must stay on localhost.** CLAUDE.md forbids public
> unauthenticated write endpoints and this build now has them. §6's
> "set `OPERATOR_AUTH_ENABLED=true` before exposing this to a network"
> is no longer sufficient advice: turning the flag on now 401s every
> call with no sign-in form to recover through. Restore a form first —
> `frontend-fixi/src/lib/auth-context.ts` is the single seam.

**Gemini is dead and the coordinator is on its fixture.** The key in
`backend/.env` returns `API_KEY_INVALID`. `ConservativeFixtureCoordinator`
hardcodes triage to `Trade.OTHER` and then waits, so end-to-end
autonomy cannot be demonstrated until a working key exists. ElevenLabs
was first assessed as a substitute and rejected; that judgement has since
been **narrowed** -- it holds for the TTS/STT product, but its Agents
platform brokers an LLM and scored 11/11 on the coordinator contract in a
sandbox. See the re-evaluation below and in docs/26.

**Now surfaced in the UI, having been built but invisible:** global
search (`GET /search`, previously zero callers), the coordinator's
decision history (`GET /cases/{id}/runs`, previously zero callers — now
an **Agent** tab), `approved_contractors` and `policy_snapshot`
(previously typed `unknown[]` and discarded), and recording-failure
reasons with a working retry.

**A "waiting" state exists for the first time.** A `Wait` with no timer
writes nothing durable, so a case waiting on a contractor was
indistinguishable from an abandoned one. `AgentActivity` derives the
state from real fields and admits when it cannot tell.

**The workspace has an operational workload.** Two idempotent
generators fill what an empty database cannot show: `app.sample_operations`
writes 25 operational cases across every status (6 resolved this week, 6
resolved 9-27 days back, 4 awaiting confirmation, 3 escalated, 4 active
with a visit to come, 2 cancelled), and `app.backfill_case_history` gives
pre-existing event-less cases a log derived from their own rows. The
dashboard now reads 39 total / 12 active / 4 awaiting / 3 escalated / 6
resolved this week / 59.8h average, where every one of those was 0 or
null. Both generators refuse to touch a case carrying LIVE provenance,
write `Provenance.SIMULATED` on everything and enqueue no jobs. Run
`--validate` on either; see docs/26.

**Four defects were found by exercising the running app, not by reading
it** -- a 500 on `GET /cases/{id}` for every case with a contractor
report, a 500 on `GET /cases/{id}/runs` for every backfilled case, an
`agent_active` flag stuck true, and a report table labelled "Quoted
Pence" above values in pounds. All fixed, three with regression tests
proven to fail when reverted. docs/26 has the table.

**ElevenLabs was re-evaluated as the reasoning model and scored 11/11**
on the coordinator contract, including both call-placing actions and a
prompt-injection report it refused to act on. It is an evaluation only:
no backend code changed, and nothing could dial (no phone number, client
-only tools, tool calls skipped in test mode). The earlier "cannot
serve" conclusion applies to the TTS/STT product, not the Agents
platform. See docs/26.

**The Agent tab draws the coordinator's reasoning as a graph.**
`components/fixi/CaseFlow.tsx` (React Flow, over the pure
`lib/case-flow.ts`) lays a case out one column per coordination round,
with triggers on the top lane, that round's decision below them and its
effects underneath — so position means something and an operator can see
at a glance what woke the agent, what it chose and what changed. It
updates live while the tab is focused; React Query pauses polling in a
background tab. The archival cases have real histories to draw (730
events, 439 runs) rather than the single "Completed" node they showed
before. See docs/26.

**Data.** Contractor roster 6 → 18, every trade covering BS1–BS8 (trade
`OTHER` previously had none, so any non-roof/scaffold/plumbing/
electrical ticket dead-ended at escalation). The archive now generates
107 contractor reports, one per finished visit, with a 15th validation
check. The four operational properties gained photographs and types.

**Corrections to figures below:** "19 routers" was 18 (the extra was the
untracked `api/demo.py`, now deleted); the regression file holds 43
cases from 35 functions, not "24 tests / 32 cases"; all eight archival
indexes exist. Also note `repair_cases.category` is NULL on every case
in `backend/data/repairflow.db` — the backfill command has never been
run against it — and no "DNS" text exists anywhere in that database, so
the stated cause of the two failed LIVE calls is unsourced; the stored
reason is `"reconciliation abandoned"` after 1,806 and 3,795 attempts.

**Row 10 (error envelopes) is half closed.** The backend still emits
three shapes, but the client now parses all three, so a `DomainError` no
longer reaches the operator as a raw JSON blob. The backend-side
normalisation is still outstanding.

A thirteenth audit, `docs/audit/13_full_stack_sweep.md`, records the
full-repository sweep that produced most of the above.

---

## 0c. The UI pass of 2026-09-21

A second session on the same day rebuilt the layout, type scale and
motion of the frontend. `docs/27_UI_LAYOUT_AND_MOTION_PLAN.md` is the
audit and, in its section 9, the record of what landed and what the
numbers came out at. The short version:

- **One page width** (`--container-page`, 110rem) replaces six
  hand-written values; the ticket page, which had no container, now has
  one. Its chrome above the first card went 526px -> 321px.
- **One type scale**, seven sizes, an 11px floor. There were seventeen
  sizes and fifty-one usages below 11px, down to 8px.
- **Motion** where it carries information: route transitions that say
  which direction you went, content-shaped loading skeletons in place of
  twelve bare "Loading..." strings, KPI figures that count up and flash
  when they change under you, and an agent-activity ring gated on the
  same boolean as the indicator dot so it cannot claim work that is not
  happening. All of it behind a global `prefers-reduced-motion` guard.
- **Dark mode was deleted, not disabled.** The `.dark` block defined 32
  of the 55 tokens `:root` does — missing every status and timeline
  colour — and nothing in the app ever set the class, so it had never
  rendered. `styles.css` carries the recovery command and the reasoning.

**Two things to know before changing styles.**

First: `cn()` in `lib/utils.ts` is an *extended* tailwind-merge. It has
to be. Plain tailwind-merge treats any unrecognised `text-<word>` as a
colour, so it silently deleted all six custom font-size classes whenever
a text colour appeared in the same call — no error, no build failure,
the class just absent from the DOM and the element back on the 16px
browser default. **A new token in `@theme` must also be registered in
`utils.ts`,** or it will not survive `cn()`. `lib/utils.test.ts` guards
this.

Second: `frontend-fixi/dist` must be rebuilt for any of this to be
visible. The backend serves the built bundle, not the source.

## 0d. A clone now reproduces this workspace exactly

`data/` is gitignored, so a clone has no database -- that has not
changed, and the SQLite file is still never committed. What changed on
2026-09-21 is that everything *in* it is now reproducible from the
repository:

```
uv run python -m app.bootstrap
```

Five idempotent steps, then the validators, then the counts to check
against: **12 properties, 12 tenants, 24 contractors, 99 cases (39
operational, 60 archival)**. Verified by diffing a freshly bootstrapped
database against the source machine's: every one of the eighteen
content tables matches row for row, and the case ids and case numbers
are identical sets.

Three of the five steps already existed. The two new pieces:

- **`app.intake_fixture`** holds the fourteen cases that were created by
  *using* the application rather than by a generator -- including the
  eight genuine Gemini coordinator runs -- captured row-for-row into a
  committed `dataset.json` and replayed on import. They could not be
  regenerated; they are a record of what happened.
- **`app.bootstrap`** runs everything in the one order that works and
  prints the counts. `--check` reports without writing.

**Order is load-bearing.** `app.intake_fixture` must run before both
case generators: its cases carry the numbers they were originally issued
(1-14) while the generators allocate `MAX(case_number) + 1`, so running
it last collides on `uq_case_number` for all fourteen. Numbering
reproduces as intake 1-14, archive 15-74, operations 75-99.

**Two things are deliberately not identical, and both are correct.**
Generated cases are dated relative to bootstrap time, so a clone made
next month still has upcoming visits in the future rather than a stale
workspace; only the derived week-over-week delta percentages differ as a
result. And `jobs` is the worker's retry queue -- runtime state, not
content -- so it is never captured. (The source machine had 5,618 rows
there, almost all accumulated retries against the dead Gemini key.)

**This repository is public.** The exporter refuses to write a dataset
containing a non-placeholder phone number, an email address or anything
shaped like an API key, and never exports `tenants`, `properties` or
`contractors` at all -- `app.seed` creates those deterministically, with
placeholder numbers, before the import runs. That is what keeps the one
value that has ever qualified (a real mobile, hand-edited into a single
`tenants` row on one machine) structurally out of scope rather than
merely filtered. `tests/test_intake_fixture.py` re-runs the same scan
against the committed file.

The five real call recordings in `backend/data/recordings/` are
unreferenced orphans -- no `communications` row carries a `media_path`,
and the three `LIVE` rows have empty transcripts -- so nothing in the
captured dataset points at audio, and none of it ships.

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
`/healthz`); **25** database tables; **232** backend tests and **62**
frontend tests.

---

## 2. What exists

### Backend

| Area | Modules | State |
| --- | --- | --- |
| Domain engine | `domain/{services,transitions,policy,dependencies,errors}.py` | Complete. Event-sourced: append-only `CaseEvent`, derived `CaseSnapshot`, typed action ledger. |
| Orchestration | `orchestration/{dispatcher,worker,executor,dedupe}.py` | Complete. Durable `JobModel` queue, leases, idempotency keys, one proposal per wake. |
| Agent | `agents/{coordinator,read_tools,instructions,dependencies}.py` | Complete. Gemini via Pydantic AI, scoped read-only tools, bounded retries, redacted snapshot. |
| Integrations | `integrations/{elevenlabs,tavily,booking,no_contact}.py` | ElevenLabs and Tavily complete; **booking is a mock that invents availability** (§5). |
| API | `api/` — 18 routers, 72 routes | Complete. The "19" counted the untracked `api/demo.py`, deleted 2026-09-21. |
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
| **The fixes are pinned** | `test_audit_regressions.py` collects 43 cases from 35 functions as of 2026-09-21 (the "24 tests / 32 cases" figure was written earlier and undercounts), each proven to fail when its fix is reverted. |
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
- ~~**The production database was missing all eight archival indexes.**~~
  **Stale — re-measured 2026-09-21: all eight exist.** Kept because
  `docs/audit/` refers to it.
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

- **Needs a product decision, not a patch** — row 1. See §7.2. Row 1 now has a researched recommendation attached; §7.2
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
- **Low value against the cost** — row 20.

If any of these should have been fixed instead of recorded, that is a
scope call to make explicitly — the work is scoped in §6.


| # | Issue | Severity | Where |
| --- | --- | --- | --- |
| 1 | `MockBookingConnector` still invents contractor availability, which CLAUDE.md prohibits outright. **Narrowed 2026-09-20**: bookings are no longer written `CONFIRMED` (nothing acknowledged them) and listing slots no longer persists rows through a model-visible read tool. The fabrication of the times themselves remains. A worked replacement plan is in §7.2. | **HIGH** | `integrations/booking.py` |
| ~~2~~ | ~~Two money sources disagree.~~ **Resolved**: quoted is now reconciled per work order at read time — the cost ledger if entries exist, otherwise the work order's own quote. Never globally, so nothing double counts. Five reads of the same scope now return one figure; all 60 archival cases match. | — | `analytics.reconciled_quotes` |
| 3 | No email or SMS transport. Outward messages persist as drafts and say so. | **HIGH** | `api/messaging.py` |
| ~~4~~ | ~~Alembic is behind and produces a broken schema.~~ **Resolved by decision**: the chain is frozen. `env.py` now refuses to run without `REPAIRFLOW_ALLOW_ALEMBIC=1`. `create_all()` plus the additive column/index passes is the real bootstrap and now says so out loud, rather than leaving revisions that look authoritative and are not. | — | `alembic/env.py` |
| 5 | Enum CHECK constraints: `enum_column()` now passes `create_constraint=True`, but **this only protects tables created from now on**. The existing database gains nothing; retrofitting needs a table-rebuild migration, which was not attempted. | **MEDIUM** | `models.py` |
| ~~6~~ | ~~22 of 87 archival work orders COMPLETED with no appointment.~~ **Resolved**: the generator drew 1–2 appointments regardless of how many work orders a case had. It now produces one attendance per work order plus an optional retry, so a completed repair always has a visit behind it. Regenerated and measured: 0 orphans, 0 work orders created after closure, 14/14 validation checks still pass. | — | `archive/dataset.py` |
| ~~7~~ | ~~Archival seasonality is flat, and roofing peaked in July.~~ **Resolved**: reporting dates are now drawn from per-trade monthly weights (the obvious physical seasons, not fitted data). Measured after regeneration: 2 cases in May against 10 in December, and roofing Nov–Feb 9 against May–Aug 6. | — | `archive/dataset.py` |
| ~~8~~ | ~~Property history/stats include archival cases undisclosed.~~ **Resolved**: both take `include_archived` (default true — the blending is wanted), both return `includes_archived_history` and `archived_case_count`, and each history row carries `is_archived`. | — | `api/cases.py` |
| ~~9~~ | ~~A late reopen reports stale `resolution_hours`.~~ **Was already correct** — `_terminal_event_at_by_case` takes MAX. Probed directly: 2,376h reported, not 48h. The row described a bug that did not exist; now pinned by a test so it cannot appear. | — | `analytics.py` |
| 10 | Error envelopes are inconsistent: `DomainError` and FastAPI's `RequestValidationError` produce different shapes across ~30 routes, and `require_operator` adds a third on auth failure. **Half closed 2026-09-21**: the client now parses all three, so a `DomainError` no longer reaches the operator as a raw JSON blob in a toast, and an unmodelled crash returns the typed envelope with a `correlation_id` instead of plain-text "Internal Server Error". The backend still emits three shapes. | **MEDIUM** | `api/errors.py`, `frontend-fixi/src/api/client.ts` |
| ~~11~~ | ~~No idempotency on case creation.~~ **Resolved**: an optional `Idempotency-Key` header derives the intake communication id deterministically, routing a repeat into `submit_intake`'s existing per-communication NOOP path. Without the header behaviour is unchanged, because two genuine reports of one fault must not merge. | — | `api/cases.py` |
| ~~12~~ | ~~Upload cap runs after the body is spooled.~~ **Resolved**: `MaxBodySizeMiddleware` rejects an over-sized `Content-Length` before a byte is read, and counts chunked bodies as they stream so omitting the header does not bypass it. It sits inside CORS on purpose, so a 413 still carries the headers a browser needs to read the status. | — | `app/middleware.py` |
| ~~13~~ | ~~No CORS guardrail against a wildcard with credentials.~~ **Resolved**: `Settings` refuses to construct on that combination, so it cannot be reached from configuration. The wildcard remains available with `CORS_ALLOW_CREDENTIALS=false`. The default allow-list also gained `:5174` — the only dev port actually served — which it had been missing. | — | `app/config.py` |
| ~~14~~ | ~~`vulnerability_concern` is unenforced.~~ **Resolved**: it now forces the approval gate before any visit is booked, which is what docs/19's "only with explicit reviewed plan" means. Deliberately not part of `is_hazard` — a hazard freezes the case, which would strand a repair that still needs doing. | — | `domain/policy.py` |
| ~~15~~ | ~~Reports filters are not in the URL.~~ **Resolved**: filters now read from and write to the URL, matching Insights and the directory pages. Note `validateSearch` is avoided app-wide — it reproducibly froze the renderer against the SPA-fallback hydration shell — so this uses the same `useRouterState` + `readParam` pattern the other pages do. | — | `routes/reports.index.tsx` |
| 16 | No browser voice panel. The original was a disabled placeholder; there was nothing to port. | **LOW** | — |
| ~~17~~ | ~~`docs/18`, `docs/04` and `docs/20` carry no superseded banner.~~ **Resolved**: all three were bannered in commit `5b2a07f`, as were `docs/16` and `docs/17`. This row was stale, not outstanding. | — | `docs/` |
| ~~18~~ | ~~No frontend test suite at all.~~ **Resolved**: Vitest, `npm test`, 62 tests over the pure logic most likely to break silently — the search-param readers (the reason every URL filter was once inert), the insights normaliser (the date-fns crash), largest-remainder rounding and pence parsing. Four were verified by deliberate breakage. | — | `frontend-fixi/` |
| ~~19~~ | ~~Three critical invariants have no test.~~ **Resolved**: `tests/test_audit_regressions.py` covers all three plus twelve more. Every one was proven to fail when its fix is reverted — a test that passes both ways guards nothing. |  — | `tests/test_audit_regressions.py` |
| 20 | Every page load produces a React hydration mismatch (error #418). React recovers by client-rendering, so it is cosmetic, but it is noise and can flicker. | **LOW** | prerendered shell |
| ~~22~~ | ~~The `jobs` table has no retention.~~ **Resolved**: `purge_finished_jobs` trims DONE rows past a week, hourly. Only DONE — a FAILED job is evidence until someone looks at it. The 5,601 dead rows already in `backend/data` will clear on the next worker run. Original finding: ~~the `jobs` table has no retention and holds 5,601 dead `FETCH_RECORDING` rows** — 5,618 jobs for 14 cases. They are the wreckage of the unbounded reconciliation sweep, each a distinct row with a timestamped dedupe key, all `DONE`. The sweep is bounded now (`RECONCILE_MAX_ATTEMPTS = 40`, counted by key prefix, so it fires correctly), but nothing ever deletes a finished job and no retention command exists. Harmless functionally; badly misleading to anyone who inspects the database. | **MEDIUM** | `orchestration/worker.py` |
| ~~21~~ | ~~Upload size cap runs after body spooling.~~ **Duplicate of row 12** — recorded twice by two different audits. Kept struck so the numbering in `docs/audit/` still resolves. |  — | — |

| ~~23~~ | ~~A model-visible read tool committed rows.~~ **Resolved**: `find_appointment_options` reached `_ensure_slots`, which added and flushed slot rows inside a committing scope — so the model asking what times were free wrote to the database, against CLAUDE.md's "model-visible tools are scoped reads". Listing is now pure; the executor validates a proposed slot against what the connector *would have offered* rather than against a stored row, and `book()` materialises the one slot it reserves. | — | `integrations/booking.py` |

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
6. ~~Fix the archival dataset's orphaned completed work orders and flat
   seasonality.~~ **Done** — see rows 6 and 7.
7. Add `include_archived` + a disclosure field to property history/stats.
8. Recompute `resolution_hours` after a reopen.
9. Enforce `vulnerability_concern` in policy, or remove it from intake.
10. Normalise the error envelope across all routes.

**Then**

11. ~~A frontend test suite.~~ **Done** — exactly those four areas.
12. ~~URL-backed Reports filters.~~ **Done**.
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

**2. What replaces the mock booking connector?** Still open, but
narrowed on 2026-09-20 and now backed by a worked plan, so a future
session does not have to re-derive it.

*Already done, and it was the part labelling could never fix.* The
connector no longer writes `CONFIRMED` — a status that asserted a
contractor acknowledgment that never happened — and listing candidate
slots no longer persists rows through a model-visible read tool. What
remains is the fabrication itself: `_ensure_slots` still generates times
from a date offset rather than any real calendar.

*The recommended full fix is human dispatch* — not a real provider
integration, which is out of scope while no outbound contact is
permitted. In outline:

- `ScheduleVisit` drops `slot_id`; the action names a work order, an
  approved contractor and which cited tenant-availability window to use.
- A deterministic `policy.suggested_visit_window(windows)` computes the
  time from the tenant's *real* stated availability. The model never
  picks a time, so nothing is invented.
- `SCHEDULE_VISIT` becomes a local executor write (`services.propose_visit`)
  rather than an external call: no connector, no availability lookup.
  This removes roughly 95 lines from `executor.py` (`_apply_schedule_result`
  and the Phase-B branch) and adds ~60 to `services.py`.
- `find_appointment_options` and its registration come out of
  `agents/read_tools.py` and `agents/coordinator.py`; the coordinator's
  instructions already say "do not invent availability", which today
  contradicts the tool it is handed.
- `MockBookingConnector` stays as unused reference code for the shape a
  real connector would take.

It needs no migration. `test_hero_path.py` needs about ten lines
changed, not a rewrite, because it asserts work-order status and
appointment counts rather than appointment status —
`propose_visit` still moves `READY → SCHEDULED` in one transaction.
`test_reliability_matrix.py`'s `_apply_schedule_result` test would be
deleted outright (the property it guards becomes structurally
impossible), and `test_external_action_never_strands_at_running` should
be retargeted at `DISCOVER_CONTRACTORS`, which is a genuine external
call. The three existing appointments stay as they are: they are honest
history of the retired path, and rewriting settled rows to match new
code would itself be a fabrication.

Rejected: keeping the connector with stronger labelling (already the
state of things, and it is the status claim rather than the label that
lies); and having it return no availability ever (leaves the machinery
wired in, and dead-ends every case at escalation).

**3. Clean the production database, or keep it?** `backend/data/repairflow.db`
still holds the nine scripted demo cases alongside five real ones with
genuine call history. `python -m app.legacy_demo_purge --dry-run` shows
exactly what would go. It has not been run.

Related, and now partly self-solving: that database also holds 5,601
dead `FETCH_RECORDING` job rows. The retention sweep added on
2026-09-20 will clear them on the next worker run against it — no
decision needed, but worth knowing before anyone inspects the file and
wonders what happened. Note the database itself does not travel to a
new machine (§0); if these fourteen cases matter, copy it by hand
before deciding.

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
