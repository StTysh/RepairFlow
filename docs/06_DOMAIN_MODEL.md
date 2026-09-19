# 06 — Domain and Pydantic contracts

This document is the canonical application schema, not a claim about a provider SDK.

## Conventions

- UUID strings for internal identifiers; provider identifiers remain opaque strings.
- `datetime` means timezone-aware RFC 3339. Store UTC; display Europe/London.
- Every field listed is required unless marked `=default`. `T | None` means required-but-nullable unless a default is explicitly given.
- Input models use `extra="forbid"`; do not apply strict whole-payload rejection to evolving provider envelopes. Adapt known provider fields first.
- Money uses integer pence, currency `GBP`, never float. No guessed quote.
- External evidence carries source, observed time and provenance `LIVE | SIMULATED | FIXTURE`.
- Unknown safety answers are `UNKNOWN`, not false.
- Reuse DTOs and generate TypeScript from OpenAPI; do not maintain competing hand-written status enums.

## Reference records

| Model | Required fields and constraints |
|---|---|
| Property | `id, address_line, postcode, timezone, landlord_reference, roof_responsibility: LANDLORD\|OTHER\|UNKNOWN, access_notes: str\|None` |
| Tenant | `id, property_id, display_name, phone_e164: str\|None, preferred_channel, contact_allowed: bool, accessibility_notes: str\|None`; synthetic data in MVP |
| Contractor | `id, display_name, trades: list[Trade], service_postcodes, approval_status: APPROVED\|PENDING\|REJECTED, connector: MOCK\|HUMAN, contact_reference: str\|None, verification_note, provenance` |
| ContractorCandidate | `id, case_id, research_id, name, trades, website: HttpUrl\|None, phone: str\|None, service_area: str\|None, claimed_emergency_service: bool\|None, evidence: list[EvidenceRef], verification_status=UNVERIFIED`; no availability field inferred from search |
| EvidenceRef | `source_type: EVENT\|REPORT\|TRANSCRIPT\|VOICE_TOOL\|WEB\|OPERATOR, source_id, locator: str\|None, observed_at, provenance`; web locator is URL; transcript locator is turn ID; VOICE_TOOL references the persisted tool receipt |

`Trade = ROOFING | SCAFFOLDING | PLUMBING | ELECTRICAL | OTHER`. This small MVP enum is not a professional diagnosis taxonomy.

## Repair records

| Model | Required fields and constraints |
|---|---|
| RepairIssue | `id, case_id, description, location, started_at: datetime\|None, evidence_refs, tenant_resolution_confirmed_at: datetime\|None, unresolved_concerns: list[str]` |
| RiskAssessment | `urgency: EMERGENCY\|URGENT\|ROUTINE\|UNKNOWN, gas: Answer, fire: Answer, water_near_electrics: Answer, structural_danger: Answer, uncontrolled_flood: Answer, vulnerability_concern: Answer, evidence_refs, uncertainties: list[str], assessed_at` |
| RepairCase | `id, property_id, tenant_id, status: CaseStatus, version: int>=1, title, risk: RiskAssessment, created_at, updated_at, owner_operator_id, last_decision_summary: str\|None, next_follow_up_at: datetime\|None, escalation_reason: str\|None, resume_status: CaseStatus\|None` |
| WorkOrder | `id, case_id, issue_id, kind: REPAIR\|SCAFFOLD_INSTALL\|SCAFFOLD_REMOVE, trade, scope, status: WorkOrderStatus, contractor_id: UUID\|None, required_for_resolution: bool, quote_pence: int\|None, approved_limit_pence: int\|None, completion_report_id: UUID\|None, created_at, updated_at` |
| Dependency | `id, case_id, prerequisite_work_order_id, dependent_work_order_id, status: OPEN\|SATISFIED\|INVALIDATED, reason, discovered_from_report_id, satisfied_by_report_id: UUID\|None, created_at, satisfied_at: datetime\|None` |
| Appointment | `id, case_id, work_order_id, contractor_id, slot_id, start_at, end_at, status: PENDING\|CONFIRMED\|FINISHED\|CANCELLED, visit_outcome: COMPLETED\|BLOCKED\|NO_ACCESS\|FAILED\|UNKNOWN\|None, connector, provider_booking_id: str\|None, action_id, attempt_number: int>=1, availability_revision: int, provenance` |
| AvailabilityWindow | `id, case_id, person_type: TENANT\|CONTRACTOR, person_id, start_at, end_at, timezone, confirmed_at, expires_at, source_ref, revision: int>=1`; end > start; explicit dates required |
| ContractorReport | `id, case_id, work_order_id, appointment_id, contractor_id, text, observed_at, received_at, source_ref, provenance, interpretation_status: PENDING\|APPLIED\|REVIEW, interpreted_action_id: UUID\|None` |

