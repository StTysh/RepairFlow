# Fixi — autonomous repair coordination

**Status:** implemented, and no longer a demo. The scripted hackathon layer (Play demo, Reset demo, simulated observations, boot-time seeding of fictional cases) has been removed: cases originate from real intake, and an empty database is a supported state with real onboarding empty states rather than manufactured activity. Backend (FastAPI + SQLAlchemy + Pydantic AI) and frontend (React + Vite + Tailwind) run locally against a real SQLite database. The default test suite passes against a real on-disk file with zero external network calls, and can never place a call, send a message or reach a provider — see *No-contact guarantee* below. See [docs/23](docs/23_RISKS_AND_OPEN_QUESTIONS.md) and [docs/26](docs/26_SPECIFICATION_REVIEW.md) for the full, dated implementation log — including every material deviation from the original spec and the exact state of each live-provider gate.

Fixi maintains a repair case across calls, appointments and contractor reports. It interprets new evidence, proposes the next action, executes only policy-approved actions, and waits durably for the next real-world event.

## Hero demonstration

A roof visit cannot proceed without scaffolding. The coordinator interprets the contractor's report, preserves the original unresolved issue, creates a prerequisite, and blocks roofing. An operator approves the simulated scaffolding commitment. When installation and access handover are reported complete, the original roofing order becomes actionable and is rebooked. Tenant confirmation and all required follow-on work gate resolution.

