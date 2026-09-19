# 23 — Risks and unresolved questions

Snapshot: 19 September 2026. No external accounts were configured, no calls were placed, no contractors/organizers/vendors were contacted, and no live application was implemented during this research.

## Priority register

| Risk / unknown | Impact | Mitigation / owner / resolution gate |
|---|---|---|
| Event date not exposed in retrieved page body | Wrong schedule assumption | User-supplied date retained; attendee verifies registration/calendar at check-in |
| Rules on prior preparation, team size, submission and prizes | Eligibility | Attendee obtains organizer answers before build; record source/time |
| Credits/model entitlements unspecified | Provider failure | Engineer tests issued key and exact model before core implementation |
| Current Gemini/Pydantic schema compatibility | Runtime failure | Phase-0 nested-union/read-tool smoke test; documented allowed flattening fallback |
| ElevenLabs audio saving disabled or unavailable | User's recording requirement unmet | Enable/check configuration and run actual audio retrieval/playback gate |
| Webhook/call ID race | Lost or wrong-case evidence | Precreated Communication, token binding, receipts, quarantine and reconciliation |
| Tunnel URL changes / laptop sleep | Callback loss/delay | Update callback settings, keep host awake, reconciliation and labelled replay; no production uptime claim |
| Contractor APIs unavailable | Cannot book real suppliers | Mock connector clearly labelled; production preferred-network pilot |
| Search gives stale/unverified claims | Unsafe supplier selection | Evidence-only candidates; separate approved pool |
| Model invents completion or dependency | Wrong workflow | Evidence-linked typed output, guards, approvals and negative tests |
| Duplicate delivery / ambiguous external effect | Double booking/contact | Action ledger, unique keys, UNKNOWN state and reconciliation |
| Unexpected complexity of scaffolding | Safety and false closure | Human scope/handover approval and removal obligation; no technical certification |
| Multi-day durability overstated | Lost operations | Clarify process/disk recovery versus host availability; production hosting needed |
| Existing close competitors | Weak novelty/commercial pitch | Demonstrate inspectable recovery; do not claim category invention |
| Social-housing evidence generalized to lettings | Unsupported market claim | Separate evidence population from buyer hypothesis; interviews/pilot |
| Legal rules change or differ by tenure/nation | Incorrect deadline/safety claims | No regulatory engine; qualified review before production |
| Audio/transcripts contain personal data | Exposure/retention risk | Consent, synthetic identity, protected evidence, short retention and deletion procedure |
| One-day scope overflow | Incomplete demo | Follow cut order; retain core invariants and honestly report unmet voice gate |

## Organizer confirmation worksheet

| Question | Status | Evidence to record |
|---|---|---|
| Exact date/timezone/location | User-provided date; page extraction incomplete | Registration confirmation |
| Team size/solo eligibility | UNKNOWN | Organizer statement |
| Pre-event docs/code/templates allowed | UNKNOWN | Written/on-site rule |
| Submission platform and deliverables | UNKNOWN | Official instructions/link |
| Demo time and judging rubric | UNKNOWN | Official instructions |
| Sponsor-specific challenges/prizes/mandatory usage | UNKNOWN | Prize rules |
| Credits by provider/model and expiration | UNKNOWN | Credit redemption details |
| Simulated integrations permitted | UNKNOWN | Organizer statement |
| Repository visibility/IP/licence requirements | UNKNOWN | Event rules |

Do not fill these fields with speculation. No special sponsor prize is assumed in the architecture.

## Product questions for a real pilot

- Who owns coordination authority: agency, landlord, repairs desk or outsourced service?
- Which actions can be authorized in advance, at what limits and for which suppliers?
- Which system must remain the work-order/financial system of record?
- How are access, vulnerabilities, complaints and out-of-hours emergencies handled today?
- How often are multi-trade dependencies actually missed, and what share is addressable by software?
- What do incumbent tools already automate for that customer?
- What evidence is required to accept scaffold handover, completion and resident resolution?
- Will managers trust bounded execution after shadow-mode results, and at what price?

No interview, willingness-to-pay validation, measured ROI, production security review or vendor hands-on evaluation has been completed.

## Integration unknowns to close during implementation

Exact installed SDK versions; Gemini account quota; ElevenLabs plan/region/retention and webhook settings; supported browser session credential method; provider payload samples; audio MIME/availability timing; actual voice/search unit costs; callback delivery under venue network conditions. Official APIs establish feasibility, not successful configuration in this user's account.

## Decision log format

For material changes append: date/time, decision, reason/evidence, affected canonical documents, behavior change, verification performed and remaining risk. Update callers and tests with the contract; do not let an implementation-only workaround become undocumented architecture.

## Implementation status, 2026-09-19 (Phases 0–2 complete)

