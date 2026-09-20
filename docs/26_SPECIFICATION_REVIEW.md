# 26 — Specification review and decision record

Review date: 19 September 2026. Scope: research evidence, architecture, interfaces, consistency and one-day feasibility. **Documentation review only: no application, live call or integration test is claimed.**

## Final design decisions

| Decision | Rationale / authoritative contract |
|---|---|
| One operational coordinator | Small shared domain, no justified specialist handoffs; 08 |
| Gemini 3.8 Flash via Pydantic AI | Current researched model plus typed execution; account/schema smoke test still required; 09/13 |
| Deterministic policy/state + typed proposal | Model interprets evidence; code owns effects and authority; 06/07/10 |
| CRUD + immutable timeline + DB jobs | Persistent waits without full event sourcing or extra infrastructure; 17 |
| SQLite single process/worker | One-day local demo; no host-loss/production availability claim; 05/17 |
| Browser voice with actual recording | Required user evidence path while cutting telephone provisioning; 11 |
| Logged Tavily discovery, separate approved network | Search is evidence, never confirmed capacity; 12 |
| Mock contractor connector | No invented real contractor API or commitment; 10 |
| Explicit dependency DAG and removal follow-on | Preserve unresolved issue and operational obligations; 07 |
| Polling | Compatible with selected tunnel and simplest UI update path; 05/18 |
| Modal/Conduct/Graph/Harness excluded | No concrete MVP problem requires them; 09/14/15 |

## Contradictions and interface gaps corrected during review

1. **Approval scope:** moved required approval behavior into MUST HAVE; only richer diagnostics/polish remain optional.
2. **Scaffold closure:** added removal as required follow-on. Roofing completion alone cannot close the case.
3. **Case versus work state:** case remains ACTIVE while one order is BLOCKED and another scheduled; no giant conflated status enum.
4. **Recording requirement:** made saved audio, full transcript, case correlation and actual caller-informed progression a live acceptance gate. Tavily logs are separate research evidence.
5. **Initial intake IDs:** new voice input uses FactInput/AvailabilityInput, not persisted models requiring a not-yet-created case ID. Trusted adapters allocate evidence IDs/provenance.
6. **During-call evidence:** VOICE_TOOL receipts support observations before final transcript turn IDs exist.
7. **Version checks and approval:** fresh proposals use optimistic version checks; existing approved actions revalidate current predicates without failing on their own approval event. Provider acknowledgments are never discarded as stale.
8. **Cancellation truth:** separate CancellationOutcome from BookingOutcome; initiation/timeout cannot imply released booking.
9. **Late contradictory reports:** resolved case can enter ESCALATED, preserving history, then operator-reviewed reopening.
10. **Voice transport:** explicit signed WebSocket URL path and React SDK binding; WebRTC requires its own credential type. PSTN remains stretch.
11. **Browser/contractor distinction:** MVP tenant CallRequest is not misused for supplier outreach; contractor voice is future scope.
12. **Operational versus evidence updates:** case version and event sequence are separate; audio-ready updates remain visible without unnecessarily invalidating operational decisions.
13. **Simulation clock:** domain demo time can advance; signature/credential/lease clocks stay real.
14. **Table rendering:** escaped union pipes inside Markdown table cells; checked consistent column counts.

## Requirement coverage

| Requested material | Where |
|---|---|
| Hackathon objective/schedule/partners/rules and unknowns | 00 and 23 |
| Business evidence/buyer/value measurement | 01–02 |
| Required competitor set plus newer close competitors | 03 |
| Concrete stack and alternatives | README, 05, 09, 11–15, 17–18 |
| Models, tools, inputs/outputs/side effects/approval | 06 and 10 |
| Case/work state and dependency model | 07 |
| Durable event-driven execution, idempotency/recovery | 05, 08, 16–17 |
| Voice/transcript/audio and Tavily logging | 11–12, 16, 22 |
| Safety/real booking boundaries | 10 and 19 |
| Context/component diagrams | 05 |
| Inbound/browser and outbound voice sequences | 11 |
| Contractor discovery/booking sequence | 12 |
| Report, dependency discovery and resumption sequences | 16 |
| State diagrams and data relationships | 07 and 17 |
| MVP, 3–5 minute demo, implementation phases/tests | 04 and 20–22 |
| Sources and all 30 requested answers | 24–25 |
| Final coding-agent instructions | CLAUDE.md and prompts/IMPLEMENTATION_PROMPT.md, authored after this review |

