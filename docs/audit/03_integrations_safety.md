# Audit 03: Integrations & Safety (Outbound Contact, Webhooks, Booking, Secrets)

Scope: `backend/app/integrations/` (elevenlabs, tavily, booking, no_contact), `backend/app/api/voice.py`,
`backend/app/config.py`, `backend/.env.example`, plus everything needed to prove or disprove claims about
them (callers, tests, frontend rendering, built frontend bundle). Read-only audit; no server started, no
provider called, no source edited.

## Severity counts

- CRITICAL: 0
- HIGH: 1
- MEDIUM: 1
- LOW: 2
- NIT: 2

**Verdict: no way to reach a human was found.** `place_outbound_call` in
`backend/app/integrations/elevenlabs.py:99-124` is the only function in the codebase that can make a phone
ring, dial, message or email anyone, it is unconditionally gated by `assert_contact_allowed()`, and the
gate cannot be defeated by import order, `lru_cache`, or a job-body bypass (all confirmed by direct
testing/reading below, not assumed).

---

## Outbound-capable functions × guards (CONFIRMED by search)

Full-repo grep for `httpx.AsyncClient`/`httpx.Client`/`requests.get|post`/`smtplib`/`twilio`/`send_sms`/
`send_email`/`sendgrid` found real network-call sites in exactly **3 files**:
`app/integrations/elevenlabs.py`, `app/integrations/tavily.py`, `app/api/voice.py`. No other file makes an
HTTP call, and no subprocess/eval/exec/arbitrary-shell pattern exists anywhere in `app/`.

| Function | File:line | Reaches a person? | Guard |
|---|---|---|---|
| `place_outbound_call` | `integrations/elevenlabs.py:99` | **Yes** — dials PSTN via Twilio | `assert_contact_allowed("voice_call", to_number)` at function entry (line 113), unconditional, no bypass parameter |
| `place_call` (job body) | `integrations/elevenlabs.py:218` | Wraps the above | Checks `no_contact_enabled() and not substitute_installed()` (line 286) *before* checking `outbound_calls_enabled`/allowlist, so the real cause is recorded; the transport-level assert above is the backstop for any caller that skips this function |
| `create_signed_session` | `integrations/elevenlabs.py:84` | No — returns a WebSocket URL for the operator's own browser to talk to the AI agent (docs/16: single-operator demo, browser channel stands in for the tenant) | Only `settings.elevenlabs_live` (real key present); **not** routed through `no_contact` |
| `fetch_conversation_details` / `fetch_conversation_audio` | `integrations/elevenlabs.py:127,137` | No — read-only retrieval of an already-initiated conversation | `settings.elevenlabs_live` only |
| `TavilyResearchAdapter.search` | `integrations/tavily.py:83` | No — search API, contacts no person | Only constructed when `settings.tavily_live` (`main.py:56-59`) |
| `MockBookingConnector.book/cancel` | `integrations/booking.py:112,154` | No — pure DB, no network call at all | N/A |
| `messaging.py` compose | `api/messaging.py` | No — every non-INTERNAL channel is saved as `DRAFT` with an honest `delivery_detail`; no provider is ever called, and the module docstring states `no_contact` isn't imported because "there is simply nothing outbound for it to guard" | N/A (verified true by reading the whole file) |

