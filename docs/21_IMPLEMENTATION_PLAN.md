# 21 — Sequential implementation plan

This plan begins **after** this documentation phase. Budget: **455 minutes (7h35) engineering**, leaving time for lunch, rule checks, rehearsal and failures in the event's daytime window. It is ambitious for one engineer; the hard cuts in 04 are essential. The full production concept cannot be built in one day.

Do not start with telephony or a polished dashboard. The first demonstrable result is a persisted report-driven dependency loop with fixtures; replace the semantic and voice boundaries with real providers next. Every phase keeps that path runnable.

## Phase 0 — Bootstrap and capability checks — 20 minutes

**Objective:** lock a working local platform and identify unavailable providers early.

**Components:** backend project manifest/lockfile, frontend Vite package/lockfile, `.env.example`, `config.py`, `main.py`, minimal README run instructions.

**Tasks:** inspect repository and read all docs; confirm event rules; choose currently supported pinned package releases; configure Python 3.12, Pydantic v2, FastAPI, SQLAlchemy, Pydantic AI Google support; run a real model structured-union/read-tool smoke test if credentials exist. Verify ElevenLabs account/agent/audio-saving access without expanding into PSTN. Establish fixture mode and explicit provider capability status.

**Dependencies:** none beyond credentials for live checks. **Test:** app health and trivial typed Gemini output; record exact model/SDK versions. **Done:** backend and minimal frontend start, secrets excluded, incompatible SDK/model discovered before core work. Do not spend the whole phase provisioning phone numbers.

## Phase 1 — Domain and database — 40 minutes

**Objective:** persist the shared case model.

**Components:** `schemas.py`, `models.py`, `db.py`, initial Alembic migration, `seed.py`, domain tests.

**Tasks:** implement canonical enums/DTOs; cases/issues/work orders/appointments/dependencies/events/actions/jobs/communications; add constraints and seed synthetic property/tenant/contractors/slots. JSON evidence fields are acceptable; avoid separate repositories per model.

**Dependencies:** phase 0. **Test:** create/reload case, FK/dedupe rejection, timezone validation. **Done:** database can represent roofing BLOCKED and scaffolding SCHEDULED while case remains ACTIVE.

## Phase 2 — Deterministic case/event engine — 50 minutes

**Objective:** demonstrate the core progression without a live model yet.

**Components:** `domain/transitions.py`, `dependencies.py`, `policy.py`, `services.py`, `orchestration/worker.py`, `dispatcher.py`, `executor.py`.

**Tasks:** transaction/event/job boundaries; single worker leases; version checking; typed fixture ActionProposal executor; graph cycle/uniqueness guards; completion/unblock; closure predicate; action approval storage. Implement mock reservations persistently. Create a test helper that supplies proposals, clearly separate from real inference.

**Dependencies:** phase 1. **Test:** original repair → blocked → prerequisite completed → original READY; restart and duplicate report. **Done:** a CLI/test/API vertical slice progresses through persisted state and stops correctly on missing approval.

## Phase 3 — Pydantic AI coordinator — 45 minutes

**Objective:** replace fixture interpretation with actual semantic decisions.

**Components:** `agents/coordinator.py`, `dependencies.py`, `read_tools.py`, `instructions.py`, orchestration run records.

**Tasks:** Agent + GoogleModel; scoped RunContext; ToolOutput(ActionProposal); input evidence packing; bounded retries/usage/timeouts; one proposal per run; stale-run supersession; short decision summaries; explicit fixture provider mode. Exclude mutating tools and raw database sessions.

**Dependencies:** phases 1–2; passing model smoke test. **Test:** novel scaffold phrasing, no-access without invented scaffold, hazard escalation, report prompt injection. **Done:** live model produces an accepted dependency proposal from source text; model error never changes state.

## Phase 4 — API and first visible case — 35 minutes

**Objective:** a demonstrable application before voice integration.

**Components:** API routers, minimal React case view, Timeline, DecisionCard, basic DemoControls.

**Tasks:** implement case polling and observation/report/approval endpoints; operator Basic authentication; provider-route separation; generated OpenAPI/client types; visible fixture/simulated badges; no arbitrary status writes.

**Dependencies:** phases 1–3. **Test:** HTTP report submission causes a visible persisted plan change; stale approval is rejected. **Done:** browser can run the blocked/resumed story, even with a plain graph initially.

## Phase 5 — Real ElevenLabs call evidence — 70 minutes

**Objective:** the user's actual voice reaches the application and is playable.

