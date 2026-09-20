# UI2 full-application migration — handoff

Assignment: `prompts/UI2_FULL_APPLICATION_MIGRATION.md`. Worked 2026-09-20 in
one unattended session. Companion files: `docs/UI2_CHECKPOINT.md` (working
notes, carried-forward knowledge, inherited bugs),
`docs/UI2_INTERACTION_CHECKLIST.md` (every control, what backs it, how it
was verified) and **`docs/UI2_TODO.md`** (the queued follow-up work).

**Nothing was pushed, merged or deployed. No call, message or email was
sent. `liza.UI2` was not modified.**

---

## 1. What changed, and where

### The hackathon layer is gone (§3)

| Removed | Replaced by |
| --- | --- |
| `backend/app/api/demo.py` (replay, reset, hard delete, seed-refs, simulated observations) | deleted outright |
| `seed_demo_data()` in `main.py`'s lifespan | nothing seeds on boot; an empty database is a supported state |
| `_seed_demo_activity()` (~490 lines, 9 fictional cases) in `app/seed.py` | deleted; `python -m app.seed` remains as an opt-in sample portfolio of reference **records only** — no cases |
| "Play demo" button | removed |
| Hard "Delete ticket" | removed; `Cancel case` keeps the record |
| "Simulate an observation" | `RecordFieldUpdateDialog` → `POST /cases/{id}/field-updates` |
| `POST /demo/intake` behind "+ New Ticket" | `POST /cases` — operator-recorded intake, property **and** tenant required |

`python -m app.legacy_demo_purge --dry-run|--apply` removes exactly the nine
scripted cases an older build seeded, identified by recomputing their
deterministic `uuid5` ids. Real operator-created cases use random `uuid4`
and cannot collide with that set, so nothing genuine is at risk. **This has
not been run against `backend/data/repairflow.db`** — that is the owner's
call, and cases #1–#5 there carry real ElevenLabs conversations.

### New schema (additive only)

Tables `archive_batches`, `notes`, `documents`, `cost_entries`. Columns:
`properties.property_type/bedrooms/photo_key/archive_batch_id`,
`repair_cases.category/archive_batch_id/archived_closed_at`,
`tenants.archive_batch_id`, `contractors.archive_batch_id`, and on
`messages`: `channel`, `delivery_state`, `delivery_detail`, `queued_at`,
`delivered_at`, `read_at`, `attachments`, `communication_id`,
`archive_batch_id`.

`db.create_all()` gained `_add_missing_columns()`. `create_all` creates
missing *tables* but never alters an existing one, so a column added to a
model after a database was created was silently absent until a query
failed. It only ever ADDs nullable/defaulted columns and refuses anything
destructive.

### API: 26 routes → 58

New: `overview`, `insights` (+ `/insights/cases` drill-down), `reports`
(summary + `export.csv`), `search`, `properties`, `contractors`, `tenants`,
`documents`, `notes`, `costs`, `messaging`, `field_updates`, plus
`PATCH /cases/{id}` and `POST /appointments/{id}/reschedule`.

`backend/app/analytics.py` is the single source of every metric. Routers
are thin: they parse filters, call it, and shape the response. That is what
makes a chart, a total, a detail table and a CSV export of the same scope
reconcile — asserted by a test that compares the CSV totals against
`/reports/summary`.

### Frontend: 5 routes → 17, all eight sidebar destinations

`/` Overview · `/maintenance` · `/maintenance/tickets/$id/{-$section}` (9
tabs) · `/properties` · `/properties/$id/{index,history,details,documents,notes}`
· `/contractors` + `/contractors/$id` · `/tenants` + `/tenants/$id` ·
`/insights` · `/messages` + `/messages/$caseId` · `/reports`.

`main.py` now serves the SPA through `SpaStaticFiles`, which falls back to
`index.html` for unknown paths while leaving `/api`, `/webhooks` and
`/integrations` alone. Without it every deep link 404'd on hard refresh —
invisible while clicking around in-app, broken the moment anyone reloads or
opens a shared link.

---

## 2. The three rules that shaped most decisions

