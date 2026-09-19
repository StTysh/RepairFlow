# 22 — Verification strategy

No application tests have been run in this documentation phase. This file defines future gates, not claimed passing results.

## Test stack and separation

Use pytest + pytest-asyncio for domain/worker/adapters, FastAPI's HTTP test client for routes, and one Playwright browser hero test. Default tests use isolated temporary SQLite files, an injected clock, fixture model outputs and deterministic mock connectors. Never make paid calls or contact real people from the default suite.

Real-provider tests are explicit opt-in integration checks with consenting/allowlisted test participants. Record provider/model/SDK versions and observed results. Pydantic AI's test models and function-model facilities can control model behavior in unit tests. [Testing guidance](https://pydantic.dev/docs/ai/guides/testing/).

## Critical deterministic matrix

| Test | Required assertion |
|---|---|
| Failed roof visit | Appointment FINISHED/BLOCKED; original issue unresolved; roof order BLOCKED |
| New prerequisite | Correct edge direction; installation and required removal created once |
| Duplicate discovery | Same report produces no second scaffold order/edge |
| Cycle/wrong case | Transaction rejected; no partial writes |
| Completion | Accepted scaffold evidence satisfies edge and makes roof READY |
| Multiple blockers | One satisfied edge does not unblock while another remains OPEN/INVALIDATED |
| Removal obligation | Roofing completion releases removal; case cannot close while removal outstanding |
| Positive closure | All required orders completed plus explicit tenant confirmation resolves |
| Negative/absent confirmation | Still leaking, silence or unknown response cannot resolve |
| Late contradiction | Preserve report, pause/review; do not silently overwrite previous facts |
| Hazard | Immediate escalation and zero scheduling side effects |
| Approval | Exact payload/hash/limit; changed scope invalidates old approval |
| Duplicate booking | One persisted reservation and one appointment per action identity |
| Ambiguous booking timeout | UNKNOWN, no blind retry or second booking |
| Availability | Explicit aware dates; slot fits window; expiry/revision enforced; BST display correct |
| Stale proposal | New webhook while model runs causes stale action rejection and fresh wake |
| Restart while blocked | New process reloads graph, history and waiting job; completion resumes |
| Expired lease | Reclaims safe jobs; reconciles uncertain external actions |
| Timer after closure | No contact/action after resolution |
| Root-loop budget | Six consequential actions maximum; repeated WAIT never spins |

Crash tests should interrupt at meaningful boundaries: after intent commit/before send, after mock reservation/before result persist, and after event/job commit/before acknowledgment. In SQLite, mock reservations can reconcile deterministically by idempotency key.

## Voice adapter and recording tests

Fixture contract tests cover valid/invalid signature, duplicate delivery, new envelope fields, missing analysis, empty transcript, user/agent roles, initiation failure, out-of-order binding, unknown token/case scope, and missing audio flags. Use a synthetic audio fixture only to test storage/serving; it does not prove a live recording.

Live gate from 11: participant supplies an unseeded phrase and dated availability; backend stores the actual speaker-labelled transcript and audio; playback includes the phrase; outcome links to one case; coordinator uses the information; restart preserves it. Save a test record containing communication/conversation IDs, timestamps, audio digest/size and pass/fail status without copying private speech into general logs.

Test missing/disabled audio saving explicitly: show UNAVAILABLE/FAILED, never AVAILABLE with a blank player. A transcript-only call is an incomplete integration. Test authenticated recording access and no public static path.

## Model evaluation

Use a small authored dataset of 10–15 reports, including:

1. Explicit scaffold prerequisite.
2. Paraphrased safe-access requirement.
3. No access because tenant absent — must not invent scaffold.
4. Leak probably from plumbing — uncertainty/trade review.
5. Completed roof work with clear evidence.
6. “Work done” but access/remaining concerns contradictory.
7. Tenant confirms still leaking.
8. Gas/electrical hazard.
9. Prompt injection inside contractor report.
10. Prerequisite already exists — no duplicate action.

Assert typed action kind, correct referenced IDs/evidence and forbidden-action absence. Do not demand an exact prose rationale. Run each key paraphrase more than once to expose variability; report counts and failures rather than an unsupported accuracy claim. Pydantic Evals is optional organization tooling. [Evals](https://pydantic.dev/docs/ai/evals/evals/).

## Frontend/E2E

One browser test follows intake → simulated first visit → model/fixture prerequisite → approval → accepted installation → automatic roof rebooking → completion/removal → tenant confirmation. Assert persisted state and rendered labels, not animation timing. A separate manual live-call run checks microphone/audio and external callbacks, which a fixture E2E cannot establish.

Manual presentation check: readable at laptop resolution, graph direction obvious, evidence drawer usable, no secret/PII in diagnostics, keyboard-accessible approval, all provenance labels present.

## Exit criteria

Critical deterministic tests and one clean E2E pass; one real Gemini semantic run and one real recorded ElevenLabs call pass; all mocked surfaces disclosed; missing optional Tavily/Logfire does not block core completion. An unavailable required provider is a reported unmet live gate, not a green test achieved by fixtures.

Do not broaden testing for its own sake once these concrete risks are resolved. Preserve failing evidence and update 23/26 when implementation differs from the specification.
