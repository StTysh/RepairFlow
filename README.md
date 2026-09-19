# Fixi — autonomous repair coordination

**Status:** implemented. Backend (FastAPI + SQLAlchemy + Pydantic AI) and frontend (React + Vite + Tailwind + React Flow) both run locally against a real SQLite database. 52 backend tests pass against a real on-disk file with zero external network calls in the default suite. See [docs/23](docs/23_RISKS_AND_OPEN_QUESTIONS.md) and [docs/26](docs/26_SPECIFICATION_REVIEW.md) for the full, dated implementation log — including every material deviation from the original spec and the exact state of each live-provider gate.

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

Run uvicorn from inside `backend/` (or point `--app-dir` at it) so `app` is importable. Demo reference data (one property, one tenant, two approved fictional contractors) is seeded automatically and idempotently on startup — no separate seed step needed.

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

52 tests, real on-disk SQLite, zero external network calls. Provider-specific tests (`test_voice.py`, `test_research.py`) exercise real signature/mapping logic against synthetic or stubbed data, never a live API — see docs/22 for the testing strategy and docs/23 for exactly which live-provider checks were never run.

### Resetting demo data

`POST /api/v1/demo/reset?confirm_reset=true` (operator auth) clears all non-LIVE cases — any case containing a real recorded call is preserved.

## Known gaps

- **`frontend-fixi` (the UI actually served at `/`) has no approval UI, dependency graph, or voice panel.** It covers case list/detail/timeline/calls/property/files/costs against real backend data, but there is currently no way to approve/reject an `AWAITING_APPROVAL` action, inject a simulated contractor observation, or start a browser voice session from this UI — all of which the hero demo path above depends on. `frontend` (the original build) has this functionality; use it for a live demo of the full hero path until it's ported over. See docs/26 for tracking.
- Both frontends have been exercised live against a real running backend (real HTTP, real clicks) during development, not just `npm run build` type-checking.
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

## MVP acceptance

One persistent case completes the unexpected dependency loop without direct UI status editing. Duplicate delivery causes no duplicate commitment (`test_phase2_reliability.py`). A backend restart while roofing is blocked preserves the case and allows continuation (`test_phase2_reliability.py`). A gas/electrical-danger variant pauses automation before any model call (`test_coordinator.py`'s hazard-gate test). The UI identifies evidence, proposed action, executed result and simulated activity separately via per-event provenance badges (LIVE/SIMULATED/FIXTURE).
