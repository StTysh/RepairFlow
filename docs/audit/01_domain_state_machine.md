# 01 — Domain engine and state-machine audit

Scope: `backend/app/domain/` (transitions, policy, services, errors, dependencies), `backend/app/models.py`, `backend/app/schemas.py`, plus the orchestration/executor/agent call sites that determine whether the domain layer's invariants actually hold at runtime (`orchestration/dispatcher.py`, `orchestration/executor.py`, `orchestration/worker.py`, `agents/coordinator.py`, `api/cases.py`, `api/voice.py`, `api/approvals.py`). Read-only; no source edited; nothing run against `backend/data/repairflow.db`.

Method: full read of `domain/transitions.py`, `domain/services.py` (1598 lines), `domain/policy.py`, `domain/errors.py`, `domain/dependencies.py`, `orchestration/executor.py`, `orchestration/dispatcher.py`, `orchestration/worker.py`, `orchestration/dedupe.py`, `agents/coordinator.py`, plus targeted reads of `api/cases.py`, `api/voice.py`, `api/approvals.py`, `api/errors.py`, `api/deps.py`, and relevant `schemas.py`/`models.py` sections. Two findings (the approval race and the FK/insert-order side-investigation) were verified with throwaway scripts against a temp-file SQLite DB under the system scratchpad dir (never `backend/data/`), using the app's real `session_scope()`/`decide_approval` code paths — not the on-disk demo DB.

## Verdict on the six named bugs

| # | Bug as named | Verdict |
|---|---|---|
| 1 | ESCALATED/CANCELLED cases do not halt automatic execution | **CONFIRMED** — Finding 1 |
| 2 | RESOLVED → ESCALATED broken (hazard after resolution cannot re-escalate) | **CONFIRMED, but relocated** — the state-machine edge and `escalate_to_human` are *not* broken; the deterministic pre-model hazard gate is. Finding 2 |
| 3 | `execute_action` can stick at RUNNING if the executor raises between lease and terminal write | **CONFIRMED** — Finding 3 |
| 4 | Service paths that commit rows written before a `DomainError` is raised | **SUSPECTED only, no reachable trigger found** — see Finding 9 |
| 5 | Lost-update race on double-submitted approvals | **CONFIRMED, reproduced live** — Finding 4 |
| 6 | `create_voice_session` returns 202 on provider failure | **CONFIRMED** — Finding 7 |

---

## CONFIRMED findings

### 1. ESCALATED/CANCELLED cases do not halt automatic execution
**Severity: CRITICAL** — `backend/app/orchestration/dispatcher.py:110`

```python
if policy.is_hazard(risk) and case.status not in ("ESCALATED", "CANCELLED", "RESOLVED"):
    ...
    return None
```

This is the **only** case-status check anywhere in `run_coordinate`, `admit_proposal` (executor.py), or `execute_action`. It fires only when a hazard is present, purely to avoid re-emitting a duplicate `CASE_ESCALATED` event. There is no unconditional `if case.status in (ESCALATED, CANCELLED): return None` anywhere in the coordinate path.

**Failure scenario**: case is ESCALATED (e.g. an earlier trade-change or loop-budget escalation, no hazard involved). Tenant calls back with a new, non-hazardous fact. `services.record_observations` (services.py:344-439) updates the issue and unconditionally calls `enqueue_job(..., kind=JobKind.COORDINATE, ...)` — it never checks `case.status`. The worker picks up the job, `run_coordinate` loads the case, `is_hazard(risk)` is `False` so the whole guard is skipped, the loop-budget check passes, and `coordinator.decide()` is invoked with a live ESCALATED-case snapshot. Any proposal that doesn't need approval (`Wait`, `RequestInformation`, etc., per `_needs_approval` in executor.py:131-147, which also never checks case status) is auto-admitted and auto-executed via `EXECUTE_ACTION`. This directly contradicts docs/19: "An escalated case retains all work orders and pending commitments... Stopping the coordinator does not cancel external work" and CLAUDE.md's "Architectural rules" bullet on ESCALATED/CANCELLED halting automation.

