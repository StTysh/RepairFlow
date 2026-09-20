"""Canonical application DTOs and domain value models.

Source of truth: docs/06_DOMAIN_MODEL.md and docs/10_TOOL_CATALOG.md.
SQLAlchemy models in models.py store the same vocabulary; this module
owns the enums and shapes so both layers agree.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


def utcnow() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadModel(BaseModel):
    """Output/response shapes: tolerant of extra fields growing over time."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class Trade(str, enum.Enum):
    ROOFING = "ROOFING"
    SCAFFOLDING = "SCAFFOLDING"
    PLUMBING = "PLUMBING"
    ELECTRICAL = "ELECTRICAL"
    OTHER = "OTHER"


class Answer(str, enum.Enum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class RoofResponsibility(str, enum.Enum):
    LANDLORD = "LANDLORD"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class Provenance(str, enum.Enum):
    LIVE = "LIVE"
    SIMULATED = "SIMULATED"
    FIXTURE = "FIXTURE"


class ContractorApprovalStatus(str, enum.Enum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


class ConnectorType(str, enum.Enum):
    MOCK = "MOCK"
    HUMAN = "HUMAN"


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class SourceType(str, enum.Enum):
    EVENT = "EVENT"
    REPORT = "REPORT"
    TRANSCRIPT = "TRANSCRIPT"
    VOICE_TOOL = "VOICE_TOOL"
    WEB = "WEB"
    OPERATOR = "OPERATOR"


class CaseStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class WorkOrderKind(str, enum.Enum):
    REPAIR = "REPAIR"
    SCAFFOLD_INSTALL = "SCAFFOLD_INSTALL"
    SCAFFOLD_REMOVE = "SCAFFOLD_REMOVE"


class WorkOrderStatus(str, enum.Enum):
    READY = "READY"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_REPORT = "AWAITING_REPORT"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class DependencyStatus(str, enum.Enum):
    OPEN = "OPEN"
    SATISFIED = "SATISFIED"
    INVALIDATED = "INVALIDATED"


class AppointmentStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class VisitOutcome(str, enum.Enum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    NO_ACCESS = "NO_ACCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class InterpretationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    REVIEW = "REVIEW"


class PersonType(str, enum.Enum):
    TENANT = "TENANT"
    CONTRACTOR = "CONTRACTOR"


class CommPurpose(str, enum.Enum):
    INTAKE = "INTAKE"
    AVAILABILITY = "AVAILABILITY"
    FOLLOW_UP = "FOLLOW_UP"
    CONTRACTOR = "CONTRACTOR"


class CommDirection(str, enum.Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    BROWSER = "BROWSER"


class CommState(str, enum.Enum):
    REQUESTED = "REQUESTED"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class RecordingStatus(str, enum.Enum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class CallOutcomeStatus(str, enum.Enum):
    ANSWERED = "ANSWERED"
    NO_ANSWER = "NO_ANSWER"
    VOICEMAIL = "VOICEMAIL"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class Speaker(str, enum.Enum):
    AGENT = "AGENT"
    USER = "USER"
    TOOL = "TOOL"
    UNKNOWN = "UNKNOWN"


class Transport(str, enum.Enum):
    BROWSER = "BROWSER"
    TWILIO = "TWILIO"


class BookingStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class CancellationStatus(str, enum.Enum):
    CANCELLED = "CANCELLED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class EventType(str, enum.Enum):
    CASE_CREATED = "CASE_CREATED"
    INFORMATION_RECEIVED = "INFORMATION_RECEIVED"
    AVAILABILITY_RECEIVED = "AVAILABILITY_RECEIVED"
    RESEARCH_COMPLETED = "RESEARCH_COMPLETED"
    WORK_ORDER_CREATED = "WORK_ORDER_CREATED"
    APPOINTMENT_CONFIRMED = "APPOINTMENT_CONFIRMED"
    APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"
    APPOINTMENT_WINDOW_ENDED = "APPOINTMENT_WINDOW_ENDED"
    CONTRACTOR_REPORT_RECEIVED = "CONTRACTOR_REPORT_RECEIVED"
    DEPENDENCY_DISCOVERED = "DEPENDENCY_DISCOVERED"
    WORK_ORDER_COMPLETED = "WORK_ORDER_COMPLETED"
    DEPENDENCY_SATISFIED = "DEPENDENCY_SATISFIED"
    TENANT_CONFIRMATION_RECEIVED = "TENANT_CONFIRMATION_RECEIVED"
    FOLLOW_UP_DUE = "FOLLOW_UP_DUE"
    APPROVAL_DECIDED = "APPROVAL_DECIDED"
    CASE_ESCALATED = "CASE_ESCALATED"
    CASE_RESUMED = "CASE_RESUMED"
    CASE_RESOLVED = "CASE_RESOLVED"
    CASE_CANCELLED = "CASE_CANCELLED"
    CALL_INITIATED = "CALL_INITIATED"
    CALL_SKIPPED = "CALL_SKIPPED"
    CALL_ENDED = "CALL_ENDED"
    CALL_FAILED = "CALL_FAILED"
    RECORDING_AVAILABLE = "RECORDING_AVAILABLE"
    RECORDING_FAILED = "RECORDING_FAILED"
    ACTION_FAILED = "ACTION_FAILED"
    ACTION_UNKNOWN = "ACTION_UNKNOWN"


class ActionState(str, enum.Enum):
    PROPOSED = "PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    REJECTED = "REJECTED"


class OrchestrationRunState(str, enum.Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"


class ToolTraceOutcome(str, enum.Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class JobKind(str, enum.Enum):
    COORDINATE = "COORDINATE"
    EXECUTE_ACTION = "EXECUTE_ACTION"
    FETCH_RECORDING = "FETCH_RECORDING"
    PLACE_CALL = "PLACE_CALL"
    FOLLOW_UP = "FOLLOW_UP"


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    DONE = "DONE"
    FAILED = "FAILED"


class CommandResultStatus(str, enum.Enum):
    APPLIED = "APPLIED"
    NOOP = "NOOP"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class ToolErrorCode(str, enum.Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"
    STALE_VERSION = "STALE_VERSION"
    POLICY_REJECTED = "POLICY_REJECTED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    EXTERNAL_RESULT_UNKNOWN = "EXTERNAL_RESULT_UNKNOWN"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


# --------------------------------------------------------------------------
# Reference records
# --------------------------------------------------------------------------


class Property(ReadModel):
    id: UUID
    address_line: str
    postcode: str
    timezone: str = "Europe/London"
    landlord_reference: str
    roof_responsibility: RoofResponsibility
    access_notes: str | None = None
    # Honest-or-null: only ever a real value from seed/reference data (see
    # PropertyModel.build_year); no seeded property has one today.
    build_year: int | None = None


class Tenant(ReadModel):
    id: UUID
    property_id: UUID
    display_name: str
    phone_e164: str | None = None
    email: str | None = None
    preferred_channel: str
    contact_allowed: bool
    accessibility_notes: str | None = None


class ContractorWorker(StrictModel):
    name: str
    role: str


class Contractor(ReadModel):
    id: UUID
    display_name: str
    trades: list[Trade]
    service_postcodes: list[str]
    approval_status: ContractorApprovalStatus
    connector: ConnectorType
    contact_reference: str | None = None
    verification_note: str | None = None
    provenance: Provenance
    workers: list[ContractorWorker] = Field(default_factory=list)


class AssignedContractor(ReadModel):
    """Projection of the contractor working the case's active work order --
    distinct from CaseSnapshot.approved_contractors (the whole approved
    roster). `phone` is populated only when `contact_reference` is actually
    phone-shaped (seed data uses placeholders like "mock:apex-roofing");
    otherwise it stays null rather than inventing a number. `provenance`
    rides along so the UI can label a fictional/simulated contractor as such
    (CLAUDE.md: "All demo physical activity ... carry simulation provenance")."""

    id: UUID
    display_name: str
    trade: Trade | None = None
    contact_reference: str | None = None
    phone: str | None = None
    provenance: Provenance


class EvidenceRef(StrictModel):
    source_type: SourceType
    source_id: UUID
    locator: str | None = None
    observed_at: datetime
    provenance: Provenance


class ContractorCandidate(ReadModel):
    id: UUID
    case_id: UUID
    research_id: UUID
    name: str
    trades: list[Trade]
    website: HttpUrl | None = None
    phone: str | None = None
    service_area: str | None = None
    claimed_emergency_service: bool | None = None
    evidence: list[EvidenceRef]
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED


# --------------------------------------------------------------------------
# Repair records
# --------------------------------------------------------------------------


class RepairIssue(ReadModel):
    id: UUID
    case_id: UUID
    description: str
    location: str
    started_at: datetime | None = None
    evidence_refs: list[EvidenceRef]
    tenant_resolution_confirmed_at: datetime | None = None
    unresolved_concerns: list[str] = Field(default_factory=list)


class RiskAssessment(StrictModel):
    urgency: Literal["EMERGENCY", "URGENT", "ROUTINE", "UNKNOWN"] = "UNKNOWN"
    gas: Answer = Answer.UNKNOWN
    fire: Answer = Answer.UNKNOWN
    water_near_electrics: Answer = Answer.UNKNOWN
    structural_danger: Answer = Answer.UNKNOWN
    uncontrolled_flood: Answer = Answer.UNKNOWN
    vulnerability_concern: Answer = Answer.UNKNOWN
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    assessed_at: datetime = Field(default_factory=utcnow)

    @property
    def is_hazard(self) -> bool:
        return Answer.YES in (
            self.gas,
            self.fire,
            self.water_near_electrics,
            self.structural_danger,
            self.uncontrolled_flood,
        )


class RepairCase(ReadModel):
    id: UUID
    case_number: int
    property_id: UUID
    tenant_id: UUID
    status: CaseStatus
    version: int
    title: str
    risk: RiskAssessment
    created_at: datetime
    updated_at: datetime
    owner_operator_id: str
    last_decision_summary: str | None = None
    next_follow_up_at: datetime | None = None
    escalation_reason: str | None = None
    resume_status: CaseStatus | None = None


class WorkOrder(ReadModel):
    id: UUID
    case_id: UUID
    issue_id: UUID
    kind: WorkOrderKind
    trade: Trade
    scope: str
    status: WorkOrderStatus
    contractor_id: UUID | None = None
    required_for_resolution: bool
    quote_pence: int | None = None
    approved_limit_pence: int | None = None
    completion_report_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class Dependency(ReadModel):
    id: UUID
    case_id: UUID
    prerequisite_work_order_id: UUID
    dependent_work_order_id: UUID
    status: DependencyStatus
    reason: str
    discovered_from_report_id: UUID
    satisfied_by_report_id: UUID | None = None
    created_at: datetime
    satisfied_at: datetime | None = None


class Appointment(ReadModel):
    id: UUID
    case_id: UUID
    work_order_id: UUID
    contractor_id: UUID
    slot_id: str
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    visit_outcome: VisitOutcome | None = None
    connector: ConnectorType
    provider_booking_id: str | None = None
    action_id: UUID
    attempt_number: int
    availability_revision: int
    provenance: Provenance


class AvailabilityWindow(ReadModel):
    id: UUID
    case_id: UUID
    person_type: PersonType
    person_id: UUID
    start_at: datetime
    end_at: datetime
    timezone: str
    confirmed_at: datetime
    expires_at: datetime
    source_ref: EvidenceRef
    revision: int


class ContractorReport(ReadModel):
    id: UUID
    case_id: UUID
    work_order_id: UUID
    appointment_id: UUID
    contractor_id: UUID
    text: str
    observed_at: datetime
    received_at: datetime
    source_ref: EvidenceRef
    provenance: Provenance
    interpretation_status: InterpretationStatus
    interpreted_action_id: UUID | None = None


# --------------------------------------------------------------------------
# Communication and recording
# --------------------------------------------------------------------------


class TranscriptTurn(StrictModel):
    turn_id: str
    speaker: Speaker
    text: str
    time_in_call_secs: float = Field(ge=0)
    tool_name: str | None = None


class Recording(StrictModel):
    status: RecordingStatus = RecordingStatus.PENDING
    media_path: str | None = None
    media_type: str | None = None
    byte_count: int | None = None
    sha256: str | None = None
    acquired_at: datetime | None = None
    error_code: str | None = None


class ObservedFact(StrictModel):
    field: str
    value: str | bool | None
    source_ref: EvidenceRef
    confirmed_by_speaker: bool


class CallOutcome(ReadModel):
    communication_id: UUID
    conversation_id: str | None = None
    outcome: CallOutcomeStatus
    confirmed_facts: list[ObservedFact] = Field(default_factory=list)
    availability: list[AvailabilityWindow] = Field(default_factory=list)
    tenant_confirms_resolved: bool | None = None
    missing_questions: list[str] = Field(default_factory=list)
    transcript_refs: list[str] = Field(default_factory=list)
    ended_at: datetime | None = None
    # ElevenLabs' own post-call analysis summary (real provider output, not
    # generated by this app) -- lets a "recent activity" panel show what a
    # call was about without rendering the full transcript inline. The full
    # transcript/audio must still be reachable from the same UI surface
    # (CLAUDE.md: "a summary alone is insufficient") -- this is an addition
    # to that requirement, not a substitute for it.
    transcript_summary: str | None = None


class Communication(ReadModel):
    id: UUID
    case_id: UUID | None = None
    tenant_id: UUID | None = None
    purpose: CommPurpose
    direction: CommDirection
    # OPERATOR is not a provider in the network sense -- it marks a
    # conversation that happened in person or on a handset the operator
    # was holding, with no vendor involved. It still gets a
    # Communication row because intake is defined in terms of one
    # (docs/16); what differs is that nothing external carried it.
    provider: Literal["ELEVENLABS", "OPERATOR"] = "ELEVENLABS"
    provider_conversation_id: str | None = None
    provider_call_sid: str | None = None
    correlation_token_hash: str
    state: CommState
    started_at: datetime | None = None
    ended_at: datetime | None = None
    transcript: list[TranscriptTurn] = Field(default_factory=list)
    outcome: CallOutcome | None = None
    recording: Recording = Field(default_factory=Recording)
    provenance: Provenance


class CallRequest(StrictModel):
    case_id: UUID
    tenant_id: UUID
    purpose: CommPurpose
    transport: Transport
    allowed_questions: list[str]
    context_summary: str
    action_id: UUID | None = None


# --------------------------------------------------------------------------
# Booking and research
# --------------------------------------------------------------------------


class SlotOption(ReadModel):
    slot_id: str
    contractor_id: UUID
    work_order_id: UUID
    start_at: datetime
    end_at: datetime
    expires_at: datetime
    availability_revision: int
    provenance: Provenance


class BookingRequest(StrictModel):
    case_id: UUID
    work_order_id: UUID
    contractor_id: UUID
    slot_id: str
    tenant_availability_ids: list[UUID]
    access_confirmed: bool
    authorized_limit_pence: int
    idempotency_key: str


class BookingOutcome(ReadModel):
    status: BookingStatus
    provider_booking_id: str | None = None
    confirmed_start: datetime | None = None
    confirmed_end: datetime | None = None
    reason: str | None = None
    provenance: Provenance


class CancellationOutcome(ReadModel):
    status: CancellationStatus
    provider_booking_id: str | None = None
    reason: str | None = None
    provenance: Provenance


class WebEvidence(StrictModel):
    url: str
    title: str
    excerpt: str
    retrieved_at: datetime
    provider_score: float | None = None


class ResearchSnapshot(ReadModel):
    id: UUID
    case_id: UUID
    query: str
    provider: Literal["TAVILY"] = "TAVILY"
    provider_request_id: str | None = None
    requested_at: datetime
    completed_at: datetime | None = None
    result_urls: list[str] = Field(default_factory=list)
    results: list[WebEvidence] = Field(default_factory=list)
    provenance: Provenance


# --------------------------------------------------------------------------
# Event, run and job records
# --------------------------------------------------------------------------


# Human-readable projection per EventType, for the Timeline UI (docs/18).
# Deliberately a plain constant table computed from `type` alone -- never
# from `payload`, which stays untouched/unparsed here. Any EventType not
# listed falls back to a humanized version of its enum name so a new event
# type added later never breaks display, just looks generic until mapped.
_EVENT_DISPLAY: dict[str, tuple[str, str]] = {
    "CASE_CREATED": ("Case opened", "A new repair case was created from the reported issue."),
    "INFORMATION_RECEIVED": ("Details updated", "New information was recorded about the issue."),
    "AVAILABILITY_RECEIVED": ("Availability recorded", "New tenant availability was recorded."),
    "RESEARCH_COMPLETED": ("Contractor research completed", "Web research for candidate contractors finished."),
    "WORK_ORDER_CREATED": ("Work order created", "A new work order was opened for this case."),
    "APPOINTMENT_CONFIRMED": ("Visit confirmed", "A contractor visit was booked and confirmed."),
    "APPOINTMENT_CANCELLED": ("Visit cancelled", "A scheduled visit was cancelled."),
    "APPOINTMENT_WINDOW_ENDED": ("Visit window ended", "The scheduled visit window ended; awaiting a report."),
    "CONTRACTOR_REPORT_RECEIVED": ("Contractor report received", "A contractor submitted a report from the visit."),
    "DEPENDENCY_DISCOVERED": ("Prerequisite discovered", "Further work is required before this can proceed."),
    "WORK_ORDER_COMPLETED": ("Work order completed", "A work order was marked complete."),
    "DEPENDENCY_SATISFIED": ("Prerequisite satisfied", "A blocking prerequisite was resolved."),
    "TENANT_CONFIRMATION_RECEIVED": ("Tenant responded", "The tenant confirmed or disputed resolution."),
    "FOLLOW_UP_DUE": ("Follow-up due", "A scheduled follow-up became due."),
    "APPROVAL_DECIDED": ("Approval decided", "An operator approved or rejected a proposed action."),
    "CASE_ESCALATED": ("Case escalated", "The case was escalated for human review."),
    "CASE_RESUMED": ("Case resumed", "The case resumed normal handling."),
    "CASE_RESOLVED": ("Case resolved", "The issue was confirmed resolved."),
    "CASE_CANCELLED": ("Case cancelled", "The case was cancelled."),
    "CALL_ENDED": ("Call ended", "A voice call ended."),
    "CALL_FAILED": ("Call failed", "A voice call failed to connect."),
    "RECORDING_AVAILABLE": ("Recording available", "The call recording became available."),
    "RECORDING_FAILED": ("Recording failed", "The call recording could not be retrieved."),
    "ACTION_FAILED": ("Action failed", "A proposed action failed to execute."),
    "ACTION_UNKNOWN": ("Action outcome unknown", "An action's outcome could not be confirmed."),
}


def _humanize_event_type(event_type: "EventType | str") -> tuple[str, str]:
    key = event_type.value if hasattr(event_type, "value") else str(event_type)
    if key in _EVENT_DISPLAY:
        return _EVENT_DISPLAY[key]
    label = key.replace("_", " ").title()
    return label, label


class CaseEvent(ReadModel):
    id: UUID
    case_id: UUID
    seq: int
    type: EventType
    occurred_at: datetime
    received_at: datetime
    actor_type: str
    actor_id: str
    source_event_key: str
    correlation_id: str
    causation_event_id: UUID | None = None
    payload_version: int = 1
    payload: dict
    provenance: Provenance
    display_title: str = ""
    display_description: str = ""

    @model_validator(mode="after")
    def _apply_display_defaults(self) -> "CaseEvent":
        if not self.display_title or not self.display_description:
            title, description = _humanize_event_type(self.type)
            if not self.display_title:
                self.display_title = title
            if not self.display_description:
                self.display_description = description
        return self


# --- NextAction discriminated union -----------------------------------


class ApplyTriage(StrictModel):
    kind: Literal["APPLY_TRIAGE"] = "APPLY_TRIAGE"
    risk: RiskAssessment
    issue_description: str
    suggested_trade: Trade
    scope: str


class RequestInformation(StrictModel):
    kind: Literal["REQUEST_INFORMATION"] = "REQUEST_INFORMATION"
    recipient: Literal["TENANT", "OPERATOR"]
    questions: list[str]
    purpose: CommPurpose


class DiscoverContractors(StrictModel):
    kind: Literal["DISCOVER_CONTRACTORS"] = "DISCOVER_CONTRACTORS"
    trade: Trade
    postcode: str


class ScheduleVisit(StrictModel):
    kind: Literal["SCHEDULE_VISIT"] = "SCHEDULE_VISIT"
    work_order_id: UUID
    contractor_id: UUID
    slot_id: str
    tenant_availability_ids: list[UUID]


class AddPrerequisite(StrictModel):
    kind: Literal["ADD_PREREQUISITE"] = "ADD_PREREQUISITE"
    report_id: UUID
    blocked_work_order_id: UUID
    prerequisite_trade: Trade
    prerequisite_kind: WorkOrderKind
    prerequisite_scope: str
    reason: str


class AcceptReport(StrictModel):
    kind: Literal["ACCEPT_REPORT"] = "ACCEPT_REPORT"
    report_id: UUID
    outcome: Literal["COMPLETED", "NO_ACCESS", "FAILED"]
    completion_evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class RequestConfirmation(StrictModel):
    kind: Literal["REQUEST_CONFIRMATION"] = "REQUEST_CONFIRMATION"
    issue_id: UUID
    questions: list[str]


class ResolveCase(StrictModel):
    kind: Literal["RESOLVE_CASE"] = "RESOLVE_CASE"
    issue_id: UUID
    confirmation_event_id: UUID


class Escalate(StrictModel):
    kind: Literal["ESCALATE"] = "ESCALATE"
    reason_code: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    operator_message: str


class Wait(StrictModel):
    kind: Literal["WAIT"] = "WAIT"
    reason: str
    waiting_for: str
    follow_up_at: datetime | None = None


NextAction = Annotated[
    Union[
        ApplyTriage,
        RequestInformation,
        DiscoverContractors,
        ScheduleVisit,
        AddPrerequisite,
        AcceptReport,
        RequestConfirmation,
        ResolveCase,
        Escalate,
        Wait,
    ],
    Field(discriminator="kind"),
]

NEXT_ACTION_TYPES: tuple[type[StrictModel], ...] = (
    ApplyTriage,
    RequestInformation,
    DiscoverContractors,
    ScheduleVisit,
    AddPrerequisite,
    AcceptReport,
    RequestConfirmation,
    ResolveCase,
    Escalate,
    Wait,
)


class ActionProposal(StrictModel):
    case_id: UUID
    expected_case_version: int
    trigger_event_id: UUID
    decision_summary: str = Field(max_length=500)
    evidence_refs: list[EvidenceRef]
    action: NextAction


class Approval(StrictModel):
    operator_id: str
    approved_at: datetime
    action_payload_hash: str
    authorized_limit_pence: int | None = None
    reason: str


class ActionRecord(ReadModel):
    id: UUID
    case_id: UUID
    kind: str
    target_id: UUID | None = None
    idempotency_key: str
    # Not itself a business fact -- exposed so the operator UI can echo it
    # back in ApprovalDecision.action_payload_hash (docs/18: "Approving
    # sends proposal hash/version"); docs/06 doesn't list it because it's
    # admission-time plumbing, not domain data.
    payload_hash: str
    proposal: ActionProposal
    state: ActionState
    approval: Approval | None = None
    result: dict | None = None
    created_at: datetime
    updated_at: datetime


class ToolTrace(StrictModel):
    id: UUID
    run_id: UUID
    name: str
    started_at: datetime
    finished_at: datetime | None = None
    outcome: ToolTraceOutcome | None = None
    input_resource_ids: list[str] = Field(default_factory=list)
    output_resource_ids: list[str] = Field(default_factory=list)
    error_code: str | None = None


class OrchestrationRun(ReadModel):
    id: UUID
    case_id: UUID
    trigger_event_id: UUID
    snapshot_version: int
    model_id: str
    started_at: datetime
    finished_at: datetime | None = None
    state: OrchestrationRunState
    usage: dict = Field(default_factory=dict)
    proposal: ActionProposal | None = None
    tool_calls: list[ToolTrace] = Field(default_factory=list)
    policy_result: str | None = None
    error_code: str | None = None


class Job(ReadModel):
    id: UUID
    case_id: UUID | None = None
    kind: JobKind
    dedupe_key: str
    payload: dict
    run_at: datetime
    status: JobStatus
    attempts: int
    lease_until: datetime | None = None
    last_error: str | None = None


# --------------------------------------------------------------------------
# Ingress DTOs (no persisted IDs supplied by an untrusted caller)
# --------------------------------------------------------------------------

FACT_FIELD_ALLOWLIST = {
    "description",
    "location",
    "started_at",
    "gas",
    "fire",
    "water_near_electrics",
    "structural_danger",
    "uncontrolled_flood",
    "vulnerability_concern",
    "unresolved_concern",
}


class AvailabilityInput(StrictModel):
    start_at: datetime
    end_at: datetime
    timezone: str
    spoken_text: str
    confirmed_by_speaker: bool


class FactInput(StrictModel):
    field: str
    value: str | bool | None
    spoken_text: str
    confirmed_by_speaker: bool


class SafetyAnswers(StrictModel):
    gas: Answer = Answer.UNKNOWN
    fire: Answer = Answer.UNKNOWN
    water_near_electrics: Answer = Answer.UNKNOWN
    structural_danger: Answer = Answer.UNKNOWN
    uncontrolled_flood: Answer = Answer.UNKNOWN
    vulnerability_concern: Answer = Answer.UNKNOWN


class IntakeSubmission(StrictModel):
    communication_id: UUID
    property_id: UUID
    tenant_id: UUID
    description: str
    location: str
    started_at: datetime | None = None
    safety_answers: SafetyAnswers = Field(default_factory=SafetyAnswers)
    availability: list[AvailabilityInput] = Field(default_factory=list)
    source_text: str


class ObservationSubmission(StrictModel):
    communication_id: UUID
    facts: list[FactInput] = Field(default_factory=list)
    availability: list[AvailabilityInput] = Field(default_factory=list)
    tenant_confirms_resolved: bool | None = None
    source_text: str


class ReportSubmission(StrictModel):
    work_order_id: UUID
    appointment_id: UUID
    contractor_id: UUID
    text: str
    observed_at: datetime


# --------------------------------------------------------------------------
# Command / tool infrastructure
# --------------------------------------------------------------------------


class CaseRef(StrictModel):
    case_id: UUID


class RecordRef(StrictModel):
    case_id: UUID
    record_id: UUID


class ReadEvents(StrictModel):
    case_id: UUID
    after_seq: int = 0
    limit: int = Field(default=50, le=100)


class CaseSnapshot(ReadModel):
    case: RepairCase
    issue: RepairIssue
    property: Property
    tenant: Tenant
    # The contractor assigned to the case's currently-relevant work order
    # (docs/06 distinguishes this from `approved_contractors`, the whole
    # roster). None until a work order has a contractor. See
    # services.assigned_contractors_for_cases for the single shared
    # selection rule -- also used by the case-list endpoint so the two
    # views never disagree about who's "the" contractor for a case.
    assigned_contractor: AssignedContractor | None = None
    # Soonest CONFIRMED appointment whose window hasn't fully ended yet
    # (covers a visit currently in progress, not just ones yet to start),
    # ordered by start_at. Never a fabricated future step -- null when
    # there is none on record.
    next_appointment: Appointment | None = None
    work_orders: list[WorkOrder]
    dependencies: list[Dependency]
    appointments: list[Appointment]
    latest_reports: list[ContractorReport]
    communications: list[Communication]
    availability: list[AvailabilityWindow]
    approved_contractors: list[Contractor]
    pending_actions: list[ActionRecord]
    recent_events: list[CaseEvent]
    policy_snapshot: dict
    snapshot_version: int
    # Honest per-case signal, not a fake spinner: true only while a real
    # job for THIS case is due/leased or a coordinator run on it is
    # actually mid-flight.
    agent_active: bool = False


class CommandContext(StrictModel):
    case_id: UUID
    expected_case_version: int
    action_id: UUID | None = None
    actor_id: str
    idempotency_key: str


class ToolError(StrictModel):
    code: ToolErrorCode
    message: str
    retryable: bool
    retry_after_seconds: int | None = None
    reconciliation_required: bool = False


class CommandResult(StrictModel):
    action_id: UUID | None = None
    status: CommandResultStatus
    case_version: int
    event_ids: list[UUID] = Field(default_factory=list)
    resource_ids: dict[str, UUID] = Field(default_factory=dict)
    error: ToolError | None = None


class ContractorSearchRequest(StrictModel):
    case_id: UUID
    trade: Trade
    postcode: str
    max_results: int = 5


class ContractorSearchResult(StrictModel):
    research: ResearchSnapshot
    candidates: list[ContractorCandidate]
    warnings: list[str] = Field(default_factory=list)


class AppointmentQuery(StrictModel):
    case_id: UUID
    work_order_id: UUID
    contractor_id: UUID
    tenant_availability_ids: list[UUID]


class AppointmentOptions(StrictModel):
    slots: list[SlotOption]
    reason_if_empty: str | None = None


class ApprovalDecision(StrictModel):
    action_id: UUID
    expected_case_version: int
    approve: bool
    authorized_limit_pence: int | None = None
    reason: str
    action_payload_hash: str


class CancellationRequest(StrictModel):
    appointment_id: UUID
    reason: str


class SimulationObservationContractorReport(StrictModel):
    kind: Literal["CONTRACTOR_REPORT"] = "CONTRACTOR_REPORT"
    appointment_id: UUID
    text: str
    observed_at: datetime


class SimulationObservationTenantFeedback(StrictModel):
    kind: Literal["TENANT_FEEDBACK"] = "TENANT_FEEDBACK"
    confirms_resolved: bool
    text: str


class SimulationObservationAttendanceWindowEnded(StrictModel):
    kind: Literal["ATTENDANCE_WINDOW_ENDED"] = "ATTENDANCE_WINDOW_ENDED"
    appointment_id: UUID


SimulationObservation = Annotated[
    Union[
        SimulationObservationContractorReport,
        SimulationObservationTenantFeedback,
        SimulationObservationAttendanceWindowEnded,
    ],
    Field(discriminator="kind"),
]


class VoiceSessionRequest(StrictModel):
    purpose: CommPurpose
    tenant_id: UUID | None = None
    case_id: UUID | None = None
    disclosure_accepted: bool
    channel: Literal["BROWSER", "PSTN"] = "BROWSER"


class ResumeCaseRequest(StrictModel):
    version: int
    reason: str
    resolved_hold_evidence: str


class ReopenCaseRequest(StrictModel):
    version: int
    reason: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class CancelCaseRequest(StrictModel):
    version: int
    reason: str


# --------------------------------------------------------------------------
# HTTP response envelopes (docs/16 routes). These wrap canonical DTOs above
# for a specific endpoint's JSON body; they are transport shape, not domain
# data, so they live here rather than being added to docs/06's DTO table.
# Giving every route a real response_model (instead of -> dict) is what
# makes the generated OpenAPI schema -- and the frontend TS types built from
# it -- describe actual response shapes rather than an opaque object.
# --------------------------------------------------------------------------


class ReadinessResponse(StrictModel):
    database: str
    gemini_live: bool
    elevenlabs_live: bool
    tavily_live: bool


class CaseListItem(StrictModel):
    id: UUID
    case_number: int
    title: str
    status: CaseStatus
    version: int
    updated_at: datetime
    property_address: str
    # A different axis from `status` -- RiskAssessment.urgency, already
    # stored per-case (decision: keep it, don't build a derived display
    # status). "UNKNOWN" until triage has run.
    urgency: Literal["EMERGENCY", "URGENT", "ROUTINE", "UNKNOWN"] = "UNKNOWN"
    assigned_contractor_name: str | None = None
    category: Trade | None = None
    # True when this row is synthetic archival history rather than
    # live work. Every list that can show one must label it, so a
    # sample case is never mistaken for something to act on.
    is_archived: bool = False


class CaseListResponse(StrictModel):
    items: list[CaseListItem]
    next_cursor: str | None = None


class CaseDetailResponse(StrictModel):
    snapshot: CaseSnapshot
    latest_event_seq: int


class CaseEventsResponse(StrictModel):
    items: list[CaseEvent]
    next_cursor: str | None = None


class CaseRunsResponse(StrictModel):
    items: list[OrchestrationRun]
    next_cursor: str | None = None


class IntakeResponse(StrictModel):
    case_id: UUID
    communication_id: UUID
    result: CommandResult


class ReportSubmitResponse(StrictModel):
    report_id: UUID
    result: CommandResult


class CaseVersionResponse(StrictModel):
    case_id: UUID
    version: int


class AppointmentCancelResponse(StrictModel):
    appointment_id: UUID
    outcome: CancellationOutcome
    case_version: int


class RetryRecordingResponse(StrictModel):
    queued: bool


class ApprovalResponse(StrictModel):
    result: CommandResult


class DemoResetResponse(StrictModel):
    cleared: bool
    reason: str | None = None
    case_count: int = 0
    preserved_live_cases: int = 0


class DemoTenantFeedbackResponse(StrictModel):
    communication_id: UUID
    result: CommandResult


class DashboardMetricsResponse(StrictModel):
    """Counts derived directly from the 5 real CaseStatus values plus
    CASE_RESOLVED CaseEvents -- no derived/richer display-status layer
    (decision: keep the status taxonomy honest and simple)."""

    active: int
    awaiting_confirmation: int
    resolved: int
    escalated: int
    cancelled: int
    total: int
    resolved_this_week: int
    # Honest signal, not a fake spinner: true only while a real job is
    # due/leased or a coordinator run is actually mid-flight.
    agent_active: bool
    # Mean hours between a case's created_at and its latest CASE_RESOLVED
    # event, for cases resolved in the last 30 days. Null when nothing has
    # resolved in that window -- never a fabricated average.
    avg_resolution_hours: float | None = None
    # "vs 7 days ago" trend arrows. See services.reconstructed_status_counts
    # for exactly what "7 days ago" means here: a documented, deliberately
    # simplified replay of the append-only CaseEvent log, not a literal
    # historical audit (AWAITING_CONFIRMATION in particular has no
    # dedicated CaseEvent, so it folds into ACTIVE for this reconstruction).
    # Null whenever the percentage change would be undefined/misleading
    # (nothing existed in that status 7 days ago to compare against).
    active_delta_pct: float | None = None
    awaiting_confirmation_delta_pct: float | None = None
    escalated_delta_pct: float | None = None


class PropertyHistoryItem(StrictModel):
    case_id: UUID
    case_number: int
    title: str
    status: CaseStatus
    created_at: datetime
    resolved_at: datetime | None = None
    # From the latest ContractorReport.text on a COMPLETED work order for
    # this case; null when there is nothing grounded to show -- never a
    # fabricated one-line summary.
    outcome: str | None = None
    # Same selection rule as CaseListItem.assigned_contractor_name /
    # CaseSnapshot.assigned_contractor (services._pick_assigned_work_order):
    # null until some work order on the case actually has a contractor.
    contractor_name: str | None = None
    # Sum of WorkOrder.quote_pence across every work order on this case.
    # Named "quoted", not "cost"/"spend": no field in this schema represents
    # money actually paid (CLAUDE.md honesty rule; see WorkOrder.quote_pence
    # vs approved_limit_pence). Null when the case has no work orders yet.
    quoted_pence: int | None = None
    # The case's "primary" trade, for property-history grouping/filtering.
    # Judgment call (no product spec for this): prefer the work order
    # marked required_for_resolution=True (the primary repair, not a
    # scaffold/access prerequisite); if several qualify, or none do, take
    # the first work order created. See services._pick_primary_trade.
    trade: Trade | None = None


class PropertyHistoryResponse(StrictModel):
    property_id: UUID
    items: list[PropertyHistoryItem]


class TradeQuoteBreakdown(StrictModel):
    trade: Trade
    quoted_pence: int
    # This trade's share of quoted_pence across all trades for the
    # property, 0-100. Computed from real sums, never hardcoded; 0.0 when
    # the property has no quoted work orders at all.
    percentage: float


class YearlyQuoteTotal(StrictModel):
    year: int
    quoted_pence: int


class RecurringIssue(StrictModel):
    trade: Trade
    occurrence_count: int
    last_occurred_at: datetime


class PropertyStatsResponse(StrictModel):
    """Property-level aggregation for the "breakdown by trade" / "annual
    quoted total" / "recurring issues" charts. See
    services.load_property_stats for the exact (documented, judgment-call)
    computation of each derived field."""

    property_id: UUID
    # Count of cases currently in CaseStatus.ACTIVE for this property -- the
    # same strict reading of "active" DashboardMetricsResponse uses (not a
    # broader "still open" definition spanning AWAITING_CONFIRMATION/
    # ESCALATED too).
    active_count: int
    total_count: int
    quoted_by_trade: list[TradeQuoteBreakdown]
    quoted_by_year: list[YearlyQuoteTotal]
    recurring_issues: list[RecurringIssue]
    build_year: int | None = None


class UpcomingAppointmentItem(StrictModel):
    """One row for the cross-case "upcoming appointments" list -- enough to
    render date, contractor, address and time window without a follow-up
    per-case fetch."""

    appointment_id: UUID
    case_id: UUID
    case_number: int
    case_title: str
    work_order_id: UUID
    trade: Trade
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    property_address: str
    contractor_id: UUID
    contractor_name: str


class UpcomingAppointmentsResponse(StrictModel):
    items: list[UpcomingAppointmentItem]


class RecordSubject(str, enum.Enum):
    """What a note or document is filed against. One enum rather than a
    table per subject: notes and documents carry no domain semantics of
    their own, so splitting them would multiply tables without adding a
    single rule."""

    PROPERTY = "PROPERTY"
    CASE = "CASE"
    CONTRACTOR = "CONTRACTOR"
    TENANT = "TENANT"


class CostKind(str, enum.Enum):
    """Why a money row exists. QUOTE is an expected amount, INVOICE an
    amount actually billed, ADJUSTMENT a signed correction to either.
    Kept distinct so spend reporting can state whether it is showing
    quoted or actual money instead of silently mixing them (docs/17)."""

    QUOTE = "QUOTE"
    INVOICE = "INVOICE"
    ADJUSTMENT = "ADJUSTMENT"


class MessageChannel(str, enum.Enum):
    """How a message is (or would be) carried. INTERNAL never leaves the
    system; VOICE is the ElevenLabs conversation path and is recorded
    here only as a pointer to the authoritative Communication row."""

    INTERNAL = "INTERNAL"
    EMAIL = "EMAIL"
    SMS = "SMS"
    VOICE = "VOICE"


class MessageDeliveryState(str, enum.Enum):
    """Deliberately distinguishes "we saved it" from "a provider accepted
    it" from "it reached somebody" (docs/16, and the standing rule that
    provider acceptance is not delivery). Nothing may display as SENT
    because a draft was persisted."""

    DRAFT = "DRAFT"
    INTERNAL_NOTE = "INTERNAL_NOTE"
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RECEIVED = "RECEIVED"


class MessageSenderType(str, enum.Enum):
    TENANT = "TENANT"
    CONTRACTOR = "CONTRACTOR"
    OPERATOR = "OPERATOR"


class Message(ReadModel):
    """Display-only tenant/contractor/operator message-thread entry
    (CLAUDE.md: chat history is not authoritative state). Never read by the
    coordinator -- not part of CaseSnapshot, its prompt, or any tool it can
    call; this exists purely so the operator UI can show a thread."""

    id: UUID
    case_id: UUID
    sender_type: MessageSenderType
    sender_name: str
    text: str
    photo_url: str | None = None
    created_at: datetime


class CaseMessagesResponse(StrictModel):
    case_id: UUID
    items: list[Message]


class NotificationKind(str, enum.Enum):
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    CASE_ESCALATED = "CASE_ESCALATED"


class NotificationItem(StrictModel):
    """Bell-icon feed row, derived entirely from existing ActionRecord/
    CaseEvent rows -- see services.load_notifications for exactly how
    `unread` is defined (there is no separate persisted read-state)."""

    id: str
    kind: NotificationKind
    case_id: UUID
    case_number: int
    case_title: str
    occurred_at: datetime
    message: str
    unread: bool


class NotificationsResponse(StrictModel):
    items: list[NotificationItem]
    unread_count: int


class DemoPropertyRef(StrictModel):
    """One seeded property + its tenant, for the "+ New Ticket" property
    picker and the property-history "Property details" tab. Demo-only glue
    (see DemoSeedRefs docstring) -- not a general properties API."""

    property_id: UUID
    tenant_id: UUID
    address_line: str
    postcode: str
    landlord_reference: str
    roof_responsibility: RoofResponsibility
    access_notes: str | None = None
    build_year: int | None = None
    tenant_name: str
    tenant_phone: str | None = None


class DemoSeedRefs(StrictModel):
    property_id: UUID
    tenant_id: UUID
    roofer_id: UUID
    scaffolder_id: UUID
    # All seeded properties (including the one above, which stays first for
    # backward compatibility with anything defaulting to it). Queried live
    # from the DB rather than the seed module's constants, so this is
    # honest even if seeding hasn't (yet) inserted everything it defines.
    properties: list[DemoPropertyRef] = []


# --------------------------------------------------------------------------
# Voice endpoints (docs/16 "Operator and UI endpoints" for /api/v1/voice/*,
# docs/16 "ElevenLabs endpoints" for the webhook and dedicated-secret tool
# routes -- these bypass operator Basic auth per docs/16's own carve-out
# and use their own verification instead).
# --------------------------------------------------------------------------


class VoiceSessionResponse(StrictModel):
    communication_id: UUID
    session_credential: str | None = None
    connection_type: Literal["websocket", "pstn"] = "websocket"
    dynamic_variables: dict[str, str]
    expires_at: datetime


class VoiceSessionBindRequest(StrictModel):
    provider_conversation_id: str


class VoiceSessionBindResponse(StrictModel):
    communication_id: UUID
    case_id: UUID | None = None
    bound: bool


class VoiceSessionEndedRequest(StrictModel):
    provider_conversation_id: str


class VoiceSessionEndedResponse(StrictModel):
    queued: bool


class ToolAckResponse(StrictModel):
    """Deliberately vague per docs/11: "Return 'Your report is saved;
    coordination is pending,' not invented operational results" -- the
    voice agent never sees the coordinator's actual decision synchronously."""

    accepted: bool
    communication_id: UUID
    case_id: UUID | None = None
    message: str


class ToolIntakeRequest(StrictModel):
    correlation_token: str
    submission: IntakeSubmission


class ToolObservationsRequest(StrictModel):
    correlation_token: str
    submission: ObservationSubmission


class ToolContextRequest(StrictModel):
    correlation_token: str
    communication_id: UUID


class ConversationContextResponse(StrictModel):
    communication_id: UUID
    case_id: UUID | None = None
    purpose: CommPurpose
    tenant_display_name: str | None = None
    property_address: str | None = None
    issue_summary: str | None = None
    current_date: datetime
    timezone: str = "Europe/London"


class WebhookAckResponse(StrictModel):
    receipt_id: UUID
    status: str