## Verification performed on the documentation

Read the full document set against the hero path and failure cases. Checked state/action naming, edge direction, closure/approval predicates, actual versus simulated boundaries, required source citations and all requested document names. Checked local Markdown links, balanced code fences and table column structure. Reviewed Mermaid source for diagram/participant scope; no graphical Mermaid renderer was available for a rendered-layout test.

The final implementation prompt is written after this architecture review and receives a final link/structure check. Application correctness still requires the tests in 22; static documentation checks cannot prove runtime behavior.

## Unresolved, intentionally explicit

Organizer rules/prizes/credit entitlements, exact SDK locks, model/account access, live ElevenLabs recording/webhook configuration, venue connectivity, measured latency/cost and product ROI remain unresolved. See 23. No source supports a claim that competitors cannot handle the exact dependency scenario.

## Future implementation amendments

Append material changes below using date, reason/evidence, affected contracts and verification. Do not silently replace the architecture. Routine SDK syntax adaptations may be recorded concisely; scope/provider/authority changes require updating the affected canonical document.

### 2026-09-19 — Phase 2 implementation, deterministic engine and hero path

Implementation began after this documentation phase (README's "Start implementation later"). Phases 0–2 complete: bootstrap, domain/database, deterministic transitions/dependency engine/action ledger/mock booking. The full hero recovery loop (roof visit fails → scaffold prerequisite discovered → approved → installed → roof rebooked → completed → removal released → approved → completed → tenant confirms → resolved) passes end-to-end via `services`/`executor`/`dispatcher`/`worker` with a `FixtureCoordinator` standing in for Gemini (Phase 3 not yet built). Plus the duplicate-report and restart-while-blocked gates from docs/21 Phase 2. Seven implementation clarifications, none changing a canonical contract's external shape:

1. **`MockBookingConnector.book()` takes `action_id` as an explicit keyword parameter, not a `BookingRequest` field.** `mock_reservations.action_id` has a real FK to `action_records.id` (docs/17); `BookingRequest` (docs/06) is the provider-facing request shape and deliberately carries no ledger-internal fields. The executor passes the actual `ActionRecord.id` at the call site.
2. **`CommandResult.resource_ids: dict[str, UUID]` cannot hold a list.** When `accept_report` satisfies a dependency edge and multiple work orders become READY in the same transaction, only `first_newly_ready_work_order_id` is summarized there; the complete set is still fully recorded via one `DEPENDENCY_SATISFIED` CaseEvent per newly-ready dependent, so no information is lost, just not duplicated into `resource_ids`.
3. **No `APPOINTMENT_WINDOW_ENDED` timer/job yet.** Deliberately deferred: docs/07 already allows a completion report to arrive and normalize a `SCHEDULED`/`IN_PROGRESS` work order straight to `AWAITING_REPORT` without an intermediate window-end webhook, which is exactly the hero path's shape (report arrives while the connector still shows the appointment `CONFIRMED`). A real wall-clock "no report ever arrived" timeout path is not yet implemented; candidate for Phase 9 if time remains, otherwise reported as a known gap.
4. **No CaseEvent is emitted when `accept_report` resolves a `NO_ACCESS`/`FAILED` outcome** (only `COMPLETED` emits `WORK_ORDER_COMPLETED`). The canonical taxonomy (docs/07) has no event type for this path; the work order's status change plus the `ActionRecord.result` (visible in the timeline per docs/18) serve as the audit trail instead of inventing an event type outside the table.
5. **`WorkOrderModel.completion_report_id` has no FK constraint** (plain string column). `work_orders` and `contractor_reports` each reference the other (a report belongs to a work order; a work order optionally points at its completing report), which is a genuine circular table dependency; SQLAlchemy's `create_all` cannot topologically order two tables that each require the other via a hard FK without `use_alter`, which SQLite does not support the way this project needs. The relationship is still enforced at the application layer (`accept_report` only ever sets it to a report that already references the same work order).
6. **Root-loop budget (docs/07: "at most six consequential actions") is measured as causation-chain depth, not a raw per-case action count.** Walking `CaseEvent.causation_event_id` backward from the current trigger, stopping at the first event with no causation (a fresh external report/approval/observation/intake), gives the length of the current *unbroken internal cascade*. A raw count would have falsely tripped on the hero path itself, which is ~11 legitimate sequential actions each triggered by a fresh external event (report, approval, observation), never more than 2 in a row without new external input.
7. **Two independent version checks, never cross-used**, exactly as docs/10's approval-revalidation paragraph requires: `executor.admit_proposal` checks `ActionProposal.expected_case_version` against the current case version (rejects a stale semantic decision, triggers a fresh COORDINATE at the current version instead); `executor.decide_approval` separately checks `ApprovalDecision.expected_case_version` (what the operator's UI last polled) against the current case version. `EXECUTE_ACTION` itself never compares a stored version at all — only current business predicates (slot validity, contractor approval, work order status) are re-checked immediately before execution, so an approval's own version increment can never invalidate the action it just approved.

