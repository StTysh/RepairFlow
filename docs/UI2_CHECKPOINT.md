# UI2 full-application migration — working checkpoint

Living file. Updated as work proceeds so another session can resume without
re-running the investigation. Final report lives in
`docs/UI2_IMPLEMENTATION_HANDOFF.md`; the per-control inventory lives in
`docs/UI2_INTERACTION_CHECKLIST.md`.

Assignment: `prompts/UI2_FULL_APPLICATION_MIGRATION.md`. Started 2026-09-20.

---

## 0. Status at a glance

| Phase | State |
| --- | --- |
| Orientation + checkpoint | done |
| No-contact hard guard | done (10-test harness) |
| Demo/scripted removal | done |
| Backend: new models + endpoints | done (58 routes) |
| Archive dataset (Sonnet) | done (600 rows, 13/13 checks) |
| 8 sidebar destinations | done (17 routes) |
| Ticket detail parity | done |
| Verification + handoff | done — see docs/UI2_IMPLEMENTATION_HANDOFF.md |

---

## 1. Carried-forward knowledge (do not re-derive)

### Repository shape
- Backend `backend/app` — FastAPI + SQLAlchemy 2.0 async + Pydantic v2. SQLite at
  `backend/data/repairflow.db`.
- Frontend `frontend-fixi/` — TanStack Start built as a **static SPA**, served by
  FastAPI `StaticFiles` from `frontend-fixi/dist` (see `main.py:FRONTEND_DIST`).
  `frontend/` is the dead original prototype; do not edit it.
- Reference UI: `liza.UI2/` on branch `origin/liza.UI2` (43 files). **Read-only.**
  The user has instructed twice that this branch must not be merged or modified.
- Package manager for backend: `uv` at
  `C:\Users\stast\AppData\Roaming\Python\Python314\Scripts\uv.exe`.

### Traps that cost time before
- **`git status` lies on Windows.** ~22 files always show as modified because of
  CRLF vs `.gitattributes text=lf`. Verify with
  `git -c core.autocrlf=false diff --stat` — only `backend/uv.lock` is a real diff.
- `npm run build` can fail EPERM when `dist/assets` is stale; `flatten-dist.mjs`
  now `rmSync`s first, but `rm -rf dist` before a build is still the safe move.
- Frontend route files use TanStack file-based routing; `routeTree.gen.ts` is
  generated on build. Adding a route file is not enough — rebuild.
- `properties.$propertyId.history.tsx` must **not** use zod `validateSearch`;
  doing so froze the whole renderer (hydration against the SPA 404 shell loops
  synchronously). Search params are read from `window.location.search` directly.

### Unresolved issues inherited from the previous session
These were deferred, not fixed. The new assignment explicitly does not erase them.

1. **ESCALATED/CANCELLED cases do not halt automatic execution.** The coordinator
   can still be woken and `execute_action` can still run against a case that
   should be frozen. Reachable only when a hazard flag is set; all existing cases
   carry `risk = UNKNOWN`, so it is unreachable from the current data.
2. **RESOLVED → ESCALATED transition is broken** (hazard reported after
   resolution cannot re-escalate).
3. **`execute_action` can stick at `RUNNING`** if the executor raises between
   lease and terminal write.
4. **Partial-write commit on `DomainError`** — some service paths commit rows
   written before the error is raised.
5. **Version lost-update race** on double-submit of an approval/action.
6. **`create_voice_session` returns 202 even when the provider call failed.**