**Platform actually installed:** Python 3.12.13 (installed via `uv`; the host's system Python was 3.14, which is not what docs/04/21 specify, so 3.12.13 was provisioned explicitly rather than silently building against 3.14). Node v24.14.1 / npm 11.11.0 for the frontend. `uv` 0.11.32 as the backend package/venv manager (`backend/pyproject.toml` + `backend/uv.lock`).

**Backend packages actually installed and locked** (`backend/uv.lock`): fastapi 0.141.1, uvicorn 0.53.0, sqlalchemy 2.0.54, alembic 1.20.0, pydantic 2.13.5, pydantic-settings 2.15.0, aiosqlite 0.22.1, httpx 0.28.1, pydantic-ai-slim 2.46.0 (with the `google` extra: google-genai 2.24.0, pydantic-graph 2.46.0), pytest 9.1.1, pytest-asyncio 1.4.0.

**Gemini model name confirmed available in the installed SDK's type literal**, not confirmed against a live account: `gemini-3.8-flash` appears in `pydantic_ai.models.google.GoogleModelName`'s `Literal[...]` in pydantic-ai-slim 2.46.0, alongside `gemini-3.7-flash` (the documented fallback) and newer previews. `Agent(GoogleModel("gemini-3.8-flash", provider=GoogleProvider(api_key=...)), deps_type=..., output_type=ToolOutput(ActionProposal), ...)` constructs successfully against the project's actual discriminated-union `ActionProposal` schema with a placeholder (non-live) API key — this only proves the tool/output schema is constructible, not that a live model call round-trips it correctly. **No `GEMINI_API_KEY` is present in this environment**; the phase-0 live smoke test from docs/21 has not been run. Phase 3 uses Pydantic AI's `TestModel`/`FunctionModel` for deterministic, credential-free coordinator tests instead, per docs/22.

**No `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, or `TAVILY_API_KEY` is present in this environment**, and none is expected to become available during this implementation session. Per docs/21's cut order and docs/11's explicit instruction, the build continues on the runnable FIXTURE path; the live ElevenLabs recording/transcript acceptance gate (docs/11, docs/22) and the live Tavily research gate (docs/12) will be reported as **UNMET** with this exact blocker at completion, not silently skipped or claimed. A separate, unrelated `.mcp.json` entry pointing at ElevenLabs' hosted MCP server exists in the repo root — that is Claude Code developer tooling only (added in an earlier session) and is explicitly not part of the application's own ElevenLabs integration architecture (docs/09, CLAUDE.md: "MCP infrastructure... excluded").

**Hero path verified deterministically, not yet with live reasoning.** See docs/26's 2026-09-19 entry for the full test/behavior record.

## Implementation status, 2026-09-19 (Phase 6 complete: Tavily research)

**No new dependency required.** `TavilyResearchAdapter` (`backend/app/integrations/tavily.py`) uses `httpx` 0.28.1 directly (already pinned `>=0.28.1`), matching docs/12's stated preference for a custom wrapper over `pydantic_ai.common_tools.tavily.tavily_search_tool`.

**No `TAVILY_API_KEY` is present in this environment** — confirmed still true, unchanged from the earlier entry above. `TavilyResearchAdapter` is fully code-complete (real `POST https://api.tavily.com/search` call, bearer auth, domain-deduplicated candidate mapping, tri-state emergency-claim detection, docs/12's 8-second/one-retry budget) and tested end-to-end against a stubbed `httpx.MockTransport` (real request/response object handling, no socket), but has never been exercised against the live Tavily API. Tavily is explicitly SHOULD-HAVE per CLAUDE.md, not a hard acceptance gate like ElevenLabs voice — this is reported as an honest gap, not a blocking failure. `main.py`'s lifespan only constructs `TavilyResearchAdapter` when `settings.tavily_live` (i.e. a real key is present); with no key, the worker keeps using the always-available `FixtureResearchAdapter`, exactly as it did before this phase.

**One real, previously-undiscovered bug found and fixed in already-existing Phase 4 code** while adding the first-ever test coverage for `DISCOVER_CONTRACTORS`: `executor._apply_research_result` passed raw Pydantic `UUID` objects into an ORM string column and a `CaseEvent.payload` dict, which crashes on flush (`TypeError: Object of type UUID is not JSON serializable`) the moment any research adapter — fixture or live — actually completes a search. See docs/26's 2026-09-19 Phase 6 entry (clarification 12) for the full explanation and fix. This means Phase 4's own claimed test coverage never actually exercised this code path; recorded here as a gap in that earlier verification, now closed.

## Implementation status, 2026-09-19 (Phase 5: ElevenLabs voice code path)

**No new backend package dependency was needed.** `httpx` (already a dependency since Phase 0) covers the REST calls to ElevenLabs' `get-signed-url`, conversation-details and conversation-audio endpoints. Attempting to install the official `elevenlabs` Python SDK (only to read its webhook-verifier source, not as a runtime dependency) failed on this Windows environment with an `OSError` on a vendored file path exceeding Windows' 260-character `MAX_PATH` limit — a machine/OS constraint, not a version or dependency-resolution problem. The partially-installed package was removed; see docs/26's Phase 5 entry (clarification 10) for the full account and the resulting decision to implement webhook signature verification against the documented external convention ElevenLabs' own docs describe following, rather than the SDK's exact (unpublished-in-prose) implementation.

**No live `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, `ELEVENLABS_WEBHOOK_SECRET`, or `ELEVENLABS_TOOL_SECRET` exists in this environment.** Every code path docs/11 requires is implemented — signed browser session creation, session bind/ended lifecycle, the signed post-call webhook (transcription/audio/initiation-failure handling, duplicate-delivery idempotency, unmapped-conversation quarantine), the three dedicated-secret server tools (intake/observations/context), and the `FETCH_RECORDING` reconciliation job (transcript/outcome/audio persistence, gap-filling semantics) — and is exercised by 26 real deterministic tests (`backend/tests/test_voice.py`) using synthetic HMAC signatures and a monkeypatched network boundary. **The docs/11 live acceptance gate itself (real participant phrase, real audio playback, restart survival, replay-safety, all against the actual ElevenLabs API) is UNMET.** The exact blocker is the absence of credentials in this environment, not an unimplemented code path. Before any live demo: (1) verify the webhook signature format against one real delivery (see docs/26 clarification 10 — this is the one piece of the implementation built against a documented convention rather than a confirmed spec), (2) confirm the exact JSON field names `map_transcript`/`map_outcome` in `app/integrations/elevenlabs.py` expect from a real `GET /v1/convai/conversations/{id}` response (also written defensively against docs/11's prose description, not a captured payload), (3) configure audio saving/retention on the ElevenLabs agent per docs/11 ("Provider recording is configurable, not something to assume").

## Correction, 2026-09-19: real Gemini and partial ElevenLabs credentials appeared mid-implementation

The two "no credentials in this environment" statements above (Phase 0-2 entry and the Phase 5 entry immediately preceding this one) were true when written and are now partly superseded. The user added real `GEMINI_API_KEY` and `ELEVENLABS_API_KEY` values to `backend/.env` (gitignored, never committed) during Phase 4/7 UI work, and supplied an existing ElevenLabs agent ID (`agent_1001m1vtyfqpezma1p9yxs3shy79`), which was set as `ELEVENLABS_AGENT_ID`.

**Gemini live path verified for real, not just constructible.** With `readiness` reporting `gemini_live: true`, a demo intake was submitted through the real running API. The background worker's `COORDINATE` job invoked the real `GeminiCoordinator` (not `FixtureCoordinator`) against `gemini-3.8-flash`. It correctly proposed `ApplyTriage` with a coherent, context-specific scope description synthesized from the free-text intake ("Inspect the roof above the rear bedroom to identify and repair the source of water ingress causing the ceiling stain."), which was admitted without approval (all safety answers known-safe) and executed, creating a `READY` `REPAIR` work order — real end-to-end round trip in ~22 seconds. A second real coordinate call then correctly proposed `Wait` (no tenant availability windows exist yet to schedule against) rather than inventing one — exactly the conservative behavior the safety design requires. **The docs/13 Gemini live acceptance gate is MET.** This also surfaced a real gap: `GET /cases/{id}/runs` returned an empty list despite two real coordinator invocations, because `dispatcher.run_coordinate` never persists an `OrchestrationRunModel` row — being fixed as part of this correction (see docs/26).

**ElevenLabs is partially configured, not fully live, and the user has explicitly said full live ElevenLabs configuration is not required for this MVP.** `ELEVENLABS_API_KEY` and `ELEVENLABS_AGENT_ID` are both set (so `settings.elevenlabs_live` is `True`), but `ELEVENLABS_WEBHOOK_SECRET` and `ELEVENLABS_TOOL_SECRET` remain unset, and the referenced agent's prompt/dynamic-variables/webhook configuration is an unrelated outbound appointment-confirmation script for a different persona ("Accenture"/"Ava"), not RepairFlow's intake flow — reconfiguring it via the ElevenLabs API/MCP would also change what real inbound callers to that agent's live Twilio number hear, which is out of scope for a local MVP demo. Per explicit user instruction, this was deliberately not pursued further: no tunnel was built, no webhook was registered, and the agent was not modified. The docs/11 live *voice call* acceptance gate (signed session -> real audio -> real transcript -> real webhook) therefore remains **UNMET by product decision, not by missing implementation** — the code path built in Phase 5 is real and tested; only the operational wiring to this specific external agent was intentionally skipped.

**Tavily**: `TAVILY_API_KEY` was not provided and remains empty; `TavilyResearchAdapter` stays code-complete-but-live-untested exactly as the Phase 6 entry above describes.

**Housekeeping bug found while investigating why `GET /cases/{id}/runs` was empty:** `backend/.env`'s `DATABASE_PATH=backend/data/repairflow.db` is a relative path, and `pydantic-settings` resolves it relative to the process's current working directory, not `backend/`. `config.py`'s own default (`BACKEND_DIR / "data" / "repairflow.db"`) is correctly anchored regardless of cwd. Because uvicorn was started from within `backend/` during this session, the relative override resolved to `backend/backend/data/repairflow.db` — a duplicated-path directory that silently diverged from the `data/` directory `.gitignore` and prior smoke tests assumed. Fix: removed the `DATABASE_PATH`/`RECORDINGS_DIR` overrides from `.env`/`.env.example` and rely on the anchored defaults; documented that the run command in the README must specify the working directory explicitly.