Verification: `backend/tests/test_hero_path.py` (full loop), `backend/tests/test_phase2_reliability.py` (duplicate report + duplicate prerequisite admission are no-ops; simulated process restart via engine dispose/recreate against the same on-disk file preserves case version, event history and work-order graph, and a freshly constructed worker/coordinator resumes correctly). `backend/tests/test_domain_models.py` (FK rejection, unique-constraint dedup, naive-datetime rejection). All pass against a real (non-mocked) SQLite file with WAL/foreign_keys/busy_timeout pragmas active; no provider credentials involved (Gemini/ElevenLabs/Tavily are all in FIXTURE mode — see docs/23).

### 2026-09-19 — Phase 3–4 implementation, coordinator, API, demo controls

Phases 3–4 complete: real Pydantic AI `Agent` wired to Gemini via `GoogleModel` (mechanically verified with `FunctionModel` — no live `GEMINI_API_KEY` in this environment, see docs/23), a `ConservativeFixtureCoordinator` fallback, and the full FastAPI HTTP layer (`cases`, `observations`, `approvals`, `demo` routers) exercised through real ASGI requests, not direct Python calls. Two clarifications:

8. **`ActionRecord` (docs/06) gains a `payload_hash: str` field beyond the documented schema.** The operator UI has no other reliable way to obtain the exact value `ApprovalDecision.action_payload_hash` must echo back (docs/18: "approving sends proposal hash/version"); recomputing the hash client-side from a JSON-serialized proposal dict is fragile against serialization ordering/formatting differences from the server's own `payload_hash()`. This is admission-time plumbing, not a new domain fact — it is derived entirely from fields the schema already has — so it is additive to the read model rather than a change to what `ActionRecord` means. Verified round-trip through real HTTP in `backend/tests/test_api.py::test_approval_round_trip_through_http`.
9. **`POST /api/v1/demo/reset`'s deletion order was wrong on first implementation** and would have raised a foreign-key violation the first time it ran against a case with any appointment, contractor report, or booked scaffold slot (SQLite has `PRAGMA foreign_keys=ON`; see `db.py`). Caught by review before it was ever exercised against real data. Two separate bugs: (a) `ActionRecordModel` was deleted before `AppointmentModel`/`ContractorReportModel`, both of which reference it; `ContractorReportModel` was deleted after `AppointmentModel`, which it references — the corrected order is `DependencyModel → ContractorReportModel → AppointmentModel → ActionRecordModel` (each references the next). (b) `MockReservationModel`/`MockSlotModel` were never touched at all — they have no `case_id` column (a mock slot is contractor-calendar state, shared across cases, not case data), so a case-scoped bulk delete silently skipped them, leaving orphaned reservations pinned to a deleted `action_records`/`work_orders` row and a slot permanently stuck `is_reserved=True`. Fixed by scoping reservation cleanup through the work orders being cleared (`work_order_id IN (...)`) and releasing (`is_reserved=False`), not deleting, the underlying slots. Verified in `backend/tests/test_api.py::test_demo_reset_clears_case_and_releases_mock_reservation`, which drives a case to a real booked scaffold reservation before resetting and asserts zero `MockReservationModel` rows remain and no FK error occurs.

Verification: `backend/tests/test_coordinator.py` (real tool-calling round trip via `FunctionModel`, direct-output WAIT, hazard gate bypasses the coordinator entirely before any model call). `backend/tests/test_api.py` (auth enforcement, intake→triage→ready over real HTTP, full admit→AWAITING_APPROVAL→approve→executed round trip proving `payload_hash` works end to end, demo reset). 16 tests pass total against a real on-disk SQLite file; no provider credentials involved.

### 2026-09-19 — Phase 6 implementation, Tavily contractor research