`Answer = YES | NO | UNKNOWN`. `CaseStatus` and `WorkOrderStatus` are defined exclusively in docs/07. A source claim of safety is recorded with attribution; it is not a safety certificate issued by RepairFlow.

## Communication and recording

| Model | Required fields and constraints |
|---|---|
| Communication | `id, case_id: UUID\|None, tenant_id: UUID\|None, purpose: INTAKE\|AVAILABILITY\|FOLLOW_UP\|CONTRACTOR, direction: INBOUND\|OUTBOUND\|BROWSER, provider=ELEVENLABS, provider_conversation_id: str\|None, provider_call_sid: str\|None, correlation_token_hash, state: REQUESTED\|ACTIVE\|ENDED\|FAILED\|UNKNOWN, started_at: datetime\|None, ended_at: datetime\|None, transcript: list[TranscriptTurn], outcome: CallOutcome\|None, recording: Recording, provenance` |
| TranscriptTurn | `turn_id, speaker: AGENT\|USER\|TOOL\|UNKNOWN, text, time_in_call_secs: float>=0, tool_name: str\|None`; preserve order and original speech text |
| Recording | `status: PENDING\|AVAILABLE\|UNAVAILABLE\|FAILED, media_path: str\|None, media_type: str\|None, byte_count: int\|None, sha256: str\|None, acquired_at: datetime\|None, error_code: str\|None`; AVAILABLE only after nonempty bytes are saved |
| CallRequest | `case_id, tenant_id, purpose, transport: BROWSER\|TWILIO, allowed_questions: list[str], context_summary, action_id`; backend looks up recipient number; LLM cannot supply arbitrary destinations |
| CallOutcome | `communication_id, conversation_id: str\|None, outcome: ANSWERED\|NO_ANSWER\|VOICEMAIL\|FAILED\|UNKNOWN, confirmed_facts: list[ObservedFact], availability: list[AvailabilityWindow], tenant_confirms_resolved: bool\|None, missing_questions, transcript_refs, ended_at`; initiation failure may have no conversation ID |
| ObservedFact | `field, value: str\|bool\|None, source_ref, confirmed_by_speaker: bool`; validated field mapping applies observations; contradictions require operator review |

Keep original transcript and structured extraction separately. A fluent summary cannot replace what the caller actually said. A corrected extraction appends an event, rather than modifying historical transcript turns.

## Booking and research

| Model | Required fields |
|---|---|
| SlotOption | `slot_id, contractor_id, work_order_id, start_at, end_at, expires_at, availability_revision, provenance` |
| BookingRequest | `case_id, work_order_id, contractor_id, slot_id, tenant_availability_ids, access_confirmed: bool, authorized_limit_pence: int, idempotency_key` |
| BookingOutcome | `status: CONFIRMED\|PENDING\|REJECTED\|UNKNOWN, provider_booking_id: str\|None, confirmed_start: datetime\|None, confirmed_end: datetime\|None, reason: str\|None, provenance` |
| CancellationOutcome | `status: CANCELLED\|PENDING\|REJECTED\|UNKNOWN, provider_booking_id, reason: str\|None, provenance`; only CANCELLED proves the reservation was released |
| ResearchSnapshot | `id, case_id, query, provider=TAVILY, provider_request_id: str\|None, requested_at, completed_at, result_urls, results: list[WebEvidence], provenance` |
| WebEvidence | `url, title, excerpt, retrieved_at, provider_score: float\|None`; score is retrieval relevance, not supplier quality |

CONFIRMED requires a booking ID and confirmed interval; validate it fits an accepted tenant window and is not expired. PENDING/UNKNOWN never create a confirmed appointment.

## Event, run and job records

