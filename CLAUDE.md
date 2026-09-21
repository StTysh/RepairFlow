# Project instructions

## Status: the application exists

**Read `docs/APPLICATION_STATE.md` first.** It is the single current
account of what is built, what works, what is broken and what is
undecided, and it is kept reconciled against the code.

This file used to say "this phase delivered documentation only. Do not
interpret illustrative interfaces as an existing application." That has
been false since 2026-09-19. RepairFlow is built and running: ~14,800
lines of backend Python, a React SPA, 73 HTTP routes, 25 tables, 214
passing backend tests and 62 frontend tests. It was then migrated out of its hackathon framing on
2026-09-20 -- the scripted demo layer (Play/Reset demo, boot-time
seeding, fictional cases) was deleted, and an empty database became a
supported state rather than something to paper over.

Do not rebuild it. Read the state document, then the code.

## Orientation, in order

1. `docs/APPLICATION_STATE.md` -- what exists and what is wrong with it.
2. `README.md` -- what it is, and how to run it on a new machine.
3. `docs/26_SPECIFICATION_REVIEW.md` -- the dated log of every material
   deviation from the original specification. Read the newest entries;
   they supersede the numbered specs where they conflict.
4. The canonical contracts, when you need them: `docs/06` (domain),
   `docs/07` (case state machine), `docs/10` (tool catalog), `docs/16`
   (API and webhooks), `docs/17` (database), `docs/19` (safety).
5. `prompts/NEW_SESSION_HANDOFF.md` -- the constraints still in force
   and the traps that have already cost a session real time. Short.
6. `docs/audit/` -- twelve independent read-only audits from 2026-09-20.
   These are historical inputs, not a live tracker: many findings were
   fixed afterwards. `docs/APPLICATION_STATE.md` is the tracker.

`docs/00`, `docs/04`, `docs/18` and `docs/20` describe the retired
hackathon product and carry superseded banners. `docs/21`'s
implementation order is spent. `FIXI_UI_SPECIFICATION.md` and
`prompts/` are pre-migration inputs, kept for provenance.

## Authoritative contracts

Resolve disagreements in this order: explicit user instructions; safety
rules in docs/19; the current state in `docs/APPLICATION_STATE.md` and
the newest entries in docs/26; domain/state/API contracts in docs/06,
07, 10, 16 and 17; architecture in docs/05, 08 and 09. Record a material
correction in docs/26 and the affected canonical contract before
changing callers.

Where a numbered spec and the running code disagree, the code is usually
right and the spec is usually stale -- but confirm which, and fix the
loser. Do not silently leave the two disagreeing.

## Project-mandatory technologies

Pydantic AI meaningfully owns model execution, typed dependencies, tools, output validation and bounded retries. Gemini is the operational reasoning model. ElevenLabs supplies the live voice target. Tavily supplies optional live contractor evidence. FastAPI, SQLite/SQLAlchemy and React/Vite are the selected MVP platform.

These are project choices; no sponsor technology mandate was verified. Preserve a clearly labelled offline fixture mode when credentials are absent. Do not silently substitute another provider, model alias or database. Use the explicit fallback procedure in docs/13.

## Architectural rules

- One central operational agent; the voice agent is a constrained conversational adapter.
- Current case snapshot + immutable events + pending jobs preserve progress. Chat history is not authoritative state.
- Model-visible tools are scoped reads. Domain writes go through a typed action executor and deterministic policy.
- One action proposal per wake. Re-enter after material results; never keep an LLM session sleeping for days.
- Case, work order, appointment, dependency and external-action status are different concepts.
- A visit can end while the repair remains unresolved.
- A candidate from the web is not an approved contractor.
- Provider request acceptance is not booking confirmation.
- Do not hold a DB transaction across any network/model call.
- Use one backend worker/process for the SQLite MVP; enforce version checks and unique idempotency keys anyway.
- Use polling; Quick Tunnels do not support SSE.
- All demo physical activity and outbound commitments carry simulation provenance.
- Actual ElevenLabs audio recording and the full transcript are required: persist, correlate, display and play them. A summary alone is insufficient. Log Tavily research separately; it is a search service.

## Vocabulary