Phase 6 complete: `TavilyResearchAdapter` (`backend/app/integrations/tavily.py`), a drop-in implementation of `executor.ResearchAdapter`'s Protocol, wired into `main.py`'s lifespan and threaded through `run_worker_loop` exactly parallel to how `build_coordinator(settings)` already selects real-vs-fixture for Gemini: constructed only when `settings.tavily_live`, otherwise `research_adapter=None` and `execute_action` keeps falling back to the existing `FixtureResearchAdapter`. No dependency was added — `httpx` (already pinned `>=0.28.1`, installed 0.28.1) is sufficient for the single bounded search call, matching docs/12's explicit preference for a custom wrapper over the documented Pydantic AI Tavily helper. Also added `read_research`, a fifth coordinator read tool (`backend/app/agents/read_tools.py`, registered in `coordinator.py`) so the model can inspect a completed `DISCOVER_CONTRACTORS` result — the `CaseSnapshot` it already receives has no research/candidate fields, so without this tool the coordinator would have zero visibility into research it just triggered. Two implementation clarifications, plus one real bug found and fixed in already-existing code:

10. **Domain deduplication groups multiple search hits into one `ContractorCandidate`, never auto-merging across domains.** Per docs/12 ("normalize duplicate domains but do not automatically merge unrelated companies that share a trading name"): results are grouped by normalized netloc (`www.` stripped); the highest-scoring result in a group names the candidate and every result in the group becomes one `EvidenceRef`. Two companies sharing a trading name but different domains stay as separate, unmerged candidates. `phone` and `service_area` are always left `None` — docs/12: "For unsupported values use null, not guesses" — a search snippet is not a reliable enough source to assert either without risking a fabricated claim. `claimed_emergency_service` follows a tri-state rule: `True` only on an explicit "emergency" mention in the title/excerpt (docs/12: "a website claim with a timestamp, not a live dispatch promise"), `None` (not `False`) otherwise, since absence of the word is not evidence the claim is false.
11. **Provider failure and no-results both degrade to the same shape**: an empty `candidates` list, an empty `research.results` list, and a human-readable entry in `ContractorSearchResult.warnings`, with the `ResearchSnapshot` attempt itself always preserved (never dropped, never fabricated) — docs/12: "A provider failure must not erase earlier research or cause a fabricated search result." One read-only retry on any `httpx.HTTPError` (network failure or non-2xx status) or a malformed JSON body, matching docs/12's eight-second-budget/one-retry rule exactly (`_REQUEST_TIMEOUT_SECONDS = 8.0`, a plain `for attempt in range(2)` loop, no backoff needed since the budget is a single request-response round trip).
12. **Bug found and fixed: `executor._apply_research_result` never coerced `ResearchSnapshot.id`/`ContractorCandidate.id` (Pydantic `UUID` fields, coerced from any valid UUID string at validation time) to `str()` before assigning them to the corresponding ORM string columns.** Every other ID-bearing `CaseEvent.payload` in `services.py` sources its value from an already-`str` ORM attribute (e.g. `report.id`, `work_order.id`); this was the first and only path that put a raw Pydantic `UUID` object into a payload dict, and `sa.JSON`'s default serializer (plain `json.dumps`, no `default=str`) raises `TypeError: Object of type UUID is not JSON serializable` on flush. This is pre-existing Phase-4 code, not something this phase introduced — it was simply never exercised, since no test or caller had driven `DISCOVER_CONTRACTORS` to completion before (confirmed by grep: zero prior references to `DISCOVER_CONTRACTORS`/`DiscoverContractors` in `backend/tests/`). Fixed by wrapping both IDs in `str(...)` at `ResearchSnapshotModel`/`ContractorCandidateModel` construction, consistent with every other ORM-construction call site in the codebase. Confirmed nothing auto-promotes a `ContractorCandidateModel` into `ContractorModel` (the approved-supplier table used for real booking eligibility) — `ContractorModel` rows are only ever created in `seed.py`; a searched candidate can never become bookable without a separate, human, out-of-band action that does not exist in this codebase.