**Archival history is quarantined.** A row with a non-null
`archive_batch_id` is synthetic sample history. It is excluded from
`GET /cases`, `GET /metrics/dashboard`, `GET /overview`, the notification
feed and every current-workload count; it is included in historical
analytics only with `include_archived=true`, which sets
`includes_archived_history` and flags each row `is_archived` so the UI can
label the scope. Archival contractors are never APPROVED and carry no
contact reference; archival tenants are `contact_allowed = false` with no
phone or email. Two validation checks enforce exactly that, so the archive
can never be dialled.

**Saving is not sending.** Composing an Email or SMS message persists a
`DRAFT` with a `delivery_detail` explaining that no transport is
configured. The composer button reads "Save draft". Nothing displays as
sent, queued or delivered unless `delivery_state` says so.

**Recording is not confirming.** An operator rescheduling a visit produces
a `PENDING` appointment with `provider_booking_id = None` and
`connector = HUMAN`, plus an event naming who arranged it and with whom. An
operator writing a time into this system is not a contractor accepting it.

---

## 3. Commands

> **The backend that was running on :8000 has been stopped.** It was the
> pre-migration process, and `StaticFiles` reads `frontend-fixi/dist` from
> disk — which this work rebuilt. It was therefore serving the new
> frontend against an API that predates seven of its eight destinations:
> a half-dead app with no explanation. It was **not** restarted, because
> booting it runs the durable-job worker against the real database with
> live ElevenLabs credentials, and this was an unattended session. Start
> it yourself with the first command below when you want it back. Its
> queue was checked at the start of this session and had zero open jobs,
> so a restart will not dial anyone.


```bash
# Backend (from backend/)
uv run uvicorn app.main:app --port 8000
.venv/Scripts/python.exe -m pytest tests/ -q

# Optional data, both idempotent
python -m app.seed                     # sample portfolio (reference records only)
python -m app.archive --apply          # ~60 closed archival cases, 2021-2026
python -m app.archive --validate       # 13 integrity checks
python -m app.archive --status
python -m app.archive --remove         # removes exactly that batch
python -m app.legacy_demo_purge --dry-run

# Frontend (from frontend-fixi/)
rm -rf dist && npm run build           # FastAPI serves dist/ at /
npm run dev                            # hot reload on :5174

# End-to-end scenarios, against an isolated no-contact instance
FIXI_NO_CONTACT=1 OUTBOUND_CALLS_ENABLED=false OPERATOR_AUTH_ENABLED=false \
DATABASE_PATH=/tmp/verify.db DOCUMENTS_DIR=/tmp/verify_docs \
  python -m uvicorn app.main:app --port 8010
python scripts/verify_scenarios.py --base-url http://127.0.0.1:8010
```

Schema migration needs no separate step: `create_all()` plus
`_add_missing_columns()` brings an existing database up to date on boot.
Alembic revisions remain in `backend/alembic/versions/` for the record but
are not what runs.

---

## 4. Verification evidence

### Automated

| Check | Result |
| --- | --- |
| `pytest tests/ -q` | **152 passed**, 0 failed |
| `npx tsc --noEmit` | **0 errors** |
| `npx eslint .` | **0 errors**, 5 warnings (react-refresh / exhaustive-deps advisories) |
| `npm run build` | green; 17 routes, prerendered shell written |
| `python -m app.archive --apply` | 600 rows: 8 properties, 8 tenants, 6 contractors, 60 cases, 87 work orders, 75 appointments, 112 costs, 55 notes, 42 messages, 12 documents (+12 real files on disk) |
| `python -m app.archive --validate` | **13/13 checks pass** |
| second `--apply` | "already imported; nothing written" |
| `--remove` then `--validate` | 601 rows and all 12 files deleted; planted non-archival control rows untouched; `PRAGMA foreign_key_check` clean |
| `scripts/verify_scenarios.py` | **41/41 checks pass** against an isolated no-contact instance |

Scenario 7 (reschedule) reports **SKIPPED** rather than passing: an
appointment requires an approved `SCHEDULE_VISIT` action, which that
script does not drive. The reschedule path is covered by
`backend/tests/test_hero_path.py` and the endpoint's own tests.

