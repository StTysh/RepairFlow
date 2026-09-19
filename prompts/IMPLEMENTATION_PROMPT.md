# Implement RepairFlow from this specification

You are the technical lead and coding agent implementing the one-day RepairFlow hackathon MVP. This repository was deliberately produced as a researched architectural specification, with no application implementation. The architecture was reviewed before this prompt was written.

Your task now is to implement the specified working demonstration. Do not repeat the research phase indefinitely, invent integrations, or replace the product with a chatbot.

## First: inspect and read

Inspect the actual repository and any applicable agent instructions. Read README.md, CLAUDE.md and **every document in docs/** before changing application files. Pay particular attention to:

- 00/23: event rules and provider entitlements still requiring confirmation.
- 04: one-day scope and real/simulated boundaries.
- 05/08/09: architecture and meaningful Pydantic AI use.
- 06/07/10/16/17: canonical schemas, state, tools, HTTP contracts and persistence.
- 11: mandatory actual call recording, full transcript and case ingestion.
- 12/13: Tavily and exact Gemini model/access policy.
- 19: safety and approval rules.
- 20/21/22: demo, sequential build plan and verification gates.
- 26: reviewed decisions and amendment log.

Preserve existing user changes if this is no longer an empty repository. Identify the current phase and continue from it. Resolve routine implementation choices autonomously; only ask for information when it materially blocks the work and cannot be inferred safely. Do not invent organizer permissions or external account access.

## Product outcome

Build a persistent operational coordinator for an unresolved repair. A case survives calls, appointments, failed visits and newly discovered prerequisites. The system observes → interprets → proposes → validates → acts → waits → resumes on the next event.

The hero path is a safe fictional roof defect. After the first simulated roofer visit, a free-text report says scaffold access is needed. Gemini proposes the new prerequisite; deterministic code blocks roofing and creates scaffold installation plus the required removal follow-on. An operator approves the scaffold commitment and later accepts handover evidence. Completion satisfies the edge, the original roofing job becomes actionable and the coordinator rebooks it. Roofing completion releases removal. All required work and affirmative tenant confirmation gate case resolution.

The initial case must not already contain the scaffold branch. A novel paraphrase of the contractor's report must work. Do not hard-code the exact phrase into a fake AI response.

## Fixed architectural choices

Use Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0/Alembic and SQLite on local persistent disk. One Uvicorn process, one lifespan worker, database-backed jobs and action ledger. No open database transaction across a model/provider request. Use WAL, foreign keys, unique idempotency constraints and optimistic case versions.

Use React/TypeScript/Vite, Tailwind/shadcn and React Flow. Serve the built UI from FastAPI. Use versioned HTTP polling, not SSE, because the chosen Quick Tunnel development transport does not support SSE. Keep backend/frontend one origin.

Use one central **Pydantic AI Agent** with typed dependencies/RunContext, scoped read tools and ToolOutput(ActionProposal). Gemini is the operational reasoning model. The selected researched model is **gemini-3.8-flash**; run the capability/access smoke test and follow the documented explicit fallback procedure if unavailable. Lock the actual passing package versions. Do not silently replace model/provider/schema semantics.

The model has no raw database session, mutation tools, arbitrary network access, shell or generic JSON patch. It returns one typed action. Normal code validates case scope, evidence, state, authority, money, slots, dependencies and duplicate effects, then executes through the action ledger.

Do not add Modal, Conduct, Pydantic Graph, Harness, Redis, Celery, Temporal, DBOS, Supabase, Postgres, vector search or specialist operational agents to this MVP. Optional Logfire is redacted and must not delay the hero path.

## Real voice evidence is required

Implement a real ElevenLabs browser microphone conversation with the official React SDK and authenticated session credentials. The browser talks directly to ElevenLabs; the backend provides short-lived session context and receives tools/webhooks. PSTN/Twilio provisioning and real contractor calls are outside the core scope.

Before a call, persist a Communication and token binding. Support in-call intake/observations with case-scoped server tools. Use ingress DTOs that do not require database IDs for not-yet-created availability/evidence. The backend allocates IDs, source references and provenance.

Verify signed post-call webhooks against raw bytes, deduplicate and persist before HTTP 200. Save the full ordered speaker-labelled transcript, not only a summary. Normalize the outcome separately and preserve uncertainty. Include the relevant caller words in the next coordinator snapshot.

Enable and verify provider audio saving and sufficient retention. Fetch the actual conversation audio, save nonempty bytes outside public assets, record digest/type/size, and provide protected playback. Reconcile conversation details if the webhook is missing. Do not label an absent or fixture recording as a real call.

The live acceptance test must let the participant speak a harmless unseeded phrase and dated availability. That phrase must appear in the app transcript and actual audio playback, and the caller's information must affect the next action. Evidence must survive restart. If account/configuration prevents this, continue the runnable fixture path but clearly report the live recording requirement as UNMET with the exact blocker.

Tavily is research, not telephony. Log its actual query, request ID when present, timestamps, returned URLs and candidate evidence against the case. Use a bounded Search adapter; Extract is optional. Never turn web claims into verified availability or fake a booking under a real searched firm's identity.

## Booking and safety

Implement only the persistent MockBookingConnector for automated bookings. Use fictional approved contractors, slots and synthetic quote amounts, with SIMULATED provenance. Persist reservations so idempotency/restart tests mean something. Future API/email/voice connectors are abstractions, not integrations to claim now.

A started call, sent request, elapsed appointment window or contractor attendance is not a successful repair. Booking requires a positive connector result. Cancellation has its own result model. Ambiguous external effects become UNKNOWN and require reconciliation; do not blindly retry a possible commitment.

Hazards, critical missing safety facts, vulnerability concerns, contradictory evidence, missing authority and unsupported suppliers stop ordinary automation. Escalate immediately without waiting for a model. No DIY gas/electrical/roof instructions, professional safety certification or emergency dispatch claim.

Scaffold scope/spend, handover acceptance and removal retain explicit human gates. Approval binds the exact action payload and authority; its own version increment must not invalidate the same immutable action. Revalidate current predicates before execution. Record provider acknowledgments even if a later observation changed the case version.

## Implement in phases

Follow docs/21 in order, tracking objective, tasks, tests and definition of done. Keep a runnable vertical slice throughout:

1. Bootstrap and SDK/model capability smoke tests.
2. Domain schemas/database/seed.
3. Deterministic transitions, dependency engine, durable jobs/actions and mock booking.
4. Live Pydantic AI/Gemini semantic coordinator.
5. API and first visible browser case.
6. Actual ElevenLabs call/transcript/recording path.
7. Bounded Tavily research.
8. Work graph/timeline/evidence UI.
9. Full hero, removal and verified closure.
10. Critical reliability tests, rehearsal and documentation.

The detailed numbered phases and time budgets in docs/21 govern if this compact list differs in grouping. Avoid generic workflow builders, repository-interface forests or a file per trivial class. Small modules should reflect real responsibility boundaries.

Use fixture model/provider mode to keep development moving, with explicit FIXTURE/SIMULATED badges. Replacing a live check with a fixture does not make that check pass. Cut PSTN, second calls, optional search/extraction/tracing and visual polish before core invariants or recorded-call evidence.

## API and UI contract

Preserve docs/16 routes and docs/06/10 DTOs; generate frontend types from OpenAPI. Do not maintain divergent status enums. Operator endpoints use the documented minimal protected demo access; provider endpoints use separate secrets/signatures. Keep secrets server-side, validate origins for browser writes and never expose recordings as static public files.

The main UI is a case workspace: original issue, risk/status, next-action explanation, work graph, blockers, approvals, appointment attempts and timeline. Show actual tool/policy results and provenance. Evidence drawer contains full transcript/audio; research drawer contains sources. No generic chatbot screen or invented chain-of-thought display.

Simulation controls submit external observations through domain services. They must not directly set lifecycle status. Separate simulated domain time from real signature, credential and lease timestamps.

## Tests and continuous verification

Run focused tests after each phase and the full required suite before declaring completion. Follow docs/22, including duplicate report/webhook/booking, restart while blocked, stale model decision, multiple prerequisites, cyclic dependency rejection, uncertain external result, hazard escalation, negative tenant confirmation and outstanding removal.

Use temporary SQLite files and injected clocks for deterministic tests. No external calls in the default suite. Real Gemini and ElevenLabs checks are explicit integration runs and reported separately. Include one browser hero E2E; test actual microphone/audio manually with the participant.

Do not report passing tests you have not run. If blocked, preserve failure details and continue all useful authorized work. Do not contact real contractors, residents, organizers or vendors, deploy publicly, or change live accounts merely because a local implementation is requested. A user-initiated consenting test call is the intended live demonstration path.

## Configuration and handoff

Create `.env.example` with descriptive placeholders for the actual configuration used: model/API credentials, ElevenLabs agent/API/signing/tool secrets, Tavily key, database/media paths, operator credential, public callback base URL and explicit provider/demo modes. Do not include real secrets or make optional keys mandatory for fixture startup.

Add documented install/start/seed/reset/test commands based on the implementation that actually exists. Keep data, recordings and credentials out of git. Preserve captured live-call evidence across synthetic demo resets unless deletion is explicitly requested.

Update affected canonical docs and append a reason/evidence/test record to docs/26 for material deviations. Do not silently change architecture to make a test easier. Record exact SDK/model versions and remaining organizer/account unknowns in docs/23.

At completion, report what works, how to run it, tests actually run, which provider paths were demonstrated live, which parts remain simulated, and any unmet acceptance gate. The goal is a credible, repeatable dependency-recovery demonstration with real caller evidence—not a claim of a production-ready property-management platform.