**Smallest fix**: in `dispatcher.run_coordinate`, before the hazard check, add:
```python
if case.status in (CaseStatus.ESCALATED, CaseStatus.CANCELLED):
    return None
```

### 2. Hazard on a RESOLVED case is not deterministically gated before the model call
**Severity: CRITICAL** — `backend/app/orchestration/dispatcher.py:110` and `backend/app/domain/services.py:344-439` (`record_observations`)

The low-level mechanism is *not* broken: `transitions.py`'s `_CASE_EDGES` permits `RESOLVED -> {ACTIVE, ESCALATED}` (matches docs/07 exactly), and `escalate_to_human` (services.py:967-981) explicitly includes `CaseStatus.RESOLVED` in its guard and calls `assert_case_transition` successfully. The actual defect is one level up: `dispatcher.py:110`'s hazard gate deliberately **excludes** `RESOLVED` from the condition that triggers deterministic escalation (`case.status not in ("ESCALATED", "CANCELLED", "RESOLVED")`), and `record_observations`, when it records a new `gas`/`fire`/`water_near_electrics`/`structural_danger`/`uncontrolled_flood` fact (the `safety_fields` branch, services.py:382-386), never itself calls `policy.is_hazard` or escalates — it only updates `case.risk` and enqueues a `COORDINATE` job.

**Failure scenario**: case is RESOLVED. Tenant later reports "actually there's a gas smell now" via a follow-up call. `record_observations` sets `risk.gas = YES`, enqueues `COORDINATE`. `run_coordinate` loads the case (`status=RESOLVED`), `is_hazard(risk)` is `True`, but `case.status not in (..., "RESOLVED")` is `False`, so the whole deterministic-escalation branch is skipped — the run falls straight through to `coordinator.decide()`, invoking Gemini with a live hazard on record and no safety pause. This violates docs/19's "Use an immediate in-call safety tool path; do not wait for post-call analysis" and CLAUDE.md's "Hazard answers must pause automation before any model call."

**Smallest fix**: drop `"RESOLVED"` from the exclusion tuple at dispatcher.py:110 (only `ESCALATED`/`CANCELLED` need it, to avoid a duplicate escalation event on an already-escalated case).

### 3. `execute_action` leaves the action stuck at RUNNING when Phase B/C raises
**Severity: HIGH** — `backend/app/orchestration/executor.py:348-360`, `:363-420` (`_apply_schedule_result`), `:423-458` (`_apply_research_result`)

Phase A commits `action_record.state = ActionState.RUNNING.value` (lines 326-329 for `ScheduleVisit`, 331-334 for `DiscoverContractors`) inside its own `session_scope()`. Everything after that — the call to `mock_booking_connector.book`/`research_adapter.search`, and the whole body of `_apply_schedule_result`/`_apply_research_result` — has **no try/except at all**. Any exception (adapter failure, or `assert_work_order_transition(work_order.status, WorkOrderStatus.SCHEDULED)` at line 380 raising `PolicyRejectedError` because the work order is no longer `READY` by the time this later, separate transaction runs) propagates uncaught through `execute_action` to the worker. `worker.process_one_job`'s except block marks the **job** `FAILED` (no retry for `EXECUTE_ACTION`, unlike `COORDINATE`) but never touches the `ActionRecordModel`, which stays at `RUNNING` forever. There is no reconciliation sweep for stuck `RUNNING` actions (contrast `worker.sweep_stale_live_calls`, which exists for stale voice calls but has no analogue here).

**Concrete trigger**: an operator cancels the work order (`services.cancel_appointment`) in the window between Phase A's `if work_order.status != WorkOrderStatus.READY: raise` check and Phase C's write — entirely plausible since Phase B is a real (simulated) network-shaped round trip.