| Model | Required fields |
|---|---|
| CaseEvent | `id, case_id, seq: int>=1, type: EventType, occurred_at, received_at, actor_type, actor_id, source_event_key, correlation_id, causation_event_id: UUID\|None, payload_version=1, payload: dict, provenance` |
| ActionProposal | `case_id, expected_case_version, trigger_event_id, decision_summary: str<=500 chars, evidence_refs, action: NextAction` |
| ActionRecord | `id, case_id, kind, target_id: UUID\|None, idempotency_key, proposal, state: PROPOSED\|AWAITING_APPROVAL\|PENDING\|RUNNING\|SUCCEEDED\|FAILED\|UNKNOWN\|REJECTED, approval: Approval\|None, result: dict\|None, created_at, updated_at` |
| Approval | `operator_id, approved_at, action_payload_hash, authorized_limit_pence: int\|None, reason`; binds to exact proposal scope |
| OrchestrationRun | `id, case_id, trigger_event_id, snapshot_version, model_id, started_at, finished_at: datetime\|None, state: RUNNING\|SUCCEEDED\|FAILED\|SUPERSEDED, usage: dict, proposal: ActionProposal\|None, tool_calls: list[ToolTrace], policy_result: str\|None, error_code: str\|None` |
| ToolTrace | `id, run_id, name, started_at, finished_at, outcome: SUCCEEDED\|FAILED, input_resource_ids, output_resource_ids, error_code: str\|None`; no secrets or copied personal transcript in general trace |
| Job | `id, case_id: UUID\|None, kind: COORDINATE\|EXECUTE_ACTION\|FETCH_RECORDING\|FOLLOW_UP, dedupe_key, payload, run_at, status: PENDING\|LEASED\|DONE\|FAILED, attempts, lease_until: datetime\|None, last_error: str\|None` |

## NextAction: discriminated union

Each variant has required literal `kind`. The envelope supplies case/version/evidence, so variants do not duplicate them.

| Kind / model | Required fields |
|---|---|
| APPLY_TRIAGE / ApplyTriage | `risk, issue_description, suggested_trade, scope` |
| REQUEST_INFORMATION / RequestInformation | `recipient: TENANT\|OPERATOR, questions: list[str], purpose: INTAKE\|AVAILABILITY\|FOLLOW_UP` |
| DISCOVER_CONTRACTORS / DiscoverContractors | `trade, postcode` |
| SCHEDULE_VISIT / ScheduleVisit | `work_order_id, contractor_id, slot_id, tenant_availability_ids` |
| ADD_PREREQUISITE / AddPrerequisite | `report_id, blocked_work_order_id, prerequisite_trade, prerequisite_kind, prerequisite_scope, reason` |
| ACCEPT_REPORT / AcceptReport | `report_id, outcome: COMPLETED\|NO_ACCESS\|FAILED, completion_evidence_refs` |
| REQUEST_CONFIRMATION / RequestConfirmation | `issue_id, questions` |
| RESOLVE_CASE / ResolveCase | `issue_id, confirmation_event_id` |
| ESCALATE / Escalate | `reason_code, evidence_refs, operator_message` |
| WAIT / Wait | `reason, waiting_for: str, follow_up_at: datetime\|None` |

No generic UPDATE_STATUS, arbitrary JSON patch, SQL or arbitrary outbound-message variant.

Illustrative interface only:

```python
NextAction = Annotated[
    ApplyTriage | RequestInformation | DiscoverContractors | ScheduleVisit
    | AddPrerequisite | AcceptReport | RequestConfirmation | ResolveCase
    | Escalate | Wait,
    Field(discriminator="kind"),
]
```

Discriminated-union support is documented by [Pydantic](https://pydantic.dev/docs/validation/latest/concepts/unions/). Business predicates below are our own design.

## Cross-record validation

All referenced records belong to the same case. An authenticated actor must be scoped to the case. Prerequisite edges cannot self-reference or form cycles. Duplicate prerequisite discovery from the same report returns existing IDs.

For scaffolding, ADD_PREREQUISITE also creates a required SCAFFOLD_REMOVE order, blocked by roofing completion. This encodes safe removal after roof work using the same DAG. Booking installation/removal requires human authorization.

APPLY_TRIAGE creates at most one primary repair order for the issue; repeated information updates that order rather than duplicating it. A change of trade after dispatch escalates for review.

Tenant confirmation applies to the original issue. Case closure additionally requires every required order completed, no unresolved dependency, no unsafe flag, no contradictory observation and no pending/unknown external commitment.

## Ingress versus persisted objects

Voice callers do not supply database IDs for new facts, availability or evidence. Ingress models in 10 use AvailabilityInput and FactInput; trusted adapters attach case/person IDs, receipt references, UTC timestamps and revisions after identity/binding. This avoids requiring a case ID before the first intake has created one. In-call facts initially cite VOICE_TOOL receipts and can acquire transcript references when the full call arrives.

`CallRequest` is a tenant-call contract in MVP. CONTRACTOR communication purpose is reserved for later actor/contact modelling; do not misuse tenant_id to call a supplier. OrchestrationRun state is distinct from ActionRecord state.