Verification: `backend/tests/test_research.py` — `TavilyResearchAdapter.search()` exercised against `httpx.MockTransport` (real httpx request/response handling, no real network): domain grouping/dedup, excerpt truncation at 400 chars, emergency-claim tri-state, `verification_status` staying `UNVERIFIED`, phone/service_area staying `None`, no-results and provider-failure (503, asserted exactly 2 attempts) degradation paths, and that the query string never contains tenant identity. Plus one end-to-end test driving a real `DiscoverContractors` `ActionProposal` through `admit_proposal` → `worker.drain_due_jobs` → `execute_action` with the default `FixtureResearchAdapter`, asserting the persisted `ResearchSnapshotModel.provenance == "FIXTURE"` (never mislabelled LIVE) and that the UUID-serialization bug above is actually fixed. 21 tests pass total (16 prior + 5 new) against a real on-disk SQLite file. No live `TAVILY_API_KEY` exists in this environment — `TavilyResearchAdapter` is code-complete and tested against a stubbed transport, but never verified against the real Tavily API. Tavily is SHOULD-HAVE per CLAUDE.md, not a hard acceptance gate; this is reported honestly rather than claimed as a live pass.

### 2026-09-19 — Phase 5 implementation, ElevenLabs voice code path

Built the full browser-voice code path from docs/11/16: `app/integrations/elevenlabs.py` (signed session creation, post-call webhook signature verification, conversation/audio retrieval, transcript/outcome mapping), `app/api/voice.py` (three routers: operator-authed `/api/v1/voice/sessions[/bind|/ended]`, the signed `/webhooks/elevenlabs/post-call`, and the dedicated-secret `/integrations/elevenlabs/tools/{intake,observations,context}`), wired into `main.py`. **At the time this fork ran, no live `ELEVENLABS_API_KEY`/`ELEVENLABS_AGENT_ID`/`ELEVENLABS_WEBHOOK_SECRET`/`ELEVENLABS_TOOL_SECRET` existed in its isolated worktree — see the correction entry below for what changed immediately afterward in the main tree.** Every code path a live call would exercise is implemented and unit/integration-tested against synthetic signatures and a monkeypatched network boundary (never the real ElevenLabs API). Five clarifications:

