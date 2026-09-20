# Audit 05: API Surface (all 58 routes)

Scope: every router under `backend/app/api/` (cases, approvals, observations, field_updates, metrics,
notifications, overview, properties, contractors, tenants, documents, notes, costs, messaging, insights,
reports, search, voice, deps, errors) as wired into `backend/app/main.py`. Read-only audit; no server
started, no `backend/data/repairflow.db` touched. All empirical checks ran through an in-process
`httpx.ASGITransport(app=app)` client against `app.main.app` (the real, fully-wired app, not a stub),
against an isolated temp SQLite file (`DATABASE_PATH`/`DOCUMENTS_DIR`/`RECORDINGS_DIR` redirected, same
pattern as `tests/conftest.py`'s `app_db` fixture), with `OPERATOR_AUTH_ENABLED=true` and
`FIXI_NO_CONTACT=1`.

## Severity counts

- CRITICAL: 0
- HIGH: 4
- MEDIUM: 3
- LOW: 2
- NIT: 1

## Top three

1. **HIGH — cross-case report misattribution.** `POST /api/v1/cases/{case_id}/reports` never validates
   that the submitted `work_order_id` actually belongs to the case named in the URL; the report is silently
   filed against whatever case the work order really belongs to. Confirmed by request/response below.
2. **HIGH — archival "read-only" cases can be reopened and cancelled.** `/cases/{id}/resume`,
   `/cases/{id}/reopen` and `/cases/{id}/cancel` are the only three case-mutating routes in `cases.py` that
   skip the `archive_batch_id is not None` guard every sibling route (`edit_case`, `update_property`,
   `update_contractor`, `delete_note`, `compose_message`, …) applies. Confirmed: reopened and then cancelled
   a synthetic archival sample case, producing real `CASE_ESCALATED`/`CASE_CANCELLED` events on a record
   documented as "read-only" and "can never be actioned."
3. **HIGH — attacker-controlled Content-Type is trusted verbatim and served back inline.** `POST
   /api/v1/documents` stores `file.content_type` (a client-supplied multipart header, not sniffed) as-is.
   `GET /documents/{id}/content` then serves it back with that same `Content-Type` and
   `Content-Disposition: inline` whenever it starts with `image/` — including `image/svg+xml`, which the
   browser will render and execute. Confirmed with a script-bearing SVG.

(A fourth HIGH — archival rows leaking into `/appointments/upcoming`, `/overview` and `/notifications` — is
documented below; it did not make the top three only because it required injecting data no current importer
produces, whereas the first three are reachable through the ordinary operator UI today.)

---

## Route table (73 method×path rows: 72 under `/api/v1`+`/webhooks`+`/integrations`, plus `/healthz`)

Auth key: **operator** = `Depends(require_operator)` (HTTP Basic, empirically confirmed to 401 with no
credentials under `OPERATOR_AUTH_ENABLED=true`); **signed** = ElevenLabs webhook signature; **secret** =
`Authorization: Bearer <ELEVENLABS_TOOL_SECRET>`; **none** = deliberately public.

| Method | Path | Auth | Archival-aware | Verdict |
|---|---|---|---|---|
| GET | /healthz | none | n/a | OK — no state exposed |
| GET | /api/v1/readiness | operator | n/a | OK |
| GET | /api/v1/cases | operator | **yes** (`include_archived`, `is_archived`) | OK — confirmed empirically |
| POST | /api/v1/cases | operator | n/a (create) | See finding 6 (whitespace/future-date validation), finding 7 (no idempotency) |
| GET | /api/v1/cases/{id} | operator | yes (`is_archived` via snapshot) | OK |
| PATCH | /api/v1/cases/{id} | operator | **yes** — blocks archival with 409 | OK — used as the *control* proving the pattern exists |
| GET | /api/v1/cases/{id}/events | operator | n/a | See finding 8 (200 empty instead of 404 for unknown case) |
| GET | /api/v1/cases/{id}/runs | operator | n/a | See finding 8 |
| POST | /api/v1/cases/{id}/reports | operator | n/a | **Finding 1 (HIGH)** — path `case_id` ignored |
| POST | /api/v1/cases/{id}/resume | operator | **no — missing guard** | **Finding 2 (HIGH)** |
| POST | /api/v1/cases/{id}/reopen | operator | **no — missing guard** | **Finding 2 (HIGH)** — confirmed |
| POST | /api/v1/cases/{id}/cancel | operator | **no — missing guard** | **Finding 2 (HIGH)** — confirmed |
| POST | /api/v1/appointments/{id}/cancel | operator | n/a | OK |
| POST | /api/v1/appointments/{id}/reschedule | operator | n/a | OK |
| GET | /api/v1/appointments/upcoming | operator | **no — leaks** | **Finding 4 (HIGH)** |
| GET | /api/v1/properties/{id}/history | operator | n/a | OK |
| GET | /api/v1/properties/{id}/stats | operator | n/a | OK |
| GET | /api/v1/cases/{id}/messages | operator | n/a (single case) | OK |
| GET | /api/v1/communications/{id} | operator | n/a | OK |
| GET | /api/v1/communications/{id}/recording | operator | n/a | OK |
| POST | /api/v1/communications/{id}/retry-recording | operator | n/a | OK |
| GET | /api/v1/research/{id} | operator | n/a | OK |
| POST | /api/v1/actions/{id}/approval | operator | n/a | OK — path/body `action_id` mismatch correctly rejected (409) by design |
| POST | /api/v1/cases/{id}/observations | operator | n/a | See finding 9 (hardcoded actor) |
| POST | /api/v1/cases/{id}/field-updates | operator | n/a | OK — correctly threads `operator` identity and cross-checks `appointment.case_id` |
| GET | /api/v1/metrics/dashboard | operator | **yes** — confirmed | OK |
| GET | /api/v1/notifications | operator | **no — leaks** | **Finding 4 (HIGH)** |
| GET | /api/v1/overview | operator | mostly yes, but reuses the leaking upcoming-appointments query | **Finding 4 (HIGH)** |
| GET | /api/v1/properties | operator | **yes** — confirmed | OK |
| POST | /api/v1/properties | operator | n/a | OK — good validators (blank/postcode/bedrooms/build_year) |
| GET | /api/v1/properties/{id} | operator | yes (`is_archived`) | OK |
| PATCH | /api/v1/properties/{id} | operator | yes — blocks archival (409) | OK |
| GET | /api/v1/contractors | operator | **yes** — confirmed | OK |
| POST | /api/v1/contractors | operator | n/a | OK |
| GET | /api/v1/contractors/{id} | operator | yes | OK |
| PATCH | /api/v1/contractors/{id} | operator | yes — blocks archival (409) | OK |
| GET | /api/v1/tenants | operator | **yes** — confirmed | OK |
| POST | /api/v1/tenants | operator | n/a | OK |
| GET | /api/v1/tenants/{id} | operator | yes | OK |
| PATCH | /api/v1/tenants/{id} | operator | yes — blocks archival-property tenants (409) | OK |
| POST | /api/v1/documents | operator | n/a | **Finding 3 (HIGH)** — content-type trusted; finding 10 (LOW) — Content-Disposition sanitization gap |
| GET | /api/v1/documents | operator | n/a (single subject) | OK |
| GET | /api/v1/documents/{id} | operator | yes (`is_archived`) | OK |
| GET | /api/v1/documents/{id}/content | operator | n/a | **Finding 3 (HIGH)** — confirmed; path traversal via `stored_name` confirmed **not** exploitable (server-generated uuid filename, never derived from user input) |
| DELETE | /api/v1/documents/{id} | operator | yes — blocks archival (409) | OK |
| GET | /api/v1/notes | operator | n/a | OK |
| POST | /api/v1/notes | operator | n/a | OK — author forced from `require_operator`, not body |
| PATCH | /api/v1/notes/{id} | operator | yes — blocks archival (409) | OK |
| DELETE | /api/v1/notes/{id} | operator | yes — blocks archival (409) | OK |
| GET | /api/v1/cases/{id}/costs | operator | n/a (single case; documented rationale) | OK |
| POST | /api/v1/cases/{id}/costs | operator | yes — blocks archival case (409) | OK — good amount/date validators |
| PATCH | /api/v1/costs/{id} | operator | yes — blocks archival (409) | OK |
| DELETE | /api/v1/costs/{id} | operator | yes — blocks archival (409) | OK |
| GET | /api/v1/messages/unread-count | operator | yes — confirmed excludes archival | OK |
| GET | /api/v1/messages/threads | operator | **yes** (`include_archived`) | OK |
| GET | /api/v1/messages/threads/{case_id} | operator | n/a | OK |
| POST | /api/v1/messages/threads/{case_id} | operator | yes — blocks archival case (409) | OK |
| POST | /api/v1/messages/threads/{case_id}/read | operator | yes — blocks archival (409) | OK |
| POST | /api/v1/messages/{id}/read | operator | yes — blocks archival (409) | OK |
| POST | /api/v1/messages/{id}/unread | operator | yes — blocks archival (409) | OK |
| GET | /api/v1/insights | operator | yes, default **include_archived=true** (documented reporting-surface exception) | OK — different default is intentional and honestly labelled (`includes_archived_history`, `archived_case_count`) |
| GET | /api/v1/insights/cases | operator | same as above | OK |
| GET | /api/v1/reports/summary | operator | same as above | OK |
| GET | /api/v1/reports/export.csv | operator | same as above | OK |
| GET | /api/v1/search | operator | flags `is_archived`, does not exclude (search is meant to find anything) | OK — reasonable for a global-find feature |
| POST | /api/v1/voice/sessions | operator | n/a | OK |
| POST | /api/v1/voice/sessions/{id}/bind | operator | n/a | OK |
| POST | /api/v1/voice/sessions/{id}/ended | operator | n/a | OK |
| POST | /webhooks/elevenlabs/post-call | signed | n/a | OK — 401 when secret unconfigured or signature invalid; unmapped conversation is quarantined, never guessed |
| POST | /integrations/elevenlabs/tools/intake | secret | n/a | OK |
| POST | /integrations/elevenlabs/tools/observations | secret | n/a | OK |
| POST | /integrations/elevenlabs/tools/context | secret | n/a | OK |

**Auth coverage verdict: no gap found.** Every one of the 69 `/api/v1/*` route×method combinations returned
`401 {"detail":"operator credentials required"}` with zero credentials under `OPERATOR_AUTH_ENABLED=true`
(verified programmatically by walking `app.routes`, not by reading decorators). The 4 remaining routes
(webhook + 3 tool routes) correctly reject with their own independent mechanism instead.

---

## Findings

### 1. HIGH — Cross-case report misattribution (CONFIRMED)
`backend/app/api/cases.py:403-410` (`submit_report`) takes `case_id` from the URL but passes it nowhere;
`backend/app/domain/services.py:442-451` (`record_contractor_report`) derives the *real* case entirely from
`work_order.case_id`. The path segment is decorative.

Request (case A's URL, case B's work order):
```
POST /api/v1/cases/{op_case}/reports
{"work_order_id": "<op_work_order2, belongs to op_case2>", "appointment_id": "<op_appointment2>",
 "contractor_id": "...", "text": "Report filed under the WRONG case's URL on purpose", "observed_at": "..."}
```
Response: `202 {"report_id":"...","result":{"status":"APPLIED","case_version":2,...}}` — no error, no
mismatch check. A follow-up `GET /api/v1/cases/{op_case2}/events` shows the `CONTRACTOR_REPORT_RECEIVED`
event landed on `op_case2`, not the URL's `op_case`.

Fix: load the work order via `services.load_work_order(session, case_id, submission.work_order_id)`
(already exists, used correctly by `costs.py`) instead of `session.get(WorkOrderModel, ...)`, so a
work-order/case mismatch 404s like every other cross-resource check in this codebase does.

### 2. HIGH — Archival ("read-only") cases can be reopened and cancelled (CONFIRMED)
`resume_case`, `reopen_case` and `cancel_case` (`backend/app/api/cases.py:413-484`) all call
`services.load_case` and check version/status, but — unlike `edit_case` two functions above them in the
same file (`cases.py:344-348`) — never check `case.archive_batch_id is not None`. `RepairCaseModel`'s own
docstring (`models.py:194-199`) states archival cases "can never be actioned."

Request 1: `POST /api/v1/cases/{arc_case}/reopen {"version":1,"reason":"audit probe","evidence_refs":[]}`
Response: `202 {"case_id":"...","version":2}` — succeeded. The case (previously `RESOLVED`) is now
`ESCALATED` with a live `CASE_ESCALATED` event.

Request 2 (same case, now at version 2): `POST /api/v1/cases/{arc_case}/cancel {"version":2,"reason":"audit probe 2"}`
Response: `202 {"case_id":"...","version":3}` — succeeded again.

Control, same case, same session: `PATCH /api/v1/cases/{arc_case} {"expected_version":2,"title":"hacked title"}`
Response: `409 {"error":{"code":"CONFLICT","message":"this is an archival sample case; archival records are read-only",...}}`
— proving the guard exists and is simply missing from three sibling routes, not absent from the codebase's
threat model.

Fix: add the same `if case.archive_batch_id is not None: raise ConflictError(...)` check to `resume_case`,
`reopen_case` and `cancel_case`.

### 3. HIGH — Content-Type spoofing → inline SVG served for execution (CONFIRMED)
`backend/app/api/documents.py:143` stores `content_type=file.content_type or "application/octet-stream"` —
the multipart `Content-Type` a client sent, unsniffed and unvalidated. `get_document_content`
(`documents.py:177-193`) computes `is_previewable = doc.content_type.startswith("image/") or doc.content_type
in _INLINE_CONTENT_TYPES` and serves `Content-Disposition: inline` whenever true, with the stored
`Content-Type` echoed back verbatim.

Request: multipart upload, `file=("evil.svg", b"<svg onload='alert(document.cookie)'><script>alert(1)</script></svg>", "image/svg+xml")`, `subject_type=CASE`.
Response: `201`, document stored.
Follow-up: `GET /api/v1/documents/{id}/content` →
`200`, headers `content-type: image/svg+xml`, `content-disposition: inline; filename="evil.svg"`, body is
the raw SVG including the `<script>` tag. A browser opening this URL directly (e.g. an operator clicking
"preview" on what they believe is a photo attachment) will parse and execute the embedded script in the
API's own origin.

Control: the same upload with `content_type=text/html` is correctly served as `attachment` (HTML isn't in
`_INLINE_CONTENT_TYPES` and doesn't start with `image/`), so only the `image/*` branch is affected — but
`image/svg+xml` is scriptable content that this allowlist treats as a safe-to-preview image.

Fix: either (a) sniff/validate actual file content against a real image decoder before trusting
`content_type`, or (b) exclude `image/svg+xml` from the inline-preview allowlist (serve it `attachment`
like everything else not on an explicit safe list), or (c) serve all `/documents/*/content` responses with
`Content-Security-Policy: sandbox` / from a separate cookie-less origin.

### 4. HIGH — Archival rows can leak into the operator's live "needs attention" feeds (CONFIRMED, latent)
Every operational aggregate that has archival exposure filters `RepairCaseModel.archive_batch_id.is_(None)`
except two: `load_upcoming_appointments` and `load_notifications`
(`backend/app/domain/services.py:1361+` and `:1421+` — the only two `archive_batch_id` references in the
whole file are elsewhere, at lines 1286 and 1343). `GET /api/v1/appointments/upcoming` and `GET
/api/v1/overview` both call the former; `GET /api/v1/notifications` calls the latter.

This is not reachable through the shipped archive importer today (it only ever produces `RESOLVED`/
`CANCELLED` archival cases with past appointments — confirmed via `app/archive/importer.py:541` and
`dataset.py:870`), so it is reported as a **latent gap**, not an actively exploited leak. Confirmed by
directly inserting (via the DB, not the API) a `CONFIRMED` future appointment and an `AWAITING_APPROVAL`
action record on the seeded archival case:

```
GET /api/v1/appointments/upcoming  -> archival case_id present: True (1 item)
GET /api/v1/overview               -> upcoming_appointments contains the archival case_id: True
GET /api/v1/notifications          -> items contains the archival case_id: True (1 item)
```

Because `action_records` and `appointments` carry no `archive_batch_id` column of their own (by design —
only `properties`/`tenants`/`contractors`/`repair_cases`/`messages`/`notes`/`documents`/`cost_entries` do),
these two functions are the *only* place in the codebase where the case-level archival join was needed but
omitted. Fix: join `RepairCaseModel` and add `RepairCaseModel.archive_batch_id.is_(None)` to both queries,
matching the pattern already used in `metrics.py:28`, `properties.py:174`, `tenants.py:153`, etc.

### 5. MEDIUM — Error envelope inconsistency on every request-body validation failure
`register_error_handlers` (`backend/app/api/errors.py`) registers a handler only for `DomainError`. FastAPI's
built-in `RequestValidationError` (missing field, wrong type, `StrictModel` extra-field rejection, a
`field_validator` raising `ValueError`) is never routed through it, so it falls back to FastAPI's default
`{"detail":[{...}]}` shape — structurally different from this app's own
`{"error":{"code":...,"message":...,"retryable":...,"correlation_id":...}}` contract that every
`DomainError`-derived 422/404/409/etc. produces. Confirmed on ~10 different mutating routes (e.g. `POST
/api/v1/cases` missing `tenant_id` → `{"detail":[{"type":"missing","loc":["body","tenant_id"],...}]}`; `POST
/api/v1/properties` with `bedrooms:-3` → `{"detail":[{"type":"value_error",...}]}`), versus e.g. `POST
/cases/{id}/costs` with a negative invoice amount → `{"error":{"code":"VALIDATION_ERROR",...}}`. Any client
coded against the documented `error.code`/`error.message` contract gets nothing usable for the most common
class of 4xx (basic body validation). Fix: add an `@app.exception_handler(RequestValidationError)` that
re-shapes into the same envelope with `code=VALIDATION_ERROR`.

### 6. MEDIUM — Blank content and future "started_at" accepted on case intake
`OperatorIntakeRequest` (`cases.py:233-242`) validates `description` with `min_length=8` only — no
`.strip()` check, unlike `PropertyCreateRequest.address_line` two files over (`properties.py:97-102`), which
explicitly rejects an all-whitespace value. Confirmed: `POST /api/v1/cases` with
`"description": "        "` (8 spaces) → `201`, case created with a blank/whitespace title (`case.title =
submission.description[:255]`). Also confirmed: `"started_at": "2099-01-01T00:00:00Z"` is accepted with no
"cannot be in the future" check, unlike `CostCreateRequest.incurred_at` (`costs.py:149-151`), which
explicitly rejects a future date for the conceptually identical "when did this happen" field. Fix: add the
same `.strip()`/non-blank `field_validator` used on `PropertyCreateRequest.address_line`, and the same
future-date guard used on `incurred_at`.

### 7. MEDIUM — No idempotency protection on operator case creation (CONFIRMED duplication)
`POST /api/v1/cases` (`create_case_from_operator_intake`, `cases.py:245-312`) mints a brand-new
`Communication` row (`comm_id = str(uuid.uuid4())`) on every call, then calls `services.submit_intake`,
whose only dedupe path is "this communication already has a case" — which is never true for a fresh
`comm_id`. Confirmed: submitting the identical body twice in a row creates two distinct cases
(`ed322c42-...` and `fa25f8e8-...`), unlike the voice/tool path (`POST /intakes`,
`/integrations/elevenlabs/tools/intake`), which is naturally idempotent because the caller supplies and
reuses one `communication_id`. A double-click on "New ticket" in the UI duplicates the case. Fix: accept an
optional client-generated idempotency key (or hash the `(property_id, tenant_id, description, source_text)`
tuple within a short window) and reuse the existing `comm.case_id is not None` NOOP path.

### 8. LOW — `GET /cases/{id}/events` and `/runs` silently succeed for a nonexistent case
Confirmed: `GET /api/v1/cases/{random-uuid}/events` and `.../runs` both return `200
{"items":[],"next_cursor":null}` for a case that does not exist, instead of `404`, unlike `GET
/api/v1/cases/{id}` itself and essentially every other by-id lookup in this codebase (`cases.py:189-209`
never calls `services.load_case`/`session.get` to check existence before querying children). Low impact
(no data leaked, just an honest "no events" for a case that doesn't exist), but it means a typo'd case_id
in a client is indistinguishable from a genuinely event-free case. Fix: `await services.load_case(session,
case_id)` first, as `get_case_messages` two routes below it already does.

### 9. LOW — Actor identity hardcoded to the literal string `"operator"` in three routes
`submit_intake_endpoint` (`cases.py:213-219`), `create_case_from_operator_intake`'s inner report-adjacent
calls, and `submit_observations` (`observations.py:17-23`) all construct
`ActorContext("OPERATOR", "operator", ...)` with a literal, rather than the value `require_operator`
actually returns (as `edit_case`, `resume_case`, `reschedule_appointment`, `notes.py`, `costs.py`, and
`messaging.py` all correctly do via `operator: str = Depends(require_operator)`). Confirmed via
`CaseEvent.actor_id == "operator"` after `POST /cases/{id}/reports`. Low impact today because this MVP ships
exactly one operator credential (`operator`/`repairflow-demo`), so the literal happens to match — but it
means `CaseEvent`'s audit trail can never attribute an action to a specific person even after a second
operator account is added, and it's an easy-to-miss inconsistency within the very same file. Fix: thread
`operator: str = Depends(require_operator)` through the two remaining routes and pass it into
`ActorContext` instead of the literal.

### 10. NIT — Content-Disposition filename sanitization strips quotes but not control characters
`documents.py:191`: `safe_name = doc.display_name.replace('"', "")` — does not strip CR/LF or other control
characters before interpolating into the `Content-Disposition` header. Tested with a filename containing
embedded `\r\n` plus a fake header line
(`legit.txt"\r\nX-Injected: pwn\r\nSet-Cookie: a=b`); the request as actually sent by the HTTP client had
already percent-encoded the control characters in the multipart `filename=` parameter before reaching the
server (`legit.txt%22%0D%0AX-Injected:...`), so this attempt could not demonstrate a real header injection —
inconclusive rather than a confirmed non-issue, since the app's own sanitization doesn't stop raw control
characters and the only reason this test came back safe is the client encoder plus (likely) the ASGI
server's own header-value validation, not a deliberate app-level defense. Recommend stripping/rejecting
control characters (`\r`, `\n`, and other non-printable bytes) from `display_name` as defense-in-depth
rather than relying on an incidental backstop.

---

## Things checked and found correct (not findings, recorded so they aren't re-litigated)

- **Auth coverage**: all 69 `/api/v1/*` routes empirically 401 with no credentials; webhook/tool routes
  correctly use their own signed/secret mechanism instead (see route table above).
- **Path traversal via `stored_name`**: structurally impossible — `stored_name` is always
  `uuid4().hex + sanitized_suffix`, generated server-side, never derived from the uploaded filename's path
  component (`documents.py:57-71,135`).
- **Archival scoping**: correct on `/cases`, `/properties`, `/contractors`, `/tenants`,
  `/messages/threads`, `/messages/unread-count`, `/metrics/dashboard`; all confirmed empirically with a
  seeded archival property/tenant/case/contractor pair (excluded by default, included + flagged
  `is_archived=true` on `include_archived=true`).
- **Reports/Insights `include_archived=true` default**: a deliberate, documented exception (reporting
  surfaces show full history by default, not "operational listings"), and every row/total is honestly
  labelled (`includes_archived_history`, `archived_case_count`, `record_source`) — not a violation of the
  archival rule, which targets operational listings specifically.
- **Pagination bounds**: `limit`/`offset` are enforced via `Query(ge=..., le=...)` on every paginated route
  checked (`/properties`, `/cases`, `/contractors`, `/tenants`) — negative offset, `limit=0`, and
  `limit=100000` all correctly 422 before reaching a handler.
- **Idempotency on report submission**: double-submitting an identical `(appointment_id, text,
  observed_at)` report body is correctly deduped — both calls return `202` with `result.status == "NOOP"`
  (`services.record_contractor_report`'s existing-row check).
- **Cross-resource authorization elsewhere**: `field_updates.py`'s `ContractorReportUpdate` correctly
  cross-checks `appointment.case_id != case_id` (404 on mismatch) — the same check finding 1 shows is
  missing from `cases.py`'s `submit_report`. `POST /actions/{id}/approval` correctly 409s when the path
  `action_id` disagrees with the body's `action_id`.
- **Upload size/empty-file handling**: an empty upload 422s (`"empty file rejected"`); an upload one byte
  over `max_document_bytes` correctly 413s with `PAYLOAD_TOO_LARGE`, and no partial file is left on disk
  (`documents.py`'s cap-then-write-then-DB-insert-or-unlink pattern).
- **Malformed/unknown UUIDs never 500**: every by-id route tried (`GET /cases/{garbage}`, `PATCH
  /cases/{garbage}`, well-formed-but-unknown UUIDs) correctly 404s via `NotFoundError`, since `case_id` etc.
  are plain `str` path params fed straight to `session.get`, which just returns `None` for a non-matching
  string rather than raising.
