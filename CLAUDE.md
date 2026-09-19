# Implementation instructions

## Goal

Build the bounded RepairFlow demonstration specified in this repository. This phase delivered documentation only. Do not interpret illustrative interfaces as an existing application.

## Authoritative contracts

Resolve disagreements in this order: explicit user instructions; safety rules in docs/19; MVP limits in docs/04; domain/state/API contracts in docs/06, 07, 10, 16 and 17; architecture in docs/05, 08 and 09; implementation order in docs/21. Record a material correction in docs/26 and the affected canonical contract before changing callers.

Read every document before bootstrap; the shortest orientation is README followed by 04, 05, 06, 07, 10, 16, 17, 19, 20 and 21. Research findings and unknowns remain relevant.

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

## Expected structure when coding begins

- `backend/app/main.py`, `config.py`, `db.py`, `models.py`, `schemas.py`
- `backend/app/api/`: cases, observations, approvals, voice, demo
- `backend/app/domain/`: transitions, policy, dependencies, services
- `backend/app/orchestration/`: dispatcher, worker, executor, dedupe
- `backend/app/agents/`: coordinator, dependencies, read_tools, instructions
- `backend/app/integrations/`: elevenlabs, tavily, booking
- `backend/app/seed.py`; `backend/tests/`; `frontend/src/`
- `frontend/src/components/`: CaseHeader, WorkGraph, DecisionCard, Timeline, VoicePanel, DemoControls
- Lockfiles, `.env.example`, documented local run/reset commands, gitignored `data/`

Modules are responsibility boundaries, not a demand for a file per class. Avoid repository-interface forests or a generic workflow builder.

## Non-negotiable prohibitions

No autonomous emergency diagnosis, unsafe DIY instructions, arbitrary SQL/shell/browser tools, real contractor outreach, payments, unsigned webhook acceptance, public unauthenticated write endpoints, invented availability, fake live traces, or closure inferred from silence.

No API keys in the frontend or logs. No cloud deployment or provider/account mutation is implied merely by implementing the local prototype. Live calls require allowlisted test recipients and a documented enable switch.

## Testing

Follow docs/22. Run focused deterministic tests on each phase; retain a repeatable hero end-to-end test, duplicate/restart tests, unsafe-case tests and a small real-model evaluation. Do not call external providers from the default test suite. Report fixture-mode tests separately from real-provider checks.

## Working method

Follow docs/21 sequentially and keep a runnable vertical slice. Time-box provider setup. Preserve contracts. Document package versions actually installed and lock them. New SDK examples must match the installed release; do not paste older examples without checking current official docs. Update the risk register when a capability is unavailable.
