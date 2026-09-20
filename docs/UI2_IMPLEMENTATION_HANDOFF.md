# UI2 full-application migration — handoff

Assignment: `prompts/UI2_FULL_APPLICATION_MIGRATION.md`. Worked 2026-09-20 in
one unattended session. Companion files: `docs/UI2_CHECKPOINT.md` (working
notes, carried-forward knowledge, inherited bugs) and
`docs/UI2_INTERACTION_CHECKLIST.md` (every control, what backs it, how it
was verified).

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

*(Filled in at the end of the session — see §7 for anything that failed or
was not reached.)*

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

*(Filled in at the end of the session.)*