13. **The exact ElevenLabs webhook HMAC signature format is not published in prose on their current docs site** (confirmed by fetching `elevenlabs.io/docs/agents-platform/workflows/post-call-webhooks`: it states webhooks "support authentication via HMAC signatures" and that the SDK's `construct_event`/`constructEvent` "verifies the signature, validates the timestamp," but does not document the header/signing scheme itself). Installing the official `elevenlabs` Python SDK to read its verifier source hit a hard environment blocker instead: `pip install elevenlabs` fails on this Windows machine with `OSError: [Errno 2] No such file or directory` on a deeply nested vendored file path (`elevenlabs/conversational_ai/whatsapp/types/body_send_an_outbound_message_via_whats_app_v_1_convai_whatsapp_outbound_message_post_template_params_item.py`) — a Windows `MAX_PATH` (260 char) limitation, not a dependency conflict; enabling OS-level long-path support was judged out of scope for an autonomous change to shared machine configuration. `app/integrations/elevenlabs.py::verify_webhook_signature` therefore implements the documented external convention their docs page's language matches (Stripe/Svix-style `ElevenLabs-Signature: t=<unix_ts>,v0=<hex hmac-sha256 of "{ts}.{raw_body}">`, with a timestamp tolerance) rather than a confirmed-exact spec. **This must be verified against one real webhook delivery before any live demo** — the module docstring and this entry both flag it; do not silently trust it live without that check. Plain `httpx` (already a dependency) is used for the REST calls instead of the SDK, which sidesteps the same long-path problem for the runtime path, not just the exploratory read.
14. **`voice.py`'s three router groups intentionally use three different auth mechanisms**, matching docs/16's own table exactly rather than a single consistent scheme: `/api/v1/voice/*` behind the same operator HTTP Basic as every other `/api/v1` route (docs/16's "Minimal demo authentication": this is a synthetic single-operator demo, so the "tenant browser" session is the operator's own browser — there is no separate tenant identity system to authenticate against); `/webhooks/elevenlabs/post-call` authenticated purely by HMAC signature verification, no operator auth, per docs/16's explicit carve-out ("Separate provider routes use their own verification and bypass operator Basic only for those exact paths"); `/integrations/elevenlabs/tools/*` authenticated by a static `ELEVENLABS_TOOL_SECRET` bearer header (checked via `secrets.compare_digest`) plus a per-conversation `correlation_token` carried in the request body and checked against `communications.correlation_token_hash` (only the hash is ever stored, per docs/11) — this is the "dedicated bearer secret + scoped correlation token" docs/16 specifies, implemented as two independent checks rather than one combined credential so a leaked static secret alone can never move data into an unrelated case.
15. **Tool-call idempotency relies on the underlying `services.submit_intake`/`services.record_observations` functions' own existing dedup (Phase 2), not a separate invocation-ID-keyed cache.** Docs/16 allows this explicitly for provider server tools that may not supply an application `Idempotency-Key` header ("identical repeated intake/observations merge within that conversation"); building a second idempotency layer on top of already-idempotent domain functions would be exactly the kind of parallel state-mutation path CLAUDE.md prohibits ("do not invent a parallel state-mutation path"). Not separately re-tested here beyond what Phase 2's existing duplicate-report/duplicate-prerequisite tests already cover for those same functions.
16. **`FETCH_RECORDING`'s reconciliation semantics: fill gaps, never overwrite.** Docs/11 describes two independent producers of the same data — the post-call webhook (primary path) and the `FETCH_RECORDING` job (fallback, for when the webhook never arrives, per docs/11: "If the transcription webhook is missing, the scheduled FETCH_RECORDING job first retrieves conversation details... reconciles any missing transcript/outcome, and then retrieves audio"). Implemented as: `fetch_recording()` only overwrites `transcript`/`outcome` when they are currently empty, and only attempts the audio fetch when `recording.status != AVAILABLE`. This means the same job is safe to enqueue from three call sites (the webhook itself, `POST .../ended`, and the manual `retry-recording` endpoint) without ever clobbering good data with a stale/incomplete reconciliation pass.
17. **A conversation ID the webhook can't map to a bound `Communication` is quarantined, never guessed.** Docs/11: "preserve the unbound communication and require operator binding; do not discard the call or attach it to a guessed property." `record_webhook_receipt`'s durable receipt still gets created and marked `QUARANTINED` (HTTP 200, so the provider doesn't retry-storm), but no domain state changes; an operator would need a review surface to re-bind it manually, which is a UI-level gap not built in this phase (frontend is Phase 7/8, out of this fork's scope) — noted here as a known follow-up rather than silently working around it.

Verification: `backend/tests/test_voice.py`, 26 tests, all passing against a real on-disk SQLite file, real HMAC signature computation, real ASGI HTTP requests (`httpx.ASGITransport`), and a monkeypatched `elevenlabs_integration.fetch_conversation_details`/`fetch_conversation_audio` boundary for the `FETCH_RECORDING` reconciliation tests — never the real ElevenLabs network. Covers: valid/invalid/missing/malformed/stale-timestamp signatures, duplicate webhook delivery (idempotent, single receipt row), an unmapped conversation ID (quarantined, no domain mutation), a new/unknown envelope field (tolerated, no crash), empty-text transcript turns (skipped, not fabricated), USER/AGENT role preservation and ordering, `call_initiation_failure` marking the communication `FAILED`, `post_call_audio` with no audio payload never reporting `AVAILABLE`, honest `503 PROVIDER_UNAVAILABLE` (with no orphan `Communication` row left behind) from session creation when ElevenLabs isn't configured, out-of-order `ended`-before-`bind` delivery, conflicting `provider_conversation_id` binding rejected with `409`, tool-secret enforcement and scoped-correlation-token rejection on the tool routes, a full intake-via-tool round trip creating a real case, `tools/context` returning the correct minimum permitted context, and `FETCH_RECORDING` both populating a fresh communication and correctly declining to overwrite one that already has a transcript. Combined with the existing suite: 42 tests pass total; still zero live provider calls anywhere in the default suite.

### 2026-09-19 — Correction: real credentials appeared mid-implementation; live Gemini verified

The Phase 5 entry above was written inside an isolated git worktree with no `.env` file (gitignored, so `git worktree add` never carries it over), which is why it states no ElevenLabs credentials exist. Back in the main tree, the user added real `GEMINI_API_KEY` and `ELEVENLABS_API_KEY` values to `backend/.env` and supplied an existing ElevenLabs agent ID to use. Full detail and reasoning is in docs/23's matching correction entry; summarized here because it changes what's provable about two of the ten implementation phases:

18. **The docs/13 Gemini live acceptance gate is now MET, not just constructible.** A real demo intake was driven through the running API with `gemini_live: true`. The real `GeminiCoordinator` (not the fixture) produced a correct, context-specific `ApplyTriage` proposal from free text, then correctly `Wait`ed rather than inventing a schedule when no tenant availability existed — both real model round trips, end to end, through the actual `dispatcher`/`executor`/`worker` pipeline already tested against fixtures. This is the "small real-model evaluation" docs/22 asks for.
19. **Bug found via that live run: `dispatcher.run_coordinate` never persists an `OrchestrationRunModel` row.** `GET /cases/{id}/runs` — a canonical docs/16 route — returned an empty list despite two real coordinator invocations having just happened. `OrchestrationRun` (docs/17) is the only place `model_id`/`usage`/`tool_calls`/`policy_result` are meant to live, so this silently discarded the one auditable record of what the model actually did. Fixed directly in `dispatcher.py` (see the fix entry immediately following the hero-path work in this log, once applied).
20. **Full live ElevenLabs configuration was deliberately not pursued, per explicit user instruction ("I don't need real credentials at all, it's mvp").** `ELEVENLABS_AGENT_ID` was set (so `elevenlabs_live` is now `True`), but the referenced agent's prompt/variables/webhooks belong to an unrelated outbound-confirmation persona with a live inbound Twilio number attached — reconfiguring it was correctly out of scope for a local MVP demo and was not attempted. `ELEVENLABS_WEBHOOK_SECRET`/`ELEVENLABS_TOOL_SECRET` remain unset; no tunnel was built. The docs/11 live *voice call* gate stays UNMET, now by product decision rather than missing credentials — Phase 5's code and its 26 tests are unaffected by this decision.
21. **Housekeeping: `DATABASE_PATH`/`RECORDINGS_DIR` removed from `.env`/`.env.example`.** Both were relative-path overrides of `config.py`'s already-correctly-anchored (`BACKEND_DIR`-relative) defaults; `pydantic-settings` resolves a relative override against the process's current working directory, not `BACKEND_DIR`, so running uvicorn from inside `backend/` silently created a duplicated `backend/backend/data/` directory. Discovered while investigating clarification 19 above. See docs/23's matching entry.

### 2026-09-19 — Phase 9 implementation, reliability test matrix, and Phase 10 freeze

Phase 9: five tests added in `backend/tests/test_reliability_matrix.py` targeting architectural invariants beyond what the hero path and Phase 2's own gate already cover — cyclic dependency rejection (tested against the real install→repair→removal chain rather than a synthetic graph, since `add_prerequisite` can never actually form a cycle through its own call pattern), expired lease reclaim, negative tenant confirmation (which surfaced that `record_observations` already proactively reopens an `AWAITING_CONFIRMATION` case back to `ACTIVE` on a negative answer — a stronger property than the test originally assumed it needed to prove), a stale model proposal being superseded and requeued rather than silently dropped, and an uncertain external booking result staying `UNKNOWN` rather than being upgraded to confirmed. 52 tests pass total.

Not covered by an explicit test in this matrix, noted honestly rather than silently skipped: multiple simultaneous prerequisite branches on unrelated work orders in the same case (the domain model supports it — dependencies are keyed per work order pair — but no test constructs two independent blocked chains at once), and a timer-driven follow-up firing after a case has already reached a terminal status (the `FOLLOW_UP` job handler already checks `case.status in (RESOLVED, CANCELLED)` and no-ops, but this specific check has no dedicated test). Both are small, targeted additions if more time becomes available; neither represents a known defect.

Phase 10 (rehearse, document, freeze): README rewritten from the pre-implementation "no application implemented" version to reflect actual runnable state — real run/test/reset commands, an honest live-vs-simulated table per provider, and a "known gaps" section stating plainly that the frontend was never exercised in an actual browser (the Chrome automation extension was unavailable in this environment) even though its production build and full backend dependency surface were verified. No new package dependencies were added in Phases 9-10.

Final honest summary of this implementation session's acceptance gates: the **deterministic core (Phases 0-4) is fully built and tested** — domain engine, dependency DAG, action ledger, mock booking, orchestration, API, 52 tests, zero flakiness observed. The **Gemini live gate is MET** (verified against the real API, not just constructed). The **ElevenLabs live voice gate is UNMET by explicit product decision** (fixture mode is sufficient for this MVP; the code path itself is complete and tested). The **Tavily live gate is UNMET for lack of credentials** (SHOULD-HAVE, not required). The **frontend is built, typed against the real OpenAPI schema, and passes a production build, but was never interactively verified in a browser** in this environment — this is the one gap a reviewer should close before treating the UI as demo-ready.

### 2026-09-20 — Full-application migration: the hackathon scope is retired

Executed `prompts/UI2_FULL_APPLICATION_MIGRATION.md`. The authoritative
report is **`docs/UI2_IMPLEMENTATION_HANDOFF.md`** (what was built, how it
was verified, and §7: what is not done). Recorded here because several
entries are material corrections to canonical contracts, per CLAUDE.md.

22. **docs/04's one-day MVP scope no longer governs.** The user has stated
    the hackathon has ended and asked for an application they can use. The
    scripted layer is gone: `app/api/demo.py` deleted, no boot-time
    seeding, `_seed_demo_activity()` removed. An empty database is now a
    supported, first-class state with real onboarding empty states, rather
    than something the product papers over with fictional activity. The
    MVP *exclusions* in docs/04 no longer justify omitting navigation
    destinations, documents, notes, analytics or reports.

23. **docs/16 is materially incomplete: 26 routes → 58.** New routers:
    `overview`, `insights` (+ `/insights/cases`), `reports` (summary and
    `export.csv`), `search`, `properties`, `contractors`, `tenants`,
    `documents`, `notes`, `costs`, `messaging`, `field_updates`; plus
    `PATCH /cases/{id}`, `POST /cases` (operator-recorded intake) and
    `POST /appointments/{id}/reschedule`. The full table is in the handoff
    §1; docs/16 has not been rewritten route-by-route.

24. **docs/17 is materially incomplete: four new tables.**
    `archive_batches`, `notes`, `documents`, `cost_entries`, plus archival
    and category columns on `properties`, `repair_cases`, `tenants`,
    `contractors`, and delivery-state columns on `messages`. Migration is
    still `create_all()` at boot, now with `_add_missing_columns()` —
    Alembic revisions remain for the record but are not what runs.

25. **Three event types were appended but never declared in
    `EventType`** — `OPERATOR_INFO_REQUESTED` (latent since it was added),
    `CASE_EDITED`, `APPOINTMENT_RESCHEDULED`. `CaseEventModel.type` is a
    plain string, so the write always succeeded; the failure landed on the
    *read* side, where `load_case_snapshot` validates the case's own
    history and 500s the entire ticket page once such an event enters the
    recent window. A test now checks the enum against every `event_type=`
    in the tree.

26. **`assert_case_transition` permits a self-transition**, which is right
    for an idempotent internal retry and wrong for an operator action.
    Cancelling an already-cancelled case returned 202 and appended a second
    `CASE_CANCELLED` event, so the history showed it closed twice for two
    different reasons; resuming a never-escalated case did the same. The
    operator endpoints now refuse both explicitly. The transition graph
    itself is unchanged.

27. **`Communication.provider` was `Literal["ELEVENLABS"]`**, which
    rejected the operator-recorded intake channel. Widened to include
    `OPERATOR` — a conversation that happened in person or on a handset the
    operator was holding, with no vendor involved. It still gets a
    Communication row because intake is defined in terms of one (docs/16);
    what differs is that nothing external carried it.

28. **`create_all()` never backfilled a newly added column.** SQLite fills
    it with NULL on existing rows and a SQLAlchemy `default=` only runs at
    INSERT time, so three NOT NULL additions to `messages` would have read
    back NULL on the five rows already in `backend/data/repairflow.db` —
    a 500 on the Messages screen, on the one database that matters. Every
    test and manual check up to that point had run against a database
    created fresh, where the migration path is a no-op. Found by copying
    the real database and migrating the copy. Fixed, with a regression
    test that was confirmed to fail without the fix.

29. **`MockBookingConnector` still invents availability.** CLAUDE.md
    prohibits it and §3 of the assignment names "fake bookings"
    explicitly; this is the last piece of the demo layer in the
    operational path. `POST /appointments/{id}/reschedule` is the honest
    counterpart — a human-recorded time, PENDING, no provider booking id,
    with an event naming who arranged it — but the coordinator's
    SCHEDULE_VISIT proposals are still booked against fabricated slots.
    Documented in the connector's own docstring and in the handoff §7;
    not fixed.

30. **No live call was placed at any point.**
    `app/integrations/no_contact.py` reads the environment on every call,
    self-enables under pytest, and guards `place_outbound_call()` — the
    one function in the codebase that makes a phone ring. A harness may
    arm a substitute so downstream handling can be exercised, but the real
    transport still refuses: arming the flag without patching the
    transport raises rather than dialling, and that fail-closed property
    has its own test. The docs/11 live voice gate remains UNMET, now
    deliberately.
