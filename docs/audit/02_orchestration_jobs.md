# Orchestration/Jobs Audit — durable pipeline

Scope: `backend/app/orchestration/` (dispatcher, worker, executor, dedupe), `backend/app/agents/`, and `JobModel`/`ActionRecordModel`/`OrchestrationRunModel` lifecycles. Read-only; server never started. Real DB (`backend/data/repairflow.db`) inspected via a throwaway copy in the scratchpad, never mutated.

## Severity counts
CRITICAL: 3 · HIGH: 3 · MEDIUM: 2 · LOW: 1 · NIT: 1

---

## CONFIRMED

### 1. CRITICAL — Unbounded FETCH_RECORDING retry storm; live in the real DB right now
`backend/app/orchestration/worker.py:148-176` (`sweep_stale_live_calls`) and `backend/app/integrations/elevenlabs.py:379-387` (`fetch_recording`'s `except httpx.HTTPError` branch).

`sweep_stale_live_calls` re-matches every `CommunicationModel` row with `state IN ('ACTIVE','REQUESTED')` and a non-null `provider_conversation_id` every `RECONCILE_SWEEP_INTERVAL_SECONDS` (5s), and enqueues a new `FETCH_RECORDING` job each time (dedupe key bucketed by `int(now // 5)`, so it *never* dedupes across sweeps — deliberate, per the code's own comment, to allow eventual retry). But `fetch_recording`'s network-failure handler only ever writes:
```python
except httpx.HTTPError as exc:
    async with session_scope() as session:
        comm = await session.get(CommunicationModel, communication_id)
        if comm is not None:
            comm.recording = Recording(status=RecordingStatus.FAILED, error_code=f"details_fetch_failed: {exc}"[:200]).model_dump(mode="json")
    return
```
It never sets `comm.state` to a terminal value (contrast with `place_call`'s own failure paths in the same file, which do set `comm.state = "FAILED"`). So a communication whose detail fetch keeps failing (or whose remote status never reaches a terminal value) stays `ACTIVE`/`REQUESTED` forever, and the sweep re-enqueues a fresh job for it every 5 seconds, indefinitely. There is no attempt cap on this path (unlike `MAX_COORDINATE_ATTEMPTS` for COORDINATE).

**Verified against the real database** (copied to scratchpad, not touched live): `jobs` has 5,618 rows total; **5,601 are `FETCH_RECORDING`, all status `DONE`, all `attempts=1`**. Split by `communication_id` (confirmed via `json_extract(payload,'$.communication_id')`, not assumed):
- `ac04cd4e-90be-4249-8c67-8c276822f240`: **3,795 rows**, `run_at` 2026-09-19T17:44:27 → 2026-09-20T00:50:36
- `94c933ee-1b26-4eb6-846b-65a06f233fbc`: **1,806 rows**, `run_at` 2026-09-19T21:38:30 → 2026-09-20T00:50:36

Both `communications` rows are still `state='ACTIVE'`, `recording.status='FAILED'`, `error_code="details_fetch_failed: [Errno 11001] getaddrinfo failed"` — a DNS failure (offline dev box reaching `api.elevenlabs.io`), so `fetch_conversation_details` raised on every single attempt for each, at ~5s cadence, for as long as the process ran. Each of these 5,601 jobs "succeeded" (job status DONE) while accomplishing nothing — the storm is invisible in job-failure metrics. (The task brief cited 5,508 rows; the DB has since grown to 5,601 — same live, ongoing mechanism, not a discrepancy.)

**Failure scenario:** any environment without live ElevenLabs network reachability (or any conversation whose detail fetch permanently errors, or whose remote status never reaches a terminal value) burns one job row + one outbound HTTP attempt every 5 seconds forever, for as long as the process runs. On restart the backlog is replayed head-of-line (Finding 5).

**Smallest correct fix:** in the `except httpx.HTTPError` branch (and in the "never reached a terminal remote status" no-op branch, past some retry bound), track failure count/age on the row and once a bound is hit, set `comm.state = "FAILED"` (terminal) so the sweep's `WHERE state IN ('ACTIVE','REQUESTED')` stops matching it, and raise a `CaseEvent`/operator-visible signal instead of silently no-op'ing.

---

### 2. CRITICAL — Two action-ledger states have no reconciliation path; a crash or a policy re-check failure strands them forever — including after the external write already happened
`ActionState.RUNNING` is set at `backend/app/orchestration/executor.py:326` (`ScheduleVisit`) and `:331` (`DiscoverContractors`), committed, and the session exits *before* the external call. `ActionState.UNKNOWN` is set at `executor.py:409` when a booking outcome comes back `PENDING`/`UNKNOWN`, explicitly flagged `reconciliation_required=True` in its own `ToolError`. Grepping the whole codebase for both states confirms neither is ever read back by any sweep or reconciler — the only other references are as "still in flight" filters (`services.py:1547`, `metrics.py:61`). There is no `RUNNING`/`UNKNOWN` analogue of `sweep_stale_live_calls`.

**Path A — mid-flight exception after a successful external write (no restart needed).** For `SCHEDULE_VISIT`, `_apply_schedule_result` (executor.py:363-420) calls
```python
assert_work_order_transition(work_order.status, WorkOrderStatus.SCHEDULED)  # line 380
```
*after* `mock_booking_connector.book()` has already run and committed in its own `session_scope()` (executor.py:351-352) — the reservation row and `slot.is_reserved=True` are already durably written. If the work order is no longer `READY` (operator cancelled it, or any concurrent path changed it between admission and Phase C), `assert_work_order_transition` raises `PolicyRejectedError` (`DomainError`), **uncaught here** (unlike Phase A of `execute_action`, lines 282-346, which does catch `DomainError`), and propagates out of `execute_action` entirely. The external booking **succeeded**; the ledger never learns of it.

**Path B — restart alone is sufficient, no concurrent writer required.** If the process crashes between the Phase-A commit (`action_record.state = RUNNING` at executor.py:326, already committed) and Phase C completing, the job row is left `LEASED`. `claim_job`'s expired-lease fallback (worker.py:59-63) reclaims it after `LEASE_SECONDS=120`, `execute_action` runs again, hits the re-entry guard (executor.py:270-274):
```python
if action_record.state != ActionState.PENDING.value:
    if action_record.result:
        return CommandResult.model_validate(action_record.result)
    return CommandResult(status=CommandResultStatus.NOOP, case_version=case.version)
```
`state == RUNNING`, `result is None` → returns `NOOP` and does **not** retry the booking. If the booking had already been committed by `mock_booking_connector.book()` before the crash, it's now a silent orphan; if it hadn't, the work order is now permanently un-schedulable through this action. This is exactly the "double-processing under a restart" scenario the task asked about — the record is stranded, not double-processed, but restart is the trigger either way.

**Compounding idempotency-key collision (item 3: two distinct actions colliding on one key — confirmed).** `_idempotency_key` for `ScheduleVisit` (executor.py:109-115) is `f"booking:{work_order_id}:{slot_id}:{count+1}"`, where
```python
count = (await session.execute(select(func.count()).select_from(AppointmentModel).where(AppointmentModel.work_order_id == str(action.work_order_id)))).scalar_one()
```
— this counts **all** `AppointmentModel` rows for the work order, with no status filter (not just confirmed ones). Because the stranded action above never created an `AppointmentModel` row at all, `count` stays exactly what it was before the stranding, so a *later, logically distinct* `ScheduleVisit` proposal for the same work order/contractor/slot computes the **identical** idempotency key. `admit_proposal` (executor.py:163-169) finds the existing (stuck) `ActionRecordModel`, compares `payload_hash`, finds it differs (different `trigger_event_id`), and raises `ConflictError` — permanently blocking any retry against that exact slot.

*(Other half of item 3 — can the same action produce two keys? Yes, in principle: two proposals racing on the same `count+1` before either commits could compute the same key from different logical attempts, or a retried proposal with a bumped `count` could get a different key than an in-flight one. In practice `mock_booking_connector.book`'s own slot-reservation check — booking.py:130-138, "slot already reserved" `REJECTED` — catches a genuine double-book of the same slot even if two different idempotency keys reach it, so this doesn't silently double-book; it degrades to a rejected second attempt instead.)*

Blast radius: `pending_actions` in the case snapshot (`services.py:1547`) includes both `RUNNING` and `UNKNOWN`, and `COORDINATOR_INSTRUCTIONS` (agents/instructions.py:34-35) tells the model "Use WAIT when a valid action is already outstanding... do not propose a duplicate of something already in flight" — so the coordinator will indefinitely WAIT on a case with a stranded action, believing scheduling/booking is progressing. The case silently stalls with no escalation. Not currently manifested in the sampled real DB (no `RUNNING`/`UNKNOWN` rows present there today — all 12 `action_records` are `SUCCEEDED` or `AWAITING_APPROVAL`), so this is code-confirmed, not data-confirmed.

**Smallest correct fix:** wrap `_apply_schedule_result`'s and `_apply_research_result`'s bodies in the same `try/except DomainError` pattern Phase A uses, terminalizing to `FAILED`/`UNKNOWN` with a `CommandResult` on any exception after a successful external call. Add a startup/periodic sweep for `ActionRecordModel.state IN ('RUNNING','UNKNOWN')` past a bound, mirroring `sweep_stale_live_calls`, that at minimum escalates rather than leaving the case silently WAITing.

---

### 3. CRITICAL — The worker loop can die silently; nothing restarts it or even logs it as a pipeline failure
`backend/app/orchestration/worker.py:97-101` (the claim block inside `process_one_job`) sits **before** the `try:` at line 103 — an exception from `claim_job` itself or from that `session_scope()`'s commit (e.g. SQLite "database is locked" under a concurrent HTTP write, a genuinely common occurrence, or any of Finding 4's unhandled `IntegrityError`s) is not caught by the `except Exception` at line 130, which only wraps lines 103-129. Separately, `run_worker_loop`'s own body (worker.py:197-215) has **no try/except anywhere**: `sweep_stale_live_calls()` at line 207 is called unguarded every 5s once ElevenLabs is configured, and per Finding 4's check-then-act race it can itself raise `IntegrityError` via `enqueue_job`.

Either exception propagates out of `run_worker_loop`, which is the coroutine handed to the bare `asyncio.create_task(...)` at `main.py:62`. Nothing awaits that task until shutdown (`await worker_task` at `main.py:74`), so the exception is not surfaced anywhere during normal operation — asyncio logs an unretrieved-task-exception warning at best, and the task simply stops. Every subsequent COORDINATE / EXECUTE_ACTION / FOLLOW_UP / FETCH_RECORDING / PLACE_CALL job in the database silently stops being processed for the remaining life of the process, with no supervisor, no restart, and no case-visible signal (cases just stop making progress).

**Smallest correct fix:** wrap the entire body of `run_worker_loop`'s `while` iteration (including the claim block inside `process_one_job` and the `sweep_stale_live_calls()` call) in a `try/except Exception` that logs and continues, matching the isolation `process_one_job` already gives individual job bodies.

---

### 4. HIGH — `PLACE_CALL` is the dangerous job kind on boot: item 8, answered
`backend/app/main.py:61-67` starts `run_worker_loop` unconditionally in `lifespan`, with no gate on what's already `PENDING`/`LEASED` in the database. Trace the cascade for a stale `COORDINATE` row surviving from a previous run: `admit_proposal`'s `_needs_approval` (executor.py:131-147) returns `False` for `RequestInformation` and `RequestConfirmation` — these are the only two `NextAction` kinds that reach a tenant by phone — so `EXECUTE_ACTION` is enqueued immediately with **no approval checkpoint** (executor.py:180-184). `_dispatch_local` routes both to `services.request_information`/`request_confirmation` (services.py:863-926), which each create a `CommunicationModel` row and unconditionally `enqueue_job(kind="PLACE_CALL", ...)` (services.py:884-888, 922-925). On the very next worker tick, `elevenlabs.place_call` (elevenlabs.py:218-300) runs and, if `settings.outbound_calls_enabled` and the resolved phone is on `settings.outbound_call_allowlist` (both are process-level config, not per-action operator confirmations), **places a real outbound PSTN call** with zero new operator action between the stale row existing and the phone ringing.

The real DB confirms this path fires in practice: 3 `PLACE_CALL` jobs, all `status='DONE'`, already exist in the sampled database (task history, not observed live by this audit). No `PENDING`/`LEASED`/`FAILED` rows of any kind exist in the current snapshot, so there is no *immediate* next-boot risk today — but the mechanism is structural: any future `COORDINATE`/`EXECUTE_ACTION`/`PLACE_CALL` row left `PENDING` at shutdown (crash, kill -9, the very worker-death scenario in Finding 3) will fire identically on the next boot. This is precisely why this audit's own instructions forbid starting the server, and it should be called out as the concrete reason, not left implicit.

**Smallest correct fix:** none needed for this audit's own execution (correctly avoided), but the architecture should not let a boot with a non-empty job queue reach a live outbound call without a fresh, explicit operator/demo-enable check at drain time — e.g. re-validate `outbound_calls_enabled`+allowlist at the moment of dequeue (already done) *and* surface/require acknowledgement of a non-empty PLACE_CALL/COORDINATE backlog before the worker starts draining it, per CLAUDE.md's "documented enable switch."

---

### 5. HIGH — Boot-time worker has no priority/backpressure; the FETCH_RECORDING backlog runs head-of-line ahead of new work
`backend/app/orchestration/worker.py:51-70` (`claim_job`) selects the single next `PENDING` job ordered only by `run_at` (then falls back to expired `LEASED` ordered by `lease_until`) — no `kind`-based priority. Given Finding 1's real backlog (thousands of `FETCH_RECORDING` rows with `run_at` far in the past whenever it recurs), on any restart against that database the worker dequeues and executes the entire backlog, one job at a time, strictly before any `run_at`-later `COORDINATE`/`EXECUTE_ACTION` job created after boot. Each iteration makes a real outbound HTTP attempt (15-30s timeout) to `api.elevenlabs.io`. Since there is exactly one worker loop (CLAUDE.md: "one backend worker/process"), this can stall all genuine new case activity for as long as the backlog takes to drain.

**Smallest correct fix:** cap what a single sweep can enqueue and/or give `claim_job` a per-kind fairness rule (e.g. round-robin by kind, or skip `FETCH_RECORDING` claims when a `COORDINATE`/`EXECUTE_ACTION` is due), paired with Finding 1's fix so the backlog stops growing in the first place.

---

## SUSPECTED

### 6. MEDIUM — `enqueue_job`/`admit_proposal`/webhook-receipt dedupe is check-then-act, not atomic; races surface as an unhandled `IntegrityError` rather than a graceful dedupe
`backend/app/domain/services.py:139-155` (`enqueue_job`):
```python
existing = (await session.execute(select(JobModel).where(JobModel.dedupe_key == dedupe_key))).scalar_one_or_none()
if existing is not None:
    return None
job = JobModel(..., dedupe_key=dedupe_key, ...)
session.add(job)
await session.flush()
```
`JobModel.dedupe_key` is `unique=True` (models.py:509) so data can't actually duplicate, but two concurrent callers (plausible: `enqueue_job` is invoked from multiple FastAPI request handlers — `api/cases.py`, `api/voice.py` — which can run concurrently under asyncio even in one process) racing between the SELECT and the flush will have the second raise `IntegrityError`, uncaught here, surfacing as a 500 instead of the intended "already enqueued, no-op" behavior. This is also Finding 3's second unguarded trigger: `sweep_stale_live_calls` calls `enqueue_job` with no try/except around it in `run_worker_loop`. The same check-then-act shape exists in `admit_proposal`'s idempotency-key lookup (`executor.py:163-169`, over `ActionRecordModel.idempotency_key`, also `unique=True` at models.py:489) and in `record_webhook_receipt` (`dedupe.py:36-58`, over the composite-unique `webhook_receipts` constraint). Not exercised in the real DB inspected (no evidence of an actual collision there), hence SUSPECTED rather than data-confirmed.

**Smallest correct fix:** catch `IntegrityError` around the flush/commit in each of these three call sites and re-SELECT-and-return-existing on conflict, or move to `INSERT ... ON CONFLICT DO NOTHING RETURNING`.

### 7. MEDIUM — `COORDINATE` retry exhaustion has no escalation path
`worker.py:130-145`: any exception from `dispatcher.run_coordinate` (model timeout, `UsageLimitExceeded`, a bug in a read tool, a transient DB issue) is retried up to `MAX_COORDINATE_ATTEMPTS=3` with a flat 5s delay, then `FAILED` with no further automatic path back — only a fresh *external* trigger creates a new COORDINATE job (new `dedupe_key`). Bounded (good, matches CLAUDE.md), but a persistently-misconfigured model (bad `GEMINI_API_KEY`, sustained provider outage) exhausts retries and leaves the case silently un-coordinated with no `Escalate`. Not verified against real data (no `FAILED` COORDINATE rows exist in the current DB to inspect) — worth confirming against docs/21's expectations for whether a terminally-`FAILED` COORDINATE job should itself raise an escalation.

---

## LOW / NIT

- **LOW** — `worker.py:206` only runs `sweep_stale_live_calls` when `elevenlabs_configured=True` at boot (a fixed snapshot of `settings.elevenlabs_live` taken once in `main.py`'s `lifespan`); this is consistent within a single process lifetime but means the sweep's on/off-ness is decided once at startup, not re-derived — worth a comment for the next reader, not a bug today.
- **NIT** — `dispatcher.py:81` bounds `_internal_chain_depth`'s walk at `depth <= 20` while `ROOT_LOOP_BUDGET=6`; the extra headroom is harmless (the `seen` set already guards the walk from an actual cycle) but the two unrelated numbers are worth a comment for the next reader.

---

## Checked and correct

- **No transaction held across model/network I/O in the core path.** `dispatcher.run_coordinate` (dispatcher.py:106-182): Phase A commits+closes before `await coordinator.decide(...)` (no session open at dispatcher.py:148); Phase C opens a fresh session afterward. `executor.execute_action`'s Phase A session closes (executor.py:266-346) before Phase B's `mock_booking_connector.book`/`research_adapter.search` calls (executor.py:349-358) — note `mock_booking_connector.book` is itself pure local DB work with no real network/sleep, so holding a session across *it* (executor.py:351-352) is not a violation. `TavilyResearchAdapter.search` (tavily.py) and `elevenlabs.place_call`/`fetch_recording` each open/close short `session_scope()`s around, never across, their `httpx` calls. `agents/read_tools.py` tools each open their own short session per call, and `agents/dependencies.py`'s docstring states this design intent explicitly.
- **"One action proposal per wake" is structurally enforced**, not just convention: the agent's `output_type=ToolOutput(ActionProposal)` (coordinator.py:52) makes a single typed `ActionProposal` the only possible run output; all five registered tools (`read_report`, `read_communication`, `list_case_events`, `find_appointment_options`, `read_research`) are read-only with no write path back into the domain, and `admit_proposal` is only ever called once per `run_coordinate` invocation (dispatcher.py:166).
- **`UsageLimitExceeded` (and any other `coordinator.decide` exception) is recorded, not swallowed**: dispatcher.py:147-155 marks the `OrchestrationRunModel` `FAILED` with `error_code=type(exc).__name__` and re-raises; worker.py's `process_one_job` (inside its `try`, unlike the claim block — see Finding 3) then records it into `JobModel.last_error` and applies the bounded COORDINATE retry.
- **`raise_on_error` is wired correctly for the code paths it covers**: production (`run_worker_loop`, worker.py:203) calls `process_one_job` with the default `False`; `drain_due_jobs` (test/dev helper, worker.py:179-194) exposes and forwards `raise_on_error` for tests to opt into. This only applies to the try-guarded body (worker.py:103-129) — it does not (and structurally cannot) cover the claim block or the sweep call, which is Finding 3.
- **`claim_job`'s lease/reclaim logic** (worker.py:51-70) is sound for the documented single-worker-process model: `PENDING & run_at<=now` first, then `LEASED & lease_until<now` as fallback, `attempts` incremented on every claim (including reclaims), `lease_until` set from a constant `LEASE_SECONDS=120` documented (worker.py:23-27) to exceed `RUN_TIMEOUT_SECONDS=120` for COORDINATE specifically so a live run's lease can't expire mid-flight.
- **Webhook idempotency** (`dedupe.py:30-58`, backed by `uq_webhook_receipt_identity` at models.py:438-441) correctly returns the original receipt with `is_new=False` on an exact-duplicate delivery, letting the webhook handler ack 200 without reprocessing.
- **MAX_MODEL_REQUESTS/MAX_TOOL_CALLS vs. registered tools**: 5 tools registered (coordinator.py:57-61), `MAX_TOOL_CALLS=8`, `MAX_MODEL_REQUESTS=10` — comment at coordinator.py:28-32 documents this was raised live after hitting `UsageLimitExceeded` with real cases; the ratio is plausible headroom, not obviously mis-sized.

---

**Top three:**
1. **CRITICAL** — Unbounded `FETCH_RECORDING` retry storm (worker.py:148-176 + elevenlabs.py:379-387): confirmed live in the real DB — 5,601 of 5,618 total job rows, split 3,795/1,806 across two never-terminalized `ACTIVE` communications, spanning ~3h/~7h at 5s cadence.
2. **CRITICAL** — The worker loop's own claim block and sweep call are unguarded (worker.py:97-101, 206-207): a single "database is locked" or a Finding-6 `IntegrityError` silently kills the entire orchestration pipeline for the rest of the process's life, with no restart and no case-visible signal.
3. **CRITICAL** — `ActionState.RUNNING`/`UNKNOWN` are true dead ends (executor.py:326-334, 409; no reconciliation anywhere): a restart alone, with no concurrent writer, can strand a record whose external booking already succeeded, and the `ScheduleVisit` idempotency key then permanently blocks retrying that exact work order/slot.

(Also load-bearing: Finding 4 answers item 8 directly — `PLACE_CALL` is the dangerous job kind on boot, reached from a stale `COORDINATE` row via an approval-free `RequestInformation`/`RequestConfirmation` cascade with zero fresh operator action, which is the concrete reason this audit's brief forbids starting the server.)
