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

_No implementation amendments yet._
