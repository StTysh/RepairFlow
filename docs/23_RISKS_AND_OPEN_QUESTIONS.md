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

## Implementation status, 2026-09-19 (Phase 5: ElevenLabs voice code path)

**No new backend package dependency was needed.** `httpx` (already a dependency since Phase 0) covers the REST calls to ElevenLabs' `get-signed-url`, conversation-details and conversation-audio endpoints. Attempting to install the official `elevenlabs` Python SDK (only to read its webhook-verifier source, not as a runtime dependency) failed on this Windows environment with an `OSError` on a vendored file path exceeding Windows' 260-character `MAX_PATH` limit — a machine/OS constraint, not a version or dependency-resolution problem. The partially-installed package was removed; see docs/26's Phase 5 entry (clarification 10) for the full account and the resulting decision to implement webhook signature verification against the documented external convention ElevenLabs' own docs describe following, rather than the SDK's exact (unpublished-in-prose) implementation.

**No live `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, `ELEVENLABS_WEBHOOK_SECRET`, or `ELEVENLABS_TOOL_SECRET` exists in this environment.** Every code path docs/11 requires is implemented — signed browser session creation, session bind/ended lifecycle, the signed post-call webhook (transcription/audio/initiation-failure handling, duplicate-delivery idempotency, unmapped-conversation quarantine), the three dedicated-secret server tools (intake/observations/context), and the `FETCH_RECORDING` reconciliation job (transcript/outcome/audio persistence, gap-filling semantics) — and is exercised by 26 real deterministic tests (`backend/tests/test_voice.py`) using synthetic HMAC signatures and a monkeypatched network boundary. **The docs/11 live acceptance gate itself (real participant phrase, real audio playback, restart survival, replay-safety, all against the actual ElevenLabs API) is UNMET.** The exact blocker is the absence of credentials in this environment, not an unimplemented code path. Before any live demo: (1) verify the webhook signature format against one real delivery (see docs/26 clarification 10 — this is the one piece of the implementation built against a documented convention rather than a confirmed spec), (2) confirm the exact JSON field names `map_transcript`/`map_outcome` in `app/integrations/elevenlabs.py` expect from a real `GET /v1/convai/conversations/{id}` response (also written defensively against docs/11's prose description, not a captured payload), (3) configure audio saving/retention on the ElevenLabs agent per docs/11 ("Provider recording is configurable, not something to assume").