### Safety state found at start
- `backend/.env` has `OUTBOUND_CALLS_ENABLED=true` and
  `OUTBOUND_CALL_ALLOWLIST` containing a single real mobile number (the
  owner's). The number itself is deliberately not repeated here — it is
  personal data and this file is tracked. Read it from `backend/.env`,
  which is gitignored and has never been committed.

  > **It was written here in full in three earlier commits** (`2adb8da`, `4b839ba`, `f0b6c83`). Redacting the file does not remove
  > it from git history. If this repository is ever published or shared,
  > that history needs rewriting (`git filter-repo`) or the number
  > treated as disclosed.
- `main.py` lifespan unconditionally starts `run_worker_loop`, which drains the
  durable `jobs` table. A pending `PLACE_CALL` job would dial on boot.
- Verified at start: **zero open jobs** (`COORDINATE` 8, `EXECUTE_ACTION` 6,
  `FETCH_RECORDING` 4313, `PLACE_CALL` 3 — all `DONE`).
- A backend was already running on :8000 from the previous session.

---

## 2. Decisions taken this session

Recorded as they are made; rationale kept short.

- **Reference `src/components/ui/button.tsx` is unavailable.** It is not in
  `git ls-tree origin/liza.UI2` and there is no on-disk checkout of that branch
  (`git worktree list` shows only `main`). Reproduced an equivalent button
  primitive in the target's own design language rather than guessing at the
  original file.
- **`liza.UI2` reference dev server is not running** (:5175 refused). Visual
  baselines taken from source (`styles.css` tokens, component markup) and from
  screenshots of the implementation, not from a live reference.

---

## 3. Work completed so far (this session)

### No-contact enforcement (§12)
- New `backend/app/integrations/no_contact.py`. Reads `FIXI_NO_CONTACT` from
  the environment on **every** call and never caches, so it cannot be
  defeated by `get_settings()`'s `lru_cache` or by import order. Also
  auto-enables under pytest (`PYTEST_CURRENT_TEST`), so the default test
  suite can never dial, message or email anyone.
- `place_outbound_call()` — the one function in the codebase that makes a
  phone ring — now calls `assert_contact_allowed("voice_call", to_number)`
  before opening the HTTP client.
- `place_call()` checks `no_contact_enabled()` *before* the policy flags so
  the recorded `CALL_SKIPPED` reason names the real cause.
- Verified at session start: the job queue had **zero** open rows, so
  nothing was pending that a restart could have dialled.

### Demo / scripted-progression removal (§3)
- `backend/app/api/demo.py` **deleted** (replay, reset, hard delete,
  seed-refs, simulated observations).
- `main.py` no longer calls `seed_demo_data()` on boot. Nothing is seeded
  at startup; an empty database is a supported state.
- `app/seed.py` gutted: the ~490-line `_seed_demo_activity()` generator
  (9 fictional cases, appointments, reports, dependencies, messages) is
  gone. What remains is an **opt-in** sample portfolio of reference
  properties/tenants/contractors, run by hand with `python -m app.seed`.
- New `app/legacy_demo_purge.py` removes exactly the nine scripted cases a
  previous build seeded, identified by recomputing their deterministic
  `uuid5` ids. Existing real cases (#1–#5, random uuid4, with genuine LIVE
  ElevenLabs conversations) cannot collide with that id set and are
  untouched. `--dry-run` / `--apply`.
- Frontend: "Play demo" and hard "Delete ticket" removed; the ticket page's
  status control is now a legal-actions menu with a proper dialog instead
  of `window.prompt`; the row "…" menu offers Open / Conversation / Cancel.
- `SimulateObservationDialog` → `RecordFieldUpdateDialog`, posting to the
  new `POST /api/v1/cases/{id}/field-updates`. Same capability, honest
  claim: it records that a *named person* reported something to a *named
  operator* at a recorded time (source_type OPERATOR, provenance LIVE),
  instead of asserting a fabricated event.
- New Ticket now posts to the real `POST /api/v1/cases` and requires both
  a property and a tenant, picked from the real directories.

### Schema (additive only)
New tables `archive_batches`, `notes`, `documents`, `cost_entries`. New
columns on `properties` (property_type, bedrooms, photo_key,
archive_batch_id), `repair_cases` (category, archive_batch_id,
archived_closed_at) and `messages` (channel, delivery_state,
delivery_detail, queued_at, delivered_at, read_at, attachments,
communication_id, archive_batch_id).

`db.create_all()` gained `_add_missing_columns()`: `create_all` never
alters an existing table, so a column added to a model after a database
was created was silently absent until a query failed. It only ever ADDs
nullable/defaulted columns and refuses anything destructive.

**The archival rule, enforced everywhere:** a row with a non-null
`archive_batch_id` is synthetic sample history. Excluded from
`GET /cases` and `GET /metrics/dashboard` by default; opt in with
`include_archived=true`, which flags each row `is_archived`.


---

## 4. Session outcome

All eight phases complete. Final state: 152 backend tests pass, `tsc` and
`eslint` clean, production build green, 41/41 end-to-end scenarios pass
against an isolated no-contact instance, and all eight destinations were
walked in a browser.

**`docs/UI2_IMPLEMENTATION_HANDOFF.md` is the authoritative report**,
including a §7 list of what is genuinely not done — most importantly that
no live call was ever placed (by design), that email/SMS have no delivery
transport, and that the six inherited state-machine bugs in §1 above
remain open.

`backend/data/repairflow.db` was deliberately left untouched: it still
holds both the nine scripted demo cases and the five real ones with
genuine ElevenLabs conversations. `python -m app.legacy_demo_purge
--dry-run` shows exactly what a cleanup would remove.

The migration path itself *was* rehearsed against a copy of that
database, which is where the last two bugs came from: three NOT NULL
columns left NULL on pre-existing rows (fixed, with a regression test),
and the archive validator counting every job in the database rather
than the batch's own (fixed). The backend that was running on :8000 was
stopped rather than restarted -- it was serving the new frontend build
against pre-migration code, and restarting it starts the durable-job
worker with live credentials, which is not an unattended decision.
