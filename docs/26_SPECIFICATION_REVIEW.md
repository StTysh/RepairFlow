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