This full loop passes deterministically end-to-end in `backend/tests/test_hero_path.py` using a scripted fixture coordinator. It has also been exercised manually against the real Gemini API through simpler cases (see docs/26's 2026-09-19 correction entry) — the model correctly proposed a context-specific triage, correctly waited when nothing was actionable, and correctly escalated to a human rather than inventing a contractor when no approved supplier existed for the required trade.

## What's live vs simulated

Contractor organisations, calendars, bookings and physical work are always **SIMULATED** (`MockBookingConnector`; no real contractor is ever contacted, no real booking is ever made).

| Provider | State in this repo | Notes |
|---|---|---|
| Gemini (coordinator reasoning) | **Live when `GEMINI_API_KEY` is set** | Falls back to a labelled, conservative fixture coordinator otherwise. Every proposal is provenance-tagged so the UI never conflates a real decision with a fixture one. |
| ElevenLabs (browser voice) | Code-complete, live acceptance gate intentionally not pursued for this MVP | Signed session creation, post-call webhook (HMAC-verified), transcript/audio persistence, and the three dedicated-secret server tools are all built and tested (`backend/tests/test_voice.py`) against synthetic signatures and a monkeypatched network boundary — never the real ElevenLabs API. Wiring a specific live agent was explicitly descoped by product decision; fixture/simulated mode is sufficient for this MVP. |
| Tavily (contractor research) | Code-complete, untested against the live API | No `TAVILY_API_KEY` was available. `TavilyResearchAdapter` is exercised against a stubbed HTTP transport (`backend/tests/test_research.py`); the always-available `FixtureResearchAdapter` is the default. Tavily is SHOULD-HAVE, not a hard gate. |

## Running locally

Requires Python 3.12 and Node 20+.

### Backend

```
cd backend
uv sync                       # or: python -m venv .venv && .venv/Scripts/pip install -e .
cp .env.example .env          # optional -- fixture mode works with no keys at all
uv run uvicorn app.main:app --port 8000
```

Run uvicorn from inside `backend/` (or point `--app-dir` at it) so `app` is importable.

**Nothing is seeded on boot.** The application starts against whatever is in
the database, including nothing at all. Two optional, idempotent commands
populate it:

```
python -m app.seed                    # sample portfolio: properties, tenants, approved contractors
python -m app.archive --apply         # ~60 closed archival cases across 8 sample properties, 2021-2026
python -m app.archive --validate      # 11 integrity checks over that import
python -m app.archive --remove        # removes exactly that batch, nothing else
python -m app.legacy_demo_purge --dry-run   # count the scripted demo cases an older build seeded
python -m app.legacy_demo_purge --apply     # remove exactly those nine cases
```

Archival cases are marked with an `archive_batch_id` and are excluded from
every current-workload count, notification and agent wake. They exist so
charts and property history have something to show; they can never be
actioned, and the application works normally without them.

### Frontend

There are two frontends in this repo. **`frontend-fixi` is the one actually served** — the backend mounts its production build at `http://localhost:8000/` directly (see `backend/app/main.py`), so once the backend is running there is nothing further to start for that path. `frontend` is the original build; it has some components (`DecisionCard`, `WorkGraph`, `VoicePanel`) not yet ported over to `frontend-fixi`, and is not what the backend serves by default.

For local dev with hot reload against `frontend-fixi`:

```
cd frontend-fixi
npm install
npm run dev
```

Open `http://localhost:5173`. Operator sign-in can be disabled entirely via `OPERATOR_AUTH_ENABLED=false` in `backend/.env` (the frontend auto-detects this and skips the login form); when enabled, credentials come from `backend/.env` (`OPERATOR_USERNAME`/`OPERATOR_PASSWORD`). The frontend polls the backend directly over CORS; no build step is required for local dev.

To run the original `frontend` instead (has the approval/dependency-graph/voice-panel UI `frontend-fixi` currently lacks — see Known gaps below):

```
cd frontend
npm install
npm run dev
```

### Tests

```
cd backend
uv run pytest tests/ -q
```

Real on-disk SQLite, zero external network calls, and no outreach is
physically possible (see *No-contact guarantee*). Provider-specific tests
(`test_voice.py`, `test_research.py`, `test_no_contact_harness.py`)
exercise real signature, parsing and state-transition logic against
synthetic or stubbed data, never a live API — see docs/22 for the testing
strategy and docs/23 for which live-provider checks have never been run.

### No-contact guarantee

`backend/app/integrations/no_contact.py` is a process-local kill switch,
independent of `Settings` (which is `lru_cache`d and could go stale). It
reads the environment on every call and self-enables whenever
`FIXI_NO_CONTACT` is set **or** the process is running under pytest, so the
default test suite cannot dial, message or email anyone. The guard sits
inside `place_outbound_call()` — the one function in the codebase that
makes a phone ring — so it covers every caller.

A verification harness (`backend/tests/test_no_contact_harness.py`) proves
the downstream call path end-to-end by injecting a deterministic substitute
at the transport boundary: request acceptance, later completion, retrieval,
transcript parsing, outcome mapping, duplicate delivery and failure. It
arms a `provider_substitute()` flag so the job body proceeds, but the real
transport still refuses — arming the flag without patching the transport
raises rather than dialling. There is no path where a missing fixture falls
through to the real client.

To make a genuine call, unset `FIXI_NO_CONTACT`, set
`OUTBOUND_CALLS_ENABLED=true`, and put the recipient on
`OUTBOUND_CALL_ALLOWLIST`. All three are required.

## Known gaps

- **No browser voice panel.** The original `frontend`'s `VoicePanel` was never functional (its own docstring describes it as a disabled placeholder), so there was nothing to port. Signed session creation exists server-side; no UI starts one.
- **Email and SMS have no delivery transport.** Composing an outward message persists a **draft** and says so on screen. Nothing is ever displayed as sent on the strength of a saved row.
- See `docs/UI2_IMPLEMENTATION_HANDOFF.md` for the current, dated status of the full-application migration, including remaining work.
- **ElevenLabs live voice** is code-complete but its acceptance gate (real audio, real transcript, real webhook delivery) was not run — see the table above.
- **Tavily** is code-complete but untested against the real API.

## Documentation index

| Read | Document |
|---|---|
| Event and product | [00 Hackathon](docs/00_HACKATHON_CONTEXT.md), [01 Vision](docs/01_PRODUCT_VISION.md) |
| Evidence and competition | [02 Business](docs/02_BUSINESS_PROBLEM_RESEARCH.md), [03 Competitors](docs/03_COMPETITOR_RESEARCH.md) |
| Scope and topology | [04 MVP](docs/04_MVP_SCOPE.md), [05 Architecture](docs/05_SYSTEM_ARCHITECTURE.md) |
| Domain contracts | [06 Models](docs/06_DOMAIN_MODEL.md), [07 State machine](docs/07_CASE_STATE_MACHINE.md) |
| Agent implementation | [08 Agent](docs/08_AGENT_ARCHITECTURE.md), [09 Pydantic AI](docs/09_PYDANTIC_AI_DESIGN.md), [10 Tools](docs/10_TOOL_CATALOG.md) |
| Integrations | [11 ElevenLabs](docs/11_ELEVENLABS_INTEGRATION.md), [12 Tavily](docs/12_TAVILY_INTEGRATION.md), [13 Gemini](docs/13_GEMINI_INTEGRATION.md) |
| Sponsor assessments | [14 Modal](docs/14_MODAL_ASSESSMENT.md), [15 Conduct](docs/15_CONDUCT_ASSESSMENT.md) |
| Interfaces and storage | [16 API](docs/16_API_AND_WEBHOOK_DESIGN.md), [17 Database](docs/17_DATABASE_DESIGN.md) |
| Experience and boundaries | [18 UI](docs/18_FRONTEND_UX.md), [19 Safety](docs/19_SAFETY_AND_ESCALATION.md) |
| Execution | [20 Demo](docs/20_DEMO_SCRIPT.md), [21 Build plan](docs/21_IMPLEMENTATION_PLAN.md), [22 Testing](docs/22_TESTING_STRATEGY.md) |
| Due diligence | [23 Risks](docs/23_RISKS_AND_OPEN_QUESTIONS.md), [24 Sources](docs/24_RESEARCH_SOURCES.md) |
| Review | [25 Questions answered](docs/25_RESEARCH_QUESTIONS_ANSWERED.md), [26 Implementation log](docs/26_SPECIFICATION_REVIEW.md) |
| Full-application migration | [Handoff](docs/UI2_IMPLEMENTATION_HANDOFF.md), [Interaction inventory](docs/UI2_INTERACTION_CHECKLIST.md), [Working checkpoint](docs/UI2_CHECKPOINT.md) |

## MVP acceptance

One persistent case completes the unexpected dependency loop without direct UI status editing. Duplicate delivery causes no duplicate commitment (`test_phase2_reliability.py`). A backend restart while roofing is blocked preserves the case and allows continuation (`test_phase2_reliability.py`). A gas/electrical-danger variant pauses automation before any model call (`test_coordinator.py`'s hazard-gate test). The UI identifies evidence, proposed action, executed result and simulated activity separately via per-event provenance badges (LIVE/SIMULATED/FIXTURE).