**Smallest fix**: wrap the body of `_apply_schedule_result`/`_apply_research_result` (and the adapter calls in `execute_action`'s Phase B) in try/except that writes a terminal `FAILED`/`UNKNOWN` `CommandResult` onto the `ActionRecordModel` before returning/re-raising, mirroring the try/except already present around Phase A's `_dispatch_local` call.

### 4. Double-submitted approval crashes with an unhandled 500; only an incidental UNIQUE constraint prevents silent double-processing
**Severity: HIGH — reproduced live** — `backend/app/orchestration/executor.py:188-230` (`decide_approval`), `backend/app/api/errors.py` (no handler for non-`DomainError` exceptions)

`decide_approval` is a plain check-then-act: `if action_record.state != ActionState.AWAITING_APPROVAL.value: raise PolicyRejectedError(...)` with no DB-level compare-and-swap. `RepairCaseModel` has no `version_id_col` (checked `models.py`); `bump_version` is a bare `case.version += 1` in Python, and the state write is an ordinary ORM UPDATE with no `WHERE state = 'AWAITING_APPROVAL'` guard.

**Reproduced**: two concurrent `decide_approval` calls for the same `action_id` (`asyncio.gather`, two independent `session_scope()`s, exactly mirroring two concurrent HTTP requests through `api/deps.get_session`) both read `state=AWAITING_APPROVAL` before either commits. The first commits cleanly (`case.version` 5→6). The second's own `append_event` call fails:
```
sqlite3.IntegrityError: UNIQUE constraint failed: case_events.case_id, case_events.source_event_key
```
because both computed the identical deterministic key `f"approval:{action_record.id}:approved"` (executor.py:224). This exception is **not** a `DomainError`, so `api/errors.py`'s `_domain_error_handler` never catches it — it becomes a raw, unhandled HTTP 500 instead of a clean conflict response. (The transaction *does* roll back atomically — no corrupted rows were left behind in this repro — but the operator-facing failure mode is a crash, and this is happening on the approval path that gates real spend/booking authority.)

**Smallest fix**: use a conditional `UPDATE action_records SET state=... WHERE id=... AND state='AWAITING_APPROVAL'` and check `rowcount`, raising a clean `ConflictError` on 0 rows affected — instead of read-then-write.

### 5. `apply_triage`'s trade-changed branch corrupts `resume_status` on an already-ESCALATED case
**Severity: HIGH** — `backend/app/domain/services.py:553-557`

```python
elif existing_wo.trade != action.suggested_trade and existing_wo.status != WorkOrderStatus.READY:
    case.resume_status = case.status
    assert_case_transition(case.status, CaseStatus.ESCALATED)
    case.status = CaseStatus.ESCALATED
```

This is exactly the "`assert_case_transition` permits self-transitions" trap the audit was asked to hunt for. The hazard branch a few lines above (services.py:512-517) is correctly guarded with `if case.status in (CaseStatus.ACTIVE, CaseStatus.AWAITING_CONFIRMATION):` before touching `resume_status`/`status`; `api/cases.py`'s `resume_case`/`cancel_case` both carry an explicit comment-documented self-transition guard. This branch has **no such guard**.

**Failure scenario** (reachable via Finding 1, which shows a `COORDINATE` job can still run against an ESCALATED case): case is already `ESCALATED` for reason A (`resume_status=ACTIVE`). A new `ApplyTriage` proposal arrives with a different `suggested_trade` while the existing work order isn't `READY`. `case.resume_status = case.status` executes first, **overwriting `ACTIVE` with `ESCALATED`**. Then `assert_case_transition(ESCALATED, ESCALATED)` hits `transitions.py`'s self-transition no-op (`if current == target: return`) — no error, `case.status = ESCALATED` is a harmless-looking no-op reassignment. Later, an operator calls `POST /cases/{id}/resume`; `cases.py:429` computes `target = case.resume_status or ACTIVE` = `ESCALATED`, and `assert_case_transition(ESCALATED, ESCALATED)` again no-ops — the endpoint returns 202 and logs a `CASE_RESUMED` event, but `case.status` never actually leaves `ESCALATED`. The case is now permanently stuck, silently, with a false-success resume.

No test in `backend/tests/` exercises this branch (grepped for `trade_changed_after_dispatch`/`resume_status`: no hits).

**Smallest fix**: guard the same way as the hazard branch: `if case.status not in (CaseStatus.ESCALATED, CaseStatus.CANCELLED): case.resume_status = case.status; ...`.

### 6. `vulnerability_concern` is collected but never enforced by policy
**Severity: MEDIUM** — `backend/app/domain/policy.py` (`is_hazard`, `has_unknown_critical_safety_fact`, `triage_requires_approval`, `work_order_requires_approval_to_schedule`, `report_acceptance_requires_approval`)

Grepped the whole `app/` tree for `vulnerability_concern`: it is written by `submit_intake`/`record_observations`/the `FACT_FIELD_ALLOWLIST`, and **never read** by any policy function. docs/19's mandatory matrix requires "Priority operator assessment; adapt communication" for this signal, and booking may continue "Only with explicit reviewed plan" — i.e. it should force the approval path, not the hard "No" of the other hazard rows, but it should force *something*. Currently nothing does: `triage_requires_approval` only checks `is_hazard`/`has_unknown_critical_safety_fact`/`urgency=="EMERGENCY"`, none of which look at `vulnerability_concern`; `work_order_requires_approval_to_schedule` only checks kind/quote/limit. A work order on a case with `vulnerability_concern=YES` can auto-triage and auto-book with no operator ever seeing a gate for it.

**Smallest fix**: add `risk.vulnerability_concern == Answer.YES` as a condition in `triage_requires_approval` (and/or a dedicated pre-booking check), forcing the approval docs/19 requires.

### 7. `create_voice_session` returns 202 (not a real failure) when ElevenLabs fails to issue a session
**Severity: MEDIUM** — `backend/app/api/voice.py:106-111`, `backend/app/api/errors.py:22`

```python
except httpx.HTTPError as exc:
    raise ExternalResultUnknownError(f"failed to obtain a signed ElevenLabs session: {exc}") from exc
```
`ToolErrorCode.EXTERNAL_RESULT_UNKNOWN` maps to HTTP **202** (`errors.py:22`), which is right for a genuinely ambiguous side effect like a booking request whose outcome is unknown (retry could double-book). Obtaining a signed WebSocket URL is not that: failure here is unambiguous — no session was created, the browser cannot connect. The client sees "202 Accepted" for what is actually a hard failure, and the durable `CommunicationModel` row created in Phase A (`state=REQUESTED`, committed *before* the network call) is left orphaned with nothing ever bound to it.

**Smallest fix**: raise a distinct error here (e.g. reuse `ProviderUnavailableError` → 503, or a new code) instead of `ExternalResultUnknownError`, reserving 202/`reconciliation_required` for genuinely ambiguous external side effects.

---

## SUSPECTED / lower-confidence

### 8. Full call transcript reaches the model unredacted (LOW / NIT)
`agents/coordinator.py`'s `_redact_snapshot` (lines 69-93) nulls `recording.media_path`, `tenant.phone_e164`/`email`, and contractor `contact_reference` (both `approved_contractors` and `assigned_contractor`) — the specific PII-shaped fields `CaseSnapshot` exposes. It does **not** touch `Communication.transcript` (`schemas.py:594`), which is embedded verbatim in every prompt via `_format_prompt`. Anything a tenant says on a call (potentially a spoken phone number, address, medical/accessibility detail) reaches Gemini unredacted. This is plausibly intentional — the coordinator needs transcript content to interpret what was said, and docs/19's redaction language is scoped to "generic logs/Logfire," not model input. Flagging as low-confidence rather than a clear violation of the audited contracts.

### 9. "Commits rows written before a DomainError" — architecturally possible, no reachable trigger found
`execute_action`'s Phase A wraps `_dispatch_local` in `try/except DomainError`, but the except branch does not roll back or use a savepoint before falling through to `session_scope()`'s commit — so if any dispatched command flushes a write and *then* raises, that write would survive a "REJECTED" result. I checked every `raise PolicyRejectedError/NotFoundError/...` site in `services.py` (19 sites) for a preceding `session.add`/mutation in the same function. Two candidates exist — `add_prerequisite`'s cycle checks at services.py:623 and :644, which run after `session.add(prerequisite_wo)`/`session.add(removal_wo)` + `flush()` — but tracing `dep_graph.would_create_cycle`/`reaches` shows both are structurally unreachable: the row being checked is always a **freshly minted UUID** created two lines earlier in the same function, so it cannot yet appear in any existing `DependencyModel` edge, and `reaches()` can therefore never find it. Every other raise site precedes any write. The architectural gap (no savepoint boundary) is real and would bite if a future change added a raise after a write anywhere in the dispatch tree, but I found no live path that hits it today — SUSPECTED/architectural only.

---

## Checked and found correct

- **Transition graphs**: `transitions.py`'s `_CASE_EDGES` and `_WORK_ORDER_EDGES` match docs/07's two Mermaid diagrams **exactly**, edge-for-edge, including `RESOLVED → {ACTIVE, ESCALATED}` and `RESOLVED → ACTIVE`. No missing or extra edges either direction.
- `api/cases.py`'s `resume_case` (line 425) and `cancel_case` (line 475) both explicitly guard against `assert_case_transition`'s self-transition no-op being misused as a legal operator action (own inline comments confirm this was a deliberate prior fix); `reopen_case` needs no such guard since its own precondition (`status == RESOLVED`) can never equal its target (`ESCALATED`).
- `resolve_case` (services.py:929-964) correctly requires, all before any mutation: `case.status == AWAITING_CONFIRMATION`, an explicit (never silence-inferred) `issue.tenant_resolution_confirmed_at is not None`, empty `issue.unresolved_concerns`, every `required_for_resolution` work order `COMPLETED`, and no dependency edge with `status != SATISFIED`. A rejected resolve leaves no partial writes. Matches docs/07's "Case → RESOLVED" guard row and CLAUDE.md's "no closure inferred from silence."
- `apply_triage`'s hazard branch (services.py:512-517) and `escalate_to_human` (967-981) both correctly guard `case.status` before calling `assert_case_transition(..., ESCALATED)` — unlike Finding 5's trade-changed branch.
- Redaction of the specific fields `CaseSnapshot` carries that docs/19 names (phone numbers, contact references, media paths) is complete for tenant, `approved_contractors`, and `assigned_contractor`.
- `ScheduleVisit`'s local validation in `execute_action` Phase A (executor.py:283-325) performs every check (work order `READY`, contractor `APPROVED`, slot exists, cited availability actually covers the slot) before the first write (`action_record.state = RUNNING`) — a rejected proposal here leaves no partial writes.
- Version/expected-version checks are present and correct on `admit_proposal` (vs. `ActionProposal.expected_case_version`), `decide_approval` (vs. `ApprovalDecision.expected_case_version`), and `api/cases.py`'s case-edit/`resume_case`/`cancel_case` endpoints (vs. request `version`).

---

## Repro artifacts
Throwaway scripts used to verify Findings 4 and dead-code status of Finding 9's candidate triggers live under the session scratchpad dir (`race_repro.py`, `race_repro2.py`), against temp-file SQLite databases created via `tempfile.mkstemp`. Nothing was run against `backend/data/repairflow.db`; no source file was modified.