### In a browser, against a running isolated instance

Served build on `:8010`, `FIXI_NO_CONTACT=1`, isolated database, at a
1528×706 viewport.

- All eight destinations return 200 on a **hard load** (deep-link fallback
  works — before `SpaStaticFiles`, every one 404'd on refresh).
- **Overview** — eight nav items, real counts, metric cards linking to
  their destinations, needs-attention and recent-activity rows linking to
  real cases.
- **Insights** — five range presets, custom from/to, property and category
  filters, archival toggle. With the archive imported: 20 months of volume,
  three years of spend (quoted and actual shown separately), a category
  donut whose displayed percentages sum to exactly 100, recurrence rows.
  Every bar, legend row and bucket is a labelled `<button>` that opens the
  supporting cases.
- **Messages** — the thread shows an "Internal note" pill on one message
  and "Draft — not sent" on the other, with the API's own explanation
  ("No delivery transport is configured for EMAIL…") printed underneath.
  The composer's button reads "Add internal note" / "Save draft" by
  channel. Nothing renders as sent.
- **Reports** — presets, filters, archival toggle, "Report window" and
  "Generated on" lines, summary tiles, Export CSV and Print / Save as PDF.
- **Contractors** with archived shown — six rows, each labelled
  "(archived, FIXTURE)", every one `Pending` with "Not assignable", and a
  heading explaining that only approved contractors can be assigned.
- **Properties** — 1 operational, 9 with archival included; the property
  with no `photo_key` renders a placeholder tile, not another building's
  photograph.
- **Property history (14 King Street)** — the reference screen reproduced:
  photo, "Sample history" pill, facts row, four tabs, KPI row, donut,
  annual-spend bars, recurring-issues panel, drill-down chips, and a
  sortable, selectable history table with row chevrons into each case.
- **Ticket detail** — number and title, urgency badge, address with copy,
  Share / Edit / kebab, status control, the five-step progression derived
  from real state (Reported done, Diagnosing current), "Record an update",
  nine working tabs.

### Against a copy of the real database

Every other check in this document ran against a database created fresh,
where the migration path is a no-op — so it was never exercised at all.
`backend/data/repairflow.db` was **copied** and the copy migrated and
driven. That rehearsal found two things:

- **Three NOT NULL columns were left NULL on existing rows.** `create_all`
  adds the column; a SQLAlchemy `default=` only runs at INSERT time. The
  five message rows already in that database came back with
  `channel`/`delivery_state`/`attachments` NULL, which the Messages screen
  declares non-optional — a 500 on first open, on the one database that
  matters. `_add_missing_columns()` now backfills a column's default in
  the same transaction as the ALTER. **Regression test added and confirmed
  to fail without the fix.**
- **`--validate`'s `no_jobs` check counted every job in the database**,
  not just jobs against the imported batch. The real database holds 5,508
  legitimate job rows, so a perfectly good import reported 12/13. Scoped
  to the batch; now 13/13 there too.

After those fixes, on the migrated copy: 18 columns added and backfilled,
all eleven API surfaces return 200, all four real cases load with their
events, messages and costs, and the two genuine LIVE ElevenLabs
communications are intact. `--apply` allocates case numbers from the live
MAX, so the archive's 60 cases became #15–#74 with no collision against
the existing #1–#14; `--remove` then left exactly those 14 cases and 5
messages with no orphans.

### Visual comparison against the reference

**Not performed as a side-by-side.** The `liza.UI2` reference could not be
run: there is no on-disk checkout of that branch, `:5175` was not serving,
and the assignment itself notes the committed branch is missing
`src/components/ui/button.tsx`, which it needs to start. Fidelity was
therefore worked from the reference **source** — `styles.css` (already the
token set this app uses, verified by diff), `AppShell.tsx`,
`UtilityBar.tsx`, `Badge.tsx`, `fixi-data.ts` and the three route files —
plus screenshots of the implementation. A real pixel comparison remains
worth doing once that workspace is available.

---

## 5. Production integrations and the no-contact boundary (§12)

**Preserved, untouched:** `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`,
`ELEVENLABS_PHONE_NUMBER_ID` and the Twilio routing behind them are
unchanged. No credential was rotated. The live agent's configuration was
not modified — the ElevenLabs MCP tools available in this session were used
read-only or not at all. `place_outbound_call()` still speaks to the real
`POST /v1/convai/twilio/outbound-call`.

**Enforced:** `backend/app/integrations/no_contact.py` reads the
environment on **every** call and never caches, so `get_settings()`'s
`lru_cache` cannot leave it stale and import order cannot defeat it. It
self-enables whenever `FIXI_NO_CONTACT` is set **or** the process runs
under pytest, which means the default test suite cannot dial, message or
email anyone even by accident.

The guard sits at the transport — inside `place_outbound_call()`, the one
function in this codebase that makes a phone ring — so it covers every
caller including future ones. `place_call()` additionally checks it before
the policy flags, so the recorded `CALL_SKIPPED` reason names the real
cause instead of blaming configuration.

**The substitute, and why it cannot leak.** A harness may arm
`provider_substitute()`, which lets the *job body* proceed past the skip so
downstream handling can be exercised. It does **not** relax the transport
guard: arming the flag without also patching the transport raises
`NoContactViolation` instead of dialling. That fail-closed property has its
own test (`test_transport_guard_fails_closed_when_substitute_is_missing`).
`provider_substitute()` also refuses to arm outside no-contact mode, so it
cannot be used to enable anything in production.

**Verified with test doubles, not live:** request acceptance, later
completion, conversation retrieval, transcript parsing, outcome mapping
(answered / failed / unanswered-is-not-answered), duplicate redelivery
idempotency, provider HTTP failure, and that no `PLACE_CALL` job is left in
the queue afterwards. Ten tests in
`backend/tests/test_no_contact_harness.py`.

**Never verified live, deliberately left unperformed:** a real outbound
call, real audio, a real signed post-call webhook delivery, and
`ELEVENLABS_WEBHOOK_SECRET` (still empty — ElevenLabs only issues one
against a reachable HTTPS destination, and `PUBLIC_BASE_URL` is localhost).
To make a genuine call: unset `FIXI_NO_CONTACT`, set
`OUTBOUND_CALLS_ENABLED=true`, and put the recipient on
`OUTBOUND_CALL_ALLOWLIST`. All three are required.

**Zero live call attempts were made during this session.**

---

## 6. Required external configuration

| Variable | Needed for | State |
| --- | --- | --- |
| `GEMINI_API_KEY` | real coordinator reasoning | set; falls back to a labelled fixture coordinator without it |
| `ELEVENLABS_API_KEY` / `_AGENT_ID` / `_PHONE_NUMBER_ID` | outbound voice | set |
| `ELEVENLABS_WEBHOOK_SECRET` | post-call webhook verification | **empty** — needs a reachable HTTPS `PUBLIC_BASE_URL` first; transcripts are polled instead |
| `TAVILY_API_KEY` | contractor research | set; fixture adapter otherwise |
| Email / SMS transport | actually sending a message | **none** — this is why outward messages stay drafts |

---

## 7. What is NOT done

Honest list. None of these is hidden behind a "coming soon" screen.

### Genuinely missing capability

1. **No email or SMS delivery.** No transport is configured, so an outward
   message is saved as a `DRAFT` and says so. Wiring a provider means an
   adapter plus a `QUEUED → SENT → DELIVERED/FAILED` transition; the
   states already exist and the UI already renders all of them.
2. **No attachment upload from the message composer.** Existing
   attachments render and open; adding one goes through the Documents
   surface instead.
3. **No browser voice panel.** The original `frontend`'s `VoicePanel` was
   never functional — its own docstring calls it a disabled placeholder —
   so there was nothing to port. Signed session creation exists
   server-side; nothing in the UI starts one.
4. **`MockBookingConnector` still invents availability.** This is the
   last piece of the retired demo layer left in the operational path, and
   CLAUDE.md prohibits invented availability explicitly. It generates
   candidate slots from a date offset rather than reading any
   contractor's calendar, and the coordinator's `SCHEDULE_VISIT`
   proposals are booked against them. The honest counterpart already
   exists — `POST /appointments/{id}/reschedule` records a time a human
   actually arranged, PENDING, with no provider booking id and an event
   naming who agreed it — but it is not yet the only way an appointment
   is created. Replacing the connector means either a real provider
   integration or routing all scheduling through that human-recorded
   path. Flagged in the connector's own docstring.
5. **`ELEVENLABS_WEBHOOK_SECRET` is still empty**, so post-call webhooks
   cannot be verified and transcripts are polled instead. ElevenLabs only
   issues that secret against a reachable HTTPS destination, and
   `PUBLIC_BASE_URL` is localhost.

### Not verified

6. **No live call, ever, this session.** Downstream processing is proven
   with an injected substitute; a real call, real audio and a real signed
   webhook delivery remain unperformed by design (§12). That is the single
   biggest gap between "verified" and "known to work end to end", and it
   is deliberate.
7. **No side-by-side visual diff against the running reference** — see §4.
8. **Narrow-width behaviour was reasoned about, not measured.** Every
   screen uses the responsive patterns the existing ones do, and tables
   scroll inside their own containers, but no 768px screenshot pass was
   run.

### Known rough edges

9. **The Insights category donut shows a meaningless 100% wedge when
   nothing is categorised**, because the UI casts a null category to a
   `Trade` and renders it unlabelled. `category` is a new column and is
   NULL on all 14 cases in `backend/data/repairflow.db`, so this is the
   state that database is actually in. Queued as
   `docs/UI2_TODO.md` #1, with the `category` backfill as #2.
10. **Two money sources disagree.** Insights and Reports read
   `cost_entries`; property stats read `work_orders.quote_pence`. On the
   real data that is £0.00 on one screen and £200.00 on another for the
   same property. This contradicts the claim in §1 that `analytics.py`
   is the single source of every metric — that is true within Insights
   and Reports, not across the whole app. Left open deliberately: it is
   a definition question (does spend mean quoted or invoiced, and should
   one fall back to the other?), not a patch. See the tail of
   `docs/UI2_TODO.md`.
11. The **Reports** screen does not read its filters from the URL, so a
   reports view is not linkable the way Insights, Properties, Contractors,
   Tenants and Messages are. Its own controls work.
12. The **Insights property filter** lists operational properties only, so
   an archival sample property cannot be singled out there even with
   archival history included.
13. **Insights chart drill-downs** open an inline panel; they do not push
    filters onto the Maintenance list. Both were acceptable per the brief;
    only one is implemented.
14. The **property-history trade drill-down** filters the table but its
    total is computed from the filtered rows rather than asserted equal to
    the donut segment — the donut sums work orders by trade while a history
    row carries the case's single primary trade, so the two genuinely
    differ. The year drill-down does reconcile exactly. This is documented
    on screen rather than papered over.

### Inherited, still open (carried from before this session)

These predate the migration and are recorded in `docs/UI2_CHECKPOINT.md`:

15. ESCALATED / CANCELLED cases do not halt automatic execution. Reachable
    only with a hazard flag; every existing case carries `risk = UNKNOWN`.
16. `RESOLVED → ESCALATED` is broken, so a hazard reported after resolution
    cannot re-escalate.
17. `execute_action` can stick at `RUNNING` if the executor raises between
    lease and terminal write.
18. Some service paths commit rows written before a `DomainError` is
    raised.
19. A lost-update race remains on double-submitted approvals.
20. `create_voice_session` returns 202 even when the provider call failed.

### One judgement call worth re-checking

`backend/data/repairflow.db` was **not** modified. It still holds the nine
scripted demo cases an older build seeded, alongside cases #1–#5, which
carry genuine ElevenLabs conversations. `python -m app.legacy_demo_purge
--dry-run` shows exactly what would go; `--apply` removes it. That is the
owner's decision, not mine, because §10 says to preserve existing and
ambiguous records.
