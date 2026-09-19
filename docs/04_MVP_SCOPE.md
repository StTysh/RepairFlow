# 04 — One-day MVP scope

## Build the recovery loop first

One property, one tenant, one active water-ingress issue, one coordinator, two primary trades. Use a safe fictional case with a known roof defect; do not infer that every ceiling leak requires a roofer.

The complete original scope is too large for one day. Target one live browser voice session, real model decisions, optional real search and simulated contractor operations. Telephone numbers, outbound contractor negotiation and production procurement are not needed to demonstrate the loop.

## Scope tiers

| Tier | Deliverables |
|---|---|
| MUST HAVE | Persisted case/events/jobs/actions; guarded coordinator; contractor-report ingestion; inferred scaffold prerequisite; block/unblock; simulated booking; required operator approvals; deterministic closure; visible graph/timeline; safe escalation; duplicate/restart tests |
| MUST HAVE live target | Gemini/Pydantic AI reasoning and one ElevenLabs browser intake conversation, with playable recorded audio, full transcript and structured outcome stored against the case; show explicit degraded mode if unavailable |
| SHOULD HAVE | Tavily search with source URLs; richer model/tool diagnostics; local replay; optional Logfire |
| NICE TO HAVE | Second browser conversation for confirmation; PSTN tenant call using already-provisioned number; source evidence drawer |
| POST-HACKATHON | Real contractor booking/outreach; email/calendar connectors; production authentication/multi-tenancy; PostgreSQL; robust workflow engine; multimodal evidence; regulatory deadline engine; broader trades |

Human approval and deterministic risk gates remain mandatory even when UI polish is cut.

## Minimum hero path

1. Seed property, tenant and fictional approved roofer/scaffolder.
2. Create case from browser voice or labelled captured intake.
3. Coordinator interprets the report and requests a roofing work order.
4. Availability is captured in the same intake to avoid an extra live call.
5. Mock connector confirms roofing appointment.
6. Operator injects a **simulated contractor observation**, not a state transition: safe roof access unavailable; scaffold required.
7. Live model proposes a prerequisite with evidence.
8. Executor atomically creates scaffold work and edge; roofing becomes BLOCKED.
9. Operator approves the simulated scaffold commitment.
10. Installation/handover observation completes the prerequisite; roofing returns to READY and is rebooked.
11. Simulated roofer completion releases the scaffold-removal follow-on.
12. Approve/book removal and accept its simulated completion; capture affirmative tenant confirmation. Early confirmation may be stored but never bypasses outstanding work.
13. Resolve only when the closure predicate passes.

Scaffold removal uses the same work-order machinery, with no extra integration. Keep it as a short final timeline event in the demo. If omitted for time, the case must stay open with “leak fixed; scaffold removal outstanding”—never silently claim complete operational resolution.

## Real versus simulated

| Surface | MVP truth |
|---|---|
| Model interpretation/action proposal | REAL API when configured; fixture substitute labelled |
| Browser microphone, voice and server tool | REAL ElevenLabs when configured |
| Incoming public telephone call | NOT core; browser voice is not PSTN |
| Tavily contractor search | REAL if enabled; otherwise a dated saved fixture |
| Agency/property/tenant records | SYNTHETIC |
| Contractor availability and reservations | SIMULATED IN MVP |
| Appointment attendance and site work | SIMULATED IN MVP |
| Tenant follow-up | Browser voice or explicit simulated observation |
| Backend restart and database persistence | REAL local behavior |
| Actual procurement, payments, emergency dispatch | NOT IMPLEMENTED |

Never attach a fictional calendar to a real contractor search result. The demo books named fictional preferred suppliers, while showing real search as an optional discovery branch.

## Fallback ladder and hard cuts

If a provider takes more than 25 minutes to configure, continue the core loop and return later. If telephony is not already working, cut it. If React Flow takes over 30 minutes, retain a fixed-position graph using the library's basic nodes. If Tavily is down, use a clearly labelled saved result. If Gemini is down, run fixture mode and disclose that the run was not live reasoning.

No mobile app, generic chat workspace, invoicing, payments, OAuth integrations, arbitrary browser automation, image diagnosis, embeddings, agent marketplace or generalized multi-agent framework.

## Demo acceptance

- Novel phrasing of the scaffold report produces the correct proposed dependency.
- Roofing stays unresolved after its failed visit.
- Duplicate report/completion causes no duplicate order or appointment.
- Restart while blocked preserves all state and resumes on the next event.
- Call results correlate to one case and communication.
- After an actual ElevenLabs test conversation, the application displays the speaker-labelled transcript, plays the captured audio and uses the caller's information in the next decision. A transcript fixture does not pass this live acceptance gate.
- Tavily queries, provider request IDs when supplied, returned sources and research results are recorded per case.
- Tenant says “still leaking” → no resolution.
- Gas/electrical-danger variant → human escalation, no booking.
- No fake live badge or fabricated savings.