Case = persistent responsibility to resolve an issue. Work order = scoped activity. Appointment = one attendance attempt. Dependency = prerequisite-to-dependent edge. Observation = untrusted reported fact with provenance. ActionProposal = typed recommendation. Action ledger = execution/reconciliation state. CaseEvent = append-only audit fact. Job = durable wake-up work. Resolution = verified issue outcome with no outstanding required work.

## Optional or excluded

Logfire and Pydantic Evals are useful optional additions. PSTN Twilio calling is stretch scope only. Modal, Conduct, Pydantic Graph, Pydantic AI Harness, Temporal/DBOS, Supabase, PostgreSQL, MCP infrastructure, vector stores and specialist subagents are excluded from the one-day implementation.

## Actual structure

- `backend/app/`: `main.py`, `config.py`, `db.py`, `models.py`,
  `schemas.py`, `analytics.py`, `middleware.py`, `seed.py`,
  `backfill_category.py`, `legacy_demo_purge.py`
- `backend/app/api/` (18 routers): approvals, cases, contractors, costs,
  documents, field_updates, insights, messaging, metrics, notes,
  notifications, observations, overview, properties, reports, search,
  tenants, voice, plus `deps.py` and `errors.py`
- `backend/app/domain/`: transitions, policy, dependencies, services, errors
- `backend/app/orchestration/`: dispatcher, worker, executor, dedupe
- `backend/app/agents/`: coordinator, dependencies, read_tools, instructions
- `backend/app/integrations/`: elevenlabs, tavily, booking, no_contact
- `backend/app/archive/`: the synthetic closed-case dataset and importer
- `backend/tests/` (252 tests); `backend/alembic/` (frozen -- see docs/26)
- `frontend-fixi/` is the only frontend. `main.py`'s `FRONTEND_DIST`
  points at `frontend-fixi/dist`. The earlier `frontend/` app was deleted
  on 2026-09-21 -- recover anything from it with
  `git show bd61137:frontend/<path>`.
- `frontend-fixi/src/components/fixi/` (20 components): AppShell, Badge,
  CaseLifecycleActions, CaseProgress, CaseToolbar, Charts, CostsPanel,
  DecisionCard, DirectoryForms, DocumentsPanel, EmptyState, LoginGate,
  MessagesPanel, NewTicketDialog, PropertyStatsCharts, PropertyTabs,
  RecordFieldUpdateDialog, RescheduleDialog, UtilityBar, WorkGraph
- `data/` is gitignored, so a clone has **no database**. The app creates
  and migrates one on first boot; `python -m app.seed` adds reference
  data. See the README for the full bootstrap.

There is no `demo.py` -- it was deleted in the migration, along with the
scripted demo endpoints. There is no VoicePanel; browser voice was never
ported. Modules are responsibility boundaries, not a demand for a file
per class. Avoid repository-interface forests or a generic workflow
builder.

## Non-negotiable prohibitions

No autonomous emergency diagnosis, unsafe DIY instructions, arbitrary SQL/shell/browser tools, real contractor outreach, payments, unsigned webhook acceptance, public unauthenticated write endpoints, invented availability, fake live traces, or closure inferred from silence.

No API keys in the frontend or logs. No cloud deployment or provider/account mutation is implied merely by implementing the local prototype. Live calls require allowlisted test recipients and a documented enable switch.

## Testing

Follow docs/22. Retain the repeatable hero end-to-end test, the
duplicate/restart tests and the unsafe-case tests. Do not call external
providers from the default test suite -- it runs fully offline, and
`integrations/no_contact.py` arms itself under pytest so it cannot
place a call or send a message even by accident. Report fixture-mode
tests separately from real-provider checks.

Tests must not depend on `backend/.env`; conftest disables `env_file`
precisely so a result means something about the code rather than about
one machine.

## Working method

Keep a runnable vertical slice; docs/21's phase order is spent. Preserve
contracts. Document package versions actually installed and lock them.
New SDK examples must match the installed release; do not paste older
examples without checking current official docs.

Verify by running, not by grepping. Several defects in this repo passed
a read of the code and failed the moment something executed -- a
Windows path separator that made every unknown `/api` path return HTML
at 200, a test suite that silently read an untracked `.env`, a CORS
default that excluded the only frontend served. When you fix something,
add a test and confirm it fails with the fix reverted; a test that
passes either way guards nothing.

Update `docs/APPLICATION_STATE.md` when you change what is true, and the
risk register when a capability turns out to be unavailable.