**Finding (informational, not a violation):** only `place_outbound_call` reaches a *person*, so
`no_contact.py`'s exclusive focus on it is correct. But it is not the only function that makes a **real
network call to a live provider with real credentials** — `create_signed_session`,
`fetch_conversation_details`, `fetch_conversation_audio`, and Tavily's `search` all fire for real whenever
credentials are configured, independent of `FIXI_NO_CONTACT`/pytest. This is intentional by design (they
don't contact a human) and is why `test_voice.py` and `test_research.py` each independently neutralize
their own network boundary (`_clear_elevenlabs_env` autouse fixture; `httpx.AsyncClient` monkeypatched to a
`MockTransport`) rather than relying on `no_contact` to do it. Confirmed no gap in the default suite: both
neutralization mechanisms were read in full and are unconditional.

## Attempts to defeat the guard (all failed — CONFIRMED)

- **Import order**: `no_contact_enabled()` reads `os.environ` directly on every call (no caching), so it
  cannot be pre-warmed stale by import order (`no_contact.py:46-49`).
- **`lru_cache` on `get_settings`**: irrelevant to the guard — `no_contact_enabled()` never touches
  `Settings`/`get_settings` at all, by design (module docstring, lines 3-7).
- **Job body bypass**: `place_call()` checks `no_contact_enabled()` before any provider policy checks
  (line 286), and `place_outbound_call()` re-checks unconditionally (line 113) as a backstop "covers every
  caller including future ones and any test that reaches it by mistake."
- **Monkeypatching without a substitute**: `test_transport_guard_fails_closed_when_substitute_is_missing`
  (`tests/test_no_contact_harness.py:198-211`) proves arming `provider_substitute()` without patching the
  transport still raises `NoContactViolation` — fail-closed, not fail-open.
- **Webhook/tool routes**: `/webhooks/elevenlabs/post-call` and `/integrations/elevenlabs/tools/*` only
  ingest data (`services.submit_intake`/`record_observations`) or persist an already-completed call's
  transcript/audio; none of them call `place_outbound_call` or any network-write function.
- **Direct httpx elsewhere**: none found (see table above; exhaustive grep).

---

## HIGH — Fabricated (MOCK) appointment reads as an unqualified "Confirmed" in the operator UI

`backend/app/integrations/booking.py:66-88` documents its own fabrication candidly:

> "**This invents availability, and that is a known outstanding problem.** `_ensure_slots` ... generates
> candidate times from a date offset rather than reading any contractor's real calendar, so a slot this
> returns reflects nothing a contractor has agreed to."

`_ensure_slots` (`booking.py:36-63`) synthesizes exactly two fixed daily slots (09:00 and 13:00, each 3h)
per weekday from `demo_slot_offset_days` (default 2) out to a 10-day horizon, keyed only by
`contractor_id`+date+hour — no contractor input of any kind. `MockBookingConnector.book()`
(`booking.py:112-152`) then reserves one and returns `BookingOutcome(status=CONFIRMED, ...,
provenance=Provenance.SIMULATED)`. `executor.py:373-380` persists that as:

```python
appointment = AppointmentModel(
    ...
    start_at=outcome.confirmed_start, end_at=outcome.confirmed_end, status="CONFIRMED",
    connector="MOCK", provider_booking_id=outcome.provider_booking_id, action_id=action_record.id,
    ...
)
```

The API does carry the honesty markers: `Appointment.connector` and `Appointment.provenance` are both
present in the schema and in the frontend's type (`frontend-fixi/src/api/types.ts:115-129`). But the
operator-facing render never uses them. `NextAppointmentRow` in
`frontend-fixi/src/routes/maintenance.tickets.$ticketId.{-$section}.tsx:541-568` maps status to a Pill
purely off `appointment.status`:

```tsx
const appointmentStatusTone: Record<Appointment["status"], "amber" | "green" | "gray"> = {
  PENDING: "amber", CONFIRMED: "green", FINISHED: "gray", CANCELLED: "gray",
};
...
<Pill tone={appointmentStatusTone[appointment.status]} className="mt-1">
  {appointment.status === "PENDING" ? "Pending — contractor has not confirmed" : titleCase(appointment.status)}
</Pill>
```

A `CONFIRMED`/`MOCK` appointment renders as a plain green **"Confirmed"** — textually and visually
identical to what a real provider integration would show. Grepping the whole frontend source for
`.connector`/`provenance` confirms `connector`/`provenance` are rendered for **Communications** (line 346,
tone `LIVE`/gray) and **Research results** (line 701) and for a *contractor's own* connector field
(`routes/contractors.$contractorId.tsx:145`), but never for an appointment. There is also no app-wide
"simulation mode" banner (grepped `frontend-fixi/src` for `SIMULAT`/"demo mode" — the only hits are the
`Provenance` type and one label in `DocumentsPanel.tsx`) that would compensate.

By contrast, the honest human-arranged path is careful about exactly this: `RescheduleDialog.tsx:14-24`
creates appointments as `PENDING`, never `CONFIRMED`, specifically citing docs/19 ("provider request
acceptance is not booking confirmation"). The MockBookingConnector path is the one place that still writes
`CONFIRMED` outright, and it is the one place the UI doesn't show provenance.

**Exploit/failure scenario**: an operator watching the ticket header during a demo or real use sees "green
— Confirmed" for a slot no contractor has ever agreed to, and it is visually indistinguishable from a
genuine provider confirmation. This is precisely the "invented availability reaching a record that reads
as provider-confirmed" the task asked to check for — and it does, in the primary UI surface.

**Smallest correct fix**: in `NextAppointmentRow` (and anywhere else `Appointment` is rendered), add a
`connector === "MOCK"` (or `provenance !== "LIVE"`) badge next to the status Pill, matching the pattern
already used for Communications/Research — e.g. `{appointment.connector === "MOCK" && <Pill tone="gray">Simulated booking</Pill>}`. No backend change needed; the data is already there.

---

## MEDIUM — Webhook replay window is exact-body-only; a captured-and-modified body has no defense beyond the signature itself

`verify_webhook_signature` (`integrations/elevenlabs.py:50-81`) is timing-safe (`hmac.compare_digest`,
line 80) and fails closed on a missing/empty secret: `voice.py:178-179` raises **401** before ever calling
the verifier if `settings.elevenlabs_webhook_secret` is falsy —

```python
if not settings.elevenlabs_webhook_secret:
    raise HTTPException(status_code=401, detail="webhook signing secret not configured")
```

— so **an unsigned webhook can never be accepted, even with an empty secret** (the CRITICAL condition
named in the brief does not hold; CONFIRMED safe).

Timestamp tolerance is ±30 minutes (`WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS = 30 * 60`, line 41), checked with
`abs(current - timestamp)`, so it accepts timestamps up to 30 minutes in the *future* as well as the past —
wider than Stripe's typical 5-minute window, and this file's own comment admits the whole scheme is
*guessed*, not confirmed against a real delivery (lines 33-40, docs/26 entry 13). Replay of an
**identical** captured request within that window is caught by `record_webhook_receipt`'s dedupe key
(`provider, event_type, conversation_id, event_timestamp, body_sha256` — `orchestration/dedupe.py:37-47`),
which returns `DUPLICATE` without reprocessing. That is a real, working replay defense for exact replays.
It is **not** a defense against a MITM/leaked-secret attacker minting a *new* signature for a *modified*
body within the 30-minute window — but that is a property of any HMAC scheme with a shared secret, not a
bug in this implementation, and the transcript/outcome mapping downstream is defensive (see next finding)
so a malicious payload would still be parsed conservatively rather than trusted blindly.

**Smallest correct fix**: tighten the tolerance to something closer to 5 minutes once a real ElevenLabs
delivery is observed and the true clock-skew need is known (docs/23 already tracks "verify against one real
webhook delivery" as an open item) — this is a hardening suggestion, not a hole.

---

## LOW — `create_signed_session`/Tavily `search` are live-provider calls not gated by `no_contact`

Documented in the table above. Not exploitable in the default test suite (`test_voice.py`'s autouse
`_reset_elevenlabs_env` fixture force-clears `ELEVENLABS_API_KEY`/`AGENT_ID`/both secrets before and after
every test, `test_voice.py:59-73`; `test_research.py` always stubs `httpx.AsyncClient` to a `MockTransport`
regardless of the key value). Worth noting explicitly because the task's framing ("is `place_outbound_call`
the *only* function that dials/messages/emails") could be misread as "the only function that talks to a
live provider" — it is the only one that reaches a **person**, which is the correct and narrower guarantee
`no_contact.py` actually gives.

## LOW — `map_outcome`/`map_transcript` role-matching duplicated, not shared

`map_outcome`'s `has_user_turn` check (`elevenlabs.py:198-201`) re-implements the same
`role in ("USER","TENANT","CALLER")` test that `map_transcript` (`elevenlabs.py:154-156`) already does,
independently, against the raw dict rather than the already-mapped `TranscriptTurn` list. Both are correct
and both default to the safe/unknown branch on anything unrecognized (verified: unknown status →
`UNKNOWN`; unknown termination_reason with no user turn → `UNKNOWN`, never `ANSWERED`; this is exactly the
"no closure inferred from silence" fix the module's own docstring at lines 178-186 describes making on
2026-09-19). Purely a maintainability nit — a future edit to one role list and not the other would silently
diverge. No incorrect output found.

---

## NIT — No secrets found in the built frontend bundle or in logs (CONFIRMED clean)

Grepped `frontend-fixi/dist/assets/*.js` for `api_key`, `apikey`, `secret`, `xi-api-key`, `sk-`,
`elevenlabs`, `tavily`, `gemini`, `bearer `. Two incidental hits, both false positives on inspection:
`sk-` matches inside minified Tailwind class-name literals (`"mask-...`), and `elevenlabs` matches only
plain UI copy ("real ElevenLabs calls, not a summary standing in for them") in the call-history panel — no
key material. Grepped `app/` for `logger.*` calls referencing `api_key|secret|token|password` — zero
matches. `api/errors.py`'s only registered handler serializes `DomainError` fields explicitly (`code`,
`message`, `retryable`, `correlation_id`) — no `str(exc)` passthrough, no traceback leakage, and `FastAPI()`
is constructed without `debug=True`. The system-status endpoint (`cases.py:75`) exposes only booleans
(`gemini_live`, `elevenlabs_live`, `tavily_live`), never the underlying key values.

## NIT — Config defaults are closed for a fresh clone (CONFIRMED)

`OPERATOR_AUTH_ENABLED` defaults `true`; `OUTBOUND_CALLS_ENABLED` defaults `false` with an empty allowlist;
`ELEVENLABS_TOOL_SECRET` unset makes the tool routes 503 (`voice.py:278-279`, fail-closed, not fail-open);
`ELEVENLABS_WEBHOOK_SECRET` unset makes the webhook 401 unconditionally; all three `*_live` properties are
`False` with no keys, which is what puts the coordinator/booking/research into their documented
fixture/simulated modes. One residual note (not a new gap, already flagged in `config.py`'s own comment):
`operator_password` defaults to the publicly-known string `repairflow-demo`, adequate only because this is
declared local-only; the comment already says to flip `operator_auth_enabled`/change the password "before
any live/public demo."

---

## Contractor-candidate / approved-contractor separation — CONFIRMED correct

`ContractorCandidateModel` (Tavily research output) and `ContractorModel` (bookable directory) are distinct
tables with no automated promotion path (grepped for `promote`/`from_candidate`: none exists).
`create_contractor` (`api/contractors.py:203-213`) always sets `approval_status=PENDING` — the request DTO
has no `approval_status` field by design ("Deliberately no `approval_status` field: a POST can never create
an already-APPROVED contractor"). Promotion to `APPROVED` requires a human `PATCH` carrying a non-empty
`verification_note` (`contractors.py:246-249`). `SCHEDULE_VISIT` policy enforcement
(`orchestration/executor.py:292-293`) hard-rejects booking against anything but an approved contractor:

```python
contractor = await session.get(ContractorModel, str(action.contractor_id))
if contractor is None or contractor.approval_status != "APPROVED":
    raise PolicyRejectedError(f"contractor {action.contractor_id} is not an approved supplier")
```

Tavily's own network/search activity is recorded in `ResearchSnapshotModel`, entirely separate from
`CommunicationModel` (which is reserved for ElevenLabs calls) — satisfies CLAUDE.md's "log Tavily research
separately; it is a search service." `_build_query` (`tavily.py:62-66`) is verified by its own test
(`test_build_query_never_includes_tenant_identity`) to never embed tenant name/phone/transcript, only trade
+ postcode.

---

## Model-visible tools are scoped reads — CONFIRMED

`app/agents/read_tools.py` exposes exactly five tools (`read_report`, `read_communication`,
`list_case_events`, `read_research`, `find_appointment_options`) — all reads. `find_appointment_options`
calls `mock_booking_connector.list_slots` (a read), never `.book`. Booking only happens inside
`orchestration/executor.py`'s typed `ScheduleVisit` action handling, behind the policy checks quoted above
— consistent with CLAUDE.md's "model-visible tools are scoped reads; domain writes go through a typed
action executor and deterministic policy." No `subprocess`/`eval`/`exec`/raw-SQL-string pattern exists
anywhere in `app/`.
