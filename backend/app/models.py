"""SQLAlchemy 2.0 ORM models. Canonical shapes: docs/06, docs/10; tables: docs/17.

Primary keys are UUID text. Enum columns use SQLAlchemy's non-native Enum,
which SQLite renders as a CHECK constraint. Structured value objects
(RiskAssessment, EvidenceRef lists, transcripts, JSON envelopes) are stored
as validated-on-boundary JSON columns rather than exploded into extra
repository tables, per docs/17's "JSON columns are acceptable" guidance.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.schemas import (
    AppointmentStatus,
    CaseStatus,
    CommDirection,
    CommPurpose,
    CommState,
    ConnectorType,
    ContractorApprovalStatus,
    DependencyStatus,
    InterpretationStatus,
    JobKind,
    JobStatus,
    OrchestrationRunState,
    PersonType,
    Provenance,
    RoofResponsibility,
    Trade,
    VerificationStatus,
    VisitOutcome,
    WorkOrderKind,
    WorkOrderStatus,
)


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(sa.TypeDecorator):
    """Stores timezone-aware UTC datetimes as ISO-8601 text; always returns aware datetimes."""

    impl = sa.String(32)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, _dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime rejected: all stored timestamps must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def process_result_value(self, value: str | None, _dialect):
        if value is None:
            return None
        return datetime.fromisoformat(value)


def enum_column(py_enum, *, nullable: bool = False, default=None, name: str | None = None):
    return mapped_column(
        sa.Enum(py_enum, native_enum=False, validate_strings=True, length=40, name=name),
        nullable=nullable,
        default=default,
    )


class PropertyModel(Base):
    __tablename__ = "properties"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    address_line: Mapped[str] = mapped_column(sa.String(255))
    postcode: Mapped[str] = mapped_column(sa.String(16))
    timezone: Mapped[str] = mapped_column(sa.String(64), default="Europe/London")
    landlord_reference: Mapped[str] = mapped_column(sa.String(64))
    roof_responsibility: Mapped[RoofResponsibility] = enum_column(
        RoofResponsibility, default=RoofResponsibility.UNKNOWN
    )
    access_notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    property_id: Mapped[str] = mapped_column(sa.ForeignKey("properties.id"), index=True)
    display_name: Mapped[str] = mapped_column(sa.String(128))
    phone_e164: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    preferred_channel: Mapped[str] = mapped_column(sa.String(32))
    contact_allowed: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    accessibility_notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ContractorModel(Base):
    __tablename__ = "contractors"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    display_name: Mapped[str] = mapped_column(sa.String(128))
    trades: Mapped[list[str]] = mapped_column(sa.JSON, default=list)
    service_postcodes: Mapped[list[str]] = mapped_column(sa.JSON, default=list)
    approval_status: Mapped[ContractorApprovalStatus] = enum_column(
        ContractorApprovalStatus, default=ContractorApprovalStatus.PENDING
    )
    connector: Mapped[ConnectorType] = enum_column(ConnectorType, default=ConnectorType.MOCK)
    contact_reference: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    verification_note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    provenance: Mapped[Provenance] = enum_column(Provenance, default=Provenance.SIMULATED)
    # Narration only -- never a booking/assignment target. The coordinator
    # may name a preferred contact in its own decision_summary text; no
    # domain write (appointment, work order) ever references a worker.
    workers: Mapped[list[dict]] = mapped_column(sa.JSON, default=list)


class RepairCaseModel(Base):
    __tablename__ = "repair_cases"
    __table_args__ = (
        sa.CheckConstraint("version > 0", name="ck_case_version_positive"),
        sa.Index("ix_case_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    property_id: Mapped[str] = mapped_column(sa.ForeignKey("properties.id"))
    tenant_id: Mapped[str] = mapped_column(sa.ForeignKey("tenants.id"))
    status: Mapped[CaseStatus] = enum_column(CaseStatus, default=CaseStatus.ACTIVE)
    version: Mapped[int] = mapped_column(sa.Integer, default=1)
    title: Mapped[str] = mapped_column(sa.String(255))
    risk: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    owner_operator_id: Mapped[str] = mapped_column(sa.String(64), default="operator")
    last_decision_summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    escalation_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    resume_status: Mapped[CaseStatus | None] = enum_column(CaseStatus, nullable=True)


class RepairIssueModel(Base):
    __tablename__ = "repair_issues"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"), unique=True)
    description: Mapped[str] = mapped_column(sa.Text)
    location: Mapped[str] = mapped_column(sa.String(128))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    evidence_refs: Mapped[list[dict]] = mapped_column(sa.JSON, default=list)
    tenant_resolution_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    unresolved_concerns: Mapped[list[str]] = mapped_column(sa.JSON, default=list)


class WorkOrderModel(Base):
    __tablename__ = "work_orders"
    __table_args__ = (sa.Index("ix_workorder_case", "case_id"),)

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"))
    issue_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_issues.id"))
    kind: Mapped[WorkOrderKind] = enum_column(WorkOrderKind)
    trade: Mapped[Trade] = enum_column(Trade)
    scope: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[WorkOrderStatus] = enum_column(WorkOrderStatus)
    contractor_id: Mapped[str | None] = mapped_column(sa.ForeignKey("contractors.id"), nullable=True)
    required_for_resolution: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    quote_pence: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    approved_limit_pence: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    completion_report_id: Mapped[str | None] = mapped_column(sa.String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DependencyModel(Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        sa.UniqueConstraint(
            "case_id", "prerequisite_work_order_id", "dependent_work_order_id", name="uq_dependency_pair"
        ),
        sa.CheckConstraint(
            "prerequisite_work_order_id != dependent_work_order_id", name="ck_dependency_not_self"
        ),
        sa.Index("ix_dependency_dependent_status", "dependent_work_order_id", "status"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"))
    prerequisite_work_order_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"))
    dependent_work_order_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"))
    status: Mapped[DependencyStatus] = enum_column(DependencyStatus, default=DependencyStatus.OPEN)
    reason: Mapped[str] = mapped_column(sa.Text)
    discovered_from_report_id: Mapped[str] = mapped_column(sa.ForeignKey("contractor_reports.id"))
    satisfied_by_report_id: Mapped[str | None] = mapped_column(
        sa.ForeignKey("contractor_reports.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    satisfied_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AppointmentModel(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        sa.UniqueConstraint("work_order_id", "attempt_number", name="uq_appointment_attempt"),
        sa.Index("ix_appointment_workorder_status", "work_order_id", "status"),
        sa.Index(
            "uq_appointment_provider_booking",
            "connector",
            "provider_booking_id",
            unique=True,
            sqlite_where=sa.text("provider_booking_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"))
    work_order_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"))
    contractor_id: Mapped[str] = mapped_column(sa.ForeignKey("contractors.id"))
    slot_id: Mapped[str] = mapped_column(sa.String(80))
    start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[AppointmentStatus] = enum_column(AppointmentStatus, default=AppointmentStatus.PENDING)
    visit_outcome: Mapped[VisitOutcome | None] = enum_column(VisitOutcome, nullable=True)
    connector: Mapped[ConnectorType] = enum_column(ConnectorType, default=ConnectorType.MOCK)
    provider_booking_id: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    action_id: Mapped[str] = mapped_column(sa.ForeignKey("action_records.id"))
    attempt_number: Mapped[int] = mapped_column(sa.Integer, default=1)
    availability_revision: Mapped[int] = mapped_column(sa.Integer, default=1)
    provenance: Mapped[Provenance] = enum_column(Provenance, default=Provenance.SIMULATED)


class AvailabilityWindowModel(Base):
    __tablename__ = "availability_windows"
    __table_args__ = (
        sa.CheckConstraint("start_at < end_at", name="ck_availability_window_order"),
        sa.Index("ix_availability_case_person_revision", "case_id", "person_id", "revision"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"))
    person_type: Mapped[PersonType] = enum_column(PersonType)
    person_id: Mapped[str] = mapped_column(sa.String(36))
    start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime)
    timezone: Mapped[str] = mapped_column(sa.String(64), default="Europe/London")
    confirmed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source_ref: Mapped[dict] = mapped_column(sa.JSON)
    revision: Mapped[int] = mapped_column(sa.Integer, default=1)


class ContractorReportModel(Base):
    __tablename__ = "contractor_reports"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"))
    work_order_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"))
    appointment_id: Mapped[str] = mapped_column(sa.ForeignKey("appointments.id"))
    contractor_id: Mapped[str] = mapped_column(sa.ForeignKey("contractors.id"))
    text: Mapped[str] = mapped_column(sa.Text)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    source_ref: Mapped[dict] = mapped_column(sa.JSON)
    provenance: Mapped[Provenance] = enum_column(Provenance, default=Provenance.SIMULATED)
    interpretation_status: Mapped[InterpretationStatus] = enum_column(
        InterpretationStatus, default=InterpretationStatus.PENDING
    )
    interpreted_action_id: Mapped[str | None] = mapped_column(
        sa.ForeignKey("action_records.id"), nullable=True
    )


class ContractorCandidateModel(Base):
    __tablename__ = "contractor_candidates"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"))
    research_id: Mapped[str] = mapped_column(sa.ForeignKey("research_snapshots.id"))
    name: Mapped[str] = mapped_column(sa.String(128))
    trades: Mapped[list[str]] = mapped_column(sa.JSON, default=list)
    website: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    phone: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    service_area: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    claimed_emergency_service: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    evidence: Mapped[list[dict]] = mapped_column(sa.JSON, default=list)
    verification_status: Mapped[VerificationStatus] = enum_column(
        VerificationStatus, default=VerificationStatus.UNVERIFIED
    )


class ResearchSnapshotModel(Base):
    __tablename__ = "research_snapshots"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"))
    query: Mapped[str] = mapped_column(sa.Text)
    provider: Mapped[str] = mapped_column(sa.String(16), default="TAVILY")
    provider_request_id: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    result_urls: Mapped[list[str]] = mapped_column(sa.JSON, default=list)
    results: Mapped[list[dict]] = mapped_column(sa.JSON, default=list)
    provenance: Mapped[Provenance] = enum_column(Provenance, default=Provenance.LIVE)


class CommunicationModel(Base):
    __tablename__ = "communications"
    __table_args__ = (sa.Index("ix_communication_case", "case_id"),)

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str | None] = mapped_column(sa.ForeignKey("repair_cases.id"), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(sa.ForeignKey("tenants.id"), nullable=True)
    purpose: Mapped[CommPurpose] = enum_column(CommPurpose)
    direction: Mapped[CommDirection] = enum_column(CommDirection)
    provider: Mapped[str] = mapped_column(sa.String(16), default="ELEVENLABS")
    provider_conversation_id: Mapped[str | None] = mapped_column(
        sa.String(80), nullable=True, unique=True
    )
    provider_call_sid: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    correlation_token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    state: Mapped[CommState] = enum_column(CommState, default=CommState.REQUESTED)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    transcript: Mapped[list[dict]] = mapped_column(sa.JSON, default=list)
    outcome: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    recording: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    provenance: Mapped[Provenance] = enum_column(Provenance, default=Provenance.LIVE)


class WebhookReceiptModel(Base):
    __tablename__ = "webhook_receipts"
    __table_args__ = (
        sa.UniqueConstraint(
            "provider", "event_type", "conversation_id", "event_timestamp", "body_sha256",
            name="uq_webhook_receipt_identity",
        ),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    provider: Mapped[str] = mapped_column(sa.String(32))
    event_type: Mapped[str] = mapped_column(sa.String(64))
    conversation_id: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    event_timestamp: Mapped[str] = mapped_column(sa.String(40))
    body_sha256: Mapped[str] = mapped_column(sa.String(64))
    payload: Mapped[dict] = mapped_column(sa.JSON)
    processing_status: Mapped[str] = mapped_column(sa.String(32), default="RECEIVED")
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CaseEventModel(Base):
    __tablename__ = "case_events"
    __table_args__ = (
        sa.UniqueConstraint("case_id", "seq", name="uq_case_event_seq"),
        sa.UniqueConstraint("case_id", "source_event_key", name="uq_case_event_source_key"),
        sa.Index("ix_case_event_received", "case_id", "received_at"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"))
    seq: Mapped[int] = mapped_column(sa.Integer)
    type: Mapped[str] = mapped_column(sa.String(40))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    actor_type: Mapped[str] = mapped_column(sa.String(32))
    actor_id: Mapped[str] = mapped_column(sa.String(64))
    source_event_key: Mapped[str] = mapped_column(sa.String(160))
    correlation_id: Mapped[str] = mapped_column(sa.String(80))
    causation_event_id: Mapped[str | None] = mapped_column(
        sa.ForeignKey("case_events.id"), nullable=True
    )
    payload_version: Mapped[int] = mapped_column(sa.Integer, default=1)
    payload: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    provenance: Mapped[Provenance] = enum_column(Provenance, default=Provenance.LIVE)


class ActionRecordModel(Base):
    __tablename__ = "action_records"
    __table_args__ = (sa.Index("ix_action_case_state", "case_id", "state"),)

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"))
    kind: Mapped[str] = mapped_column(sa.String(40))
    target_id: Mapped[str | None] = mapped_column(sa.String(36), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(sa.String(160), unique=True)
    payload_hash: Mapped[str] = mapped_column(sa.String(64))
    proposal: Mapped[dict] = mapped_column(sa.JSON)
    state: Mapped[str] = mapped_column(sa.String(24))
    approval: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class JobModel(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        sa.Index("ix_job_status_runat", "status", "run_at"),
        sa.Index("ix_job_lease_until", "lease_until"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str | None] = mapped_column(sa.ForeignKey("repair_cases.id"), nullable=True)
    kind: Mapped[JobKind] = enum_column(JobKind)
    dedupe_key: Mapped[str] = mapped_column(sa.String(160), unique=True)
    payload: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    status: Mapped[JobStatus] = enum_column(JobStatus, default=JobStatus.PENDING)
    attempts: Mapped[int] = mapped_column(sa.Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class OrchestrationRunModel(Base):
    __tablename__ = "orchestration_runs"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("repair_cases.id"))
    trigger_event_id: Mapped[str] = mapped_column(sa.ForeignKey("case_events.id"))
    snapshot_version: Mapped[int] = mapped_column(sa.Integer)
    model_id: Mapped[str] = mapped_column(sa.String(64))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    state: Mapped[OrchestrationRunState] = enum_column(
        OrchestrationRunState, default=OrchestrationRunState.RUNNING
    )
    usage: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    proposal: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    tool_calls: Mapped[list[dict]] = mapped_column(sa.JSON, default=list)
    policy_result: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)


class MockSlotModel(Base):
    __tablename__ = "mock_slots"

    slot_id: Mapped[str] = mapped_column(sa.String(80), primary_key=True)
    contractor_id: Mapped[str] = mapped_column(sa.ForeignKey("contractors.id"))
    trade: Mapped[Trade] = enum_column(Trade)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revision: Mapped[int] = mapped_column(sa.Integer, default=1)
    is_reserved: Mapped[bool] = mapped_column(sa.Boolean, default=False)


class MockReservationModel(Base):
    __tablename__ = "mock_reservations"
    __table_args__ = (
        sa.Index(
            "uq_reservation_active_slot",
            "slot_id",
            unique=True,
            sqlite_where=sa.text("status = 'RESERVED'"),
        ),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    slot_id: Mapped[str] = mapped_column(sa.ForeignKey("mock_slots.slot_id"))
    work_order_id: Mapped[str] = mapped_column(sa.ForeignKey("work_orders.id"))
    action_id: Mapped[str] = mapped_column(sa.ForeignKey("action_records.id"))
    idempotency_key: Mapped[str] = mapped_column(sa.String(160), unique=True)
    provider_booking_id: Mapped[str] = mapped_column(sa.String(80))
    status: Mapped[str] = mapped_column(sa.String(16), default="RESERVED")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