**Components:** `integrations/elevenlabs.py`, voice/tools/webhook routes, VoicePanel, recording worker, protected media route.

**Tasks:** browser session credentials/context; communication token mapping; in-call intake/observations; signature verification; receipt dedupe; full transcript adapter; provider audio-saving setting; audio fetch/save/playback; post-call reconciliation; outcome normalization and caller evidence in the coordinator snapshot.

**Dependencies:** phases 1–4, HTTPS callback tunnel and ElevenLabs access. **Test:** real unscripted phrase plus dated availability appears in transcript/audio and affects next action; replay webhook and restart. **Done:** all four artifacts exist: conversation ID, full transcript, actual saved recording, structured case outcome. Transcript-only is a failed live gate.

After 25 minutes of provider setup blockage, keep the fixture path runnable and flag the unresolved live gate; return after core completion. Do not claim the requirement is met if recording cannot be retrieved.

## Phase 6 — Tavily evidence — 20 minutes

**Objective:** add honest live research without procurement fiction.

**Components:** `integrations/tavily.py`, research DTO/endpoint and evidence drawer.

**Tasks:** bounded Search; store query/request ID/results/URLs/time; return UNVERIFIED candidates; optional two-page Extract only if time remains. Keep fictional approved contractors separate.

**Dependencies:** phase 4 and Tavily key. **Test:** real query displays actual sources; result text cannot override system policy; unavailable provider yields labelled failure/fixture. **Done:** research is inspectable and cannot imply contractor availability.

## Phase 7 — Graph and operational UI — 45 minutes

**Objective:** make the recovery loop obvious to judges.

**Components:** WorkGraph, CaseHeader, DecisionCard, Timeline, evidence drawers.

**Tasks:** fixed-position React Flow nodes; dependency direction/status; original issue always visible; past appointment attempts; audio/transcript access; approval state; real waiting/errors/provenance. Keep polling, not SSE.

**Dependencies:** phase 4; evidence surfaces from 5–6 when available. **Test:** human inspection of roof blocked → install complete → roof resumed → removal outstanding. **Done:** a viewer understands the case without reading JSON.

## Phase 8 — Full hero and closure — 25 minutes

**Objective:** finish the already-working recovery slice, not invent the graph now.

**Components:** simulation observations, scaffold removal rule, tenant confirmation and acceptance policies.

**Tasks:** wire installation/handover approval; roof rebooking; removal approval/completion; tenant “still leaking” refusal; explicit confirmation. Add simulated domain-time progression if needed while security timestamps stay real.

**Dependencies:** phases 2–7. **Test:** complete hero E2E; negative tenant feedback prevents closure; removal outstanding prevents closure. **Done:** truthful terminal state with full history.

## Phase 9 — Focused reliability gates — 45 minutes

**Objective:** resolve concrete demo failure risks.

**Components:** tests for services/worker/provider adapters, one browser E2E.

**Tasks:** duplicate report/completion/webhook; crash while blocked; crash after booking intent; stale slot/version; signature/case-scope rejection; recording missing; provider timeout; hazard path. Fix failures rather than adding broad coverage metrics.

**Dependencies:** hero path. **Test:** required matrix in 22. **Done:** critical invariants pass; live integration checks recorded separately from fixtures; any remaining failure listed honestly.

## Phase 10 — Rehearse, document and freeze — 60 minutes

**Objective:** a repeatable 3–5 minute presentation and clear handoff.

**Components:** README run/reset/seed commands, version/access record, demo seed, diagnostics, docs/23 and 26 updates.

**Tasks:** rehearse twice; validate audio volume/microphone, tunnel URLs and provider quotas; preserve evidence; prepare labelled replay fallback; freeze feature additions; write exact startup commands and environment keys actually used; remove secrets/test artifacts from commit scope.

**Dependencies:** prior gates. **Test:** fresh local start and complete demo using only documented steps. **Done:** operator can present the loop and answer what is real, simulated and incomplete.

## Cut order and scope truth

Cut PSTN, second live call, Extract, Logfire, visual polish and live search before cutting dependency logic, guardrails or recorded-call evidence. If the live voice gate cannot be met, deliver the runnable prototype but mark that requirement **UNMET**, with exact blocker; a fixture is a presentation fallback, not completion of the requirement.

With two confirmed team members, UI/voice setup can proceed alongside backend work after contracts stabilize. Team-size permission is unknown; do not depend on parallel staffing. No implementation agent should add specialist subagents or new infrastructure merely to fill time.
