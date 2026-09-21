"""Turns an `ArchiveDataset` (dataset.py) into ORM rows, and back out again.

Idempotency: `import_archive` looks up `ArchiveBatchModel` by `label` before
doing anything else. If a batch with that label already exists, the import
is a no-op -- the dataset is never even regenerated. This is what makes
"run the import twice" safe: the second run performs zero writes.

Traceability: every table that has a `provenance` and/or `archive_batch_id`
column gets it set on every row this module writes (Provenance.FIXTURE /
this run's batch id) -- that now includes `PropertyModel`, `RepairCaseModel`,
`TenantModel`, `ContractorModel`, `CostEntryModel`, `NoteModel`,
`DocumentModel` and `MessageModel`. A few tables the archive must still
populate have no `archive_batch_id` column at all in the current schema
(`RepairIssueModel`, `WorkOrderModel`, `AppointmentModel`, `ActionRecordModel`,
`ContractorReportModel` -- see NEEDS_FROM_ROOT.md); two of those five
(`AppointmentModel`, `ContractorReportModel`) do carry `provenance`
(Provenance.FIXTURE / Provenance.SIMULATED respectively) and get that set,
but none of the five can be tagged by batch id directly. Those rows are
instead scoped structurally: they belong to the batch if their `case_id`
is one of the batch's cases (found via `RepairCaseModel.archive_batch_id`).
Removal uses exactly that same traversal for those five tables, and a plain
`archive_batch_id ==` delete for everything else, so it can never touch a
row with no path back to the batch.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.archive.dataset import (
    DEFAULT_LABEL,
    DEFAULT_SEED,
    MODEL_ID,
    ArchiveDataset,
    build_dataset,
    stable_id,
)
from app.config import get_settings
from app.models import (
    ActionRecordModel,
    ArchiveBatchModel,
    AppointmentModel,
    CaseEventModel,
    ContractorModel,
    ContractorReportModel,
    CostEntryModel,
    DependencyModel,
    DocumentModel,
    JobModel,
    MessageModel,
    NoteModel,
    OrchestrationRunModel,
    PropertyModel,
    RepairCaseModel,
    RepairIssueModel,
    TenantModel,
    WorkOrderModel,
)
from app.schemas import (
    ActionProposal,
    ActionState,
    AppointmentStatus,
    CaseStatus,
    ConnectorType,
    ContractorApprovalStatus,
    DependencyStatus,
    EvidenceRef,
    InterpretationStatus,
    MessageChannel,
    OrchestrationRunState,
    Provenance,
    RecordSubject,
    SourceType,
    ToolTrace,
    ToolTraceOutcome,
    VisitOutcome,
    WorkOrderStatus,
)


# --------------------------------------------------------------------------
# Result shapes
# --------------------------------------------------------------------------


@dataclass
class ImportResult:
    label: str
    batch_id: str | None
    skipped: bool
    counts: dict[str, int] = field(default_factory=dict)
    documents_written: list[str] = field(default_factory=list)
    # Deliberately *not* a key inside `counts`: `counts`'s exact key set is
    # asserted verbatim elsewhere (tests/test_archive_import.py compares
    # `result.counts == expected` for a fixed, hand-written key set), so a
    # new key there would break that check even though it passed nothing
    # wrong. This field is purely additive to the dataclass instead.
    report_count: int = 0
    # Same reasoning: additive, not inside `counts`.
    case_event_count: int = 0
    orchestration_run_count: int = 0
    dependency_count: int = 0


@dataclass
class RemovalResult:
    label: str
    found: bool
    counts: dict[str, int] = field(default_factory=dict)
    documents_removed: list[str] = field(default_factory=list)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ValidationReport:
    label: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------


def _is_async_session(candidate: Any) -> bool:
    return isinstance(candidate, AsyncSession)


async def import_archive(
    session_or_scope: AsyncSession | Callable[[], Any] | None = None,
    *,
    label: str = DEFAULT_LABEL,
    seed: int = DEFAULT_SEED,
) -> ImportResult:
    """Imports the synthetic archive once, keyed on `label`.

    `session_or_scope` may be an existing `AsyncSession` (caller manages
    commit -- typical in tests), a callable async-context-manager factory
    such as `app.db.session_scope` (this function opens and commits its own
    transaction), or None (defaults to `app.db.session_scope`).
    """
    if session_or_scope is None:
        from app.db import session_scope as session_or_scope  # local import: avoid a hard app.db dependency at module import time for pure callers

    if _is_async_session(session_or_scope):
        return await _import_with_session(session_or_scope, label=label, seed=seed)

    async with session_or_scope() as session:  # type: ignore[misc]
        return await _import_with_session(session, label=label, seed=seed)


async def _import_with_session(session: AsyncSession, *, label: str, seed: int) -> ImportResult:
    existing = (
        await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == label))
    ).scalar_one_or_none()
    if existing is not None:
        return ImportResult(label=label, batch_id=existing.id, skipped=True, counts={})

    dataset = build_dataset(seed=seed, label=label)
    settings = get_settings()

    counts = {
        "properties": 0, "tenants": 0, "contractors": 0, "cases": 0, "issues": 0,
        "work_orders": 0, "appointments": 0, "action_records": 0, "costs": 0,
        "notes": 0, "messages": 0, "documents": 0,
    }
    documents_written: list[str] = []
    report_count = 0
    case_event_count = 0
    orchestration_run_count = 0
    dependency_count = 0

    batch = ArchiveBatchModel(
        id=stable_id(f"archive:batch:{label}"),
        label=label,
        generator_version=dataset.generator_version,
        random_seed=dataset.random_seed,
        description=dataset.description,
    )
    session.add(batch)
    await session.flush()
    batch_id = batch.id

    for prop in dataset.properties:
        session.add(
            PropertyModel(
                id=prop.id, address_line=prop.address_line, postcode=prop.postcode,
                landlord_reference=prop.landlord_reference, roof_responsibility=prop.roof_responsibility,
                access_notes=prop.access_notes, build_year=prop.build_year, property_type=prop.property_type,
                bedrooms=prop.bedrooms, photo_key=prop.photo_key, archive_batch_id=batch_id,
            )
        )
        counts["properties"] += 1

    for tenant in dataset.tenants:
        session.add(
            TenantModel(
                id=tenant.id, property_id=dataset.property_id(tenant.property_key),
                display_name=tenant.display_name, phone_e164=None, email=None,
                preferred_channel=tenant.preferred_channel, contact_allowed=False,
                accessibility_notes=None, archive_batch_id=batch_id,
            )
        )
        counts["tenants"] += 1

    for contractor in dataset.contractors:
        session.add(
            ContractorModel(
                id=contractor.id, display_name=contractor.display_name, trades=contractor.trades,
                service_postcodes=contractor.service_postcodes,
                approval_status=ContractorApprovalStatus.PENDING, connector=ConnectorType.MOCK,
                contact_reference=None, verification_note=contractor.verification_note,
                provenance=Provenance.FIXTURE, workers=[], archive_batch_id=batch_id,
            )
        )
        counts["contractors"] += 1

    await session.flush()  # properties/tenants/contractors before anything FK-ing them

    next_number = (
        await session.execute(sa.select(sa.func.coalesce(sa.func.max(RepairCaseModel.case_number), 0)))
    ).scalar_one() + 1

    def take_number() -> int:
        nonlocal next_number
        n = next_number
        next_number += 1
        return n

    for case in sorted(dataset.cases, key=lambda c: c.created_at):
        property_id = dataset.property_id(case.property_key)
        tenant_id = dataset.tenant_id(case.property_key)

        evidence_dicts = [
            EvidenceRef(
                source_type=ref.source_type, source_id=uuid.UUID(case.id), locator=ref.locator,
                observed_at=ref.observed_at, provenance=ref.provenance,
            ).model_dump(mode="json")
            for ref in case.evidence_refs
        ]

        session.add(
            RepairCaseModel(
                id=case.id, case_number=take_number(), property_id=property_id, tenant_id=tenant_id,
                status=case.status, version=1, title=case.title, risk={"urgency": case.urgency},
                created_at=case.created_at, updated_at=case.archived_closed_at,
                owner_operator_id="operator", last_decision_summary=case.last_decision_summary,
                next_follow_up_at=None, escalation_reason=None, resume_status=None,
                category=case.category, archive_batch_id=batch_id, archived_closed_at=case.archived_closed_at,
            )
        )
        counts["cases"] += 1

        issue_id = stable_id(f"archive:issue:{case.label}")
        session.add(
            RepairIssueModel(
                id=issue_id, case_id=case.id, description=case.description, location=case.location,
                started_at=case.created_at, evidence_refs=evidence_dicts,
                tenant_resolution_confirmed_at=None, unresolved_concerns=[],
            )
        )
        counts["issues"] += 1

        await session.flush()  # case + issue before work orders

        work_order_ids: list[str] = []
        work_order_models: list[WorkOrderModel] = []
        for wo in case.work_orders:
            contractor_id = dataset.contractor_id(wo.contractor_key) if wo.contractor_key else None
            wo_model = WorkOrderModel(
                id=wo.id, case_id=case.id, issue_id=issue_id, kind=wo.kind, trade=wo.trade,
                scope=wo.scope, status=wo.status, contractor_id=contractor_id,
                required_for_resolution=True, quote_pence=wo.quote_pence,
                approved_limit_pence=wo.approved_limit_pence, created_at=wo.created_at,
                updated_at=wo.updated_at,
            )
            session.add(wo_model)
            work_order_ids.append(wo.id)
            work_order_models.append(wo_model)  # kept so the reports loop below can set completion_report_id
            counts["work_orders"] += 1

        await session.flush()  # work orders before appointments/action records referencing them

        for i, appt in enumerate(case.appointments):
            wo = case.work_orders[appt.work_order_index]
            contractor_id = dataset.contractor_id(appt.contractor_key)
            proposal = {
                "case_id": case.id,
                "expected_case_version": appt.action_expected_case_version,
                "trigger_event_id": stable_id(f"archive:trigger:{case.label}:{i}"),
                "decision_summary": "Archival record: contractor visit booked and attended.",
                "evidence_refs": [],
                "action": {
                    "kind": "SCHEDULE_VISIT", "work_order_id": wo.id, "contractor_id": contractor_id,
                    "slot_id": appt.slot_id, "tenant_availability_ids": [],
                },
            }
            session.add(
                ActionRecordModel(
                    id=appt.action_id, case_id=case.id, kind="SCHEDULE_VISIT", target_id=wo.id,
                    idempotency_key=appt.action_idempotency_key,
                    payload_hash=stable_id(f"archive:hash:{case.label}:{i}").replace("-", "")[:64],
                    proposal=proposal, state=ActionState.SUCCEEDED.value,
                    created_at=appt.action_created_at, updated_at=appt.action_updated_at,
                )
            )
            counts["action_records"] += 1

        await session.flush()  # action records before appointments referencing action_id

        for i, appt in enumerate(case.appointments):
            wo = case.work_orders[appt.work_order_index]
            contractor_id = dataset.contractor_id(appt.contractor_key)
            session.add(
                AppointmentModel(
                    id=appt.id, case_id=case.id, work_order_id=wo.id, contractor_id=contractor_id,
                    slot_id=appt.slot_id, start_at=appt.start_at, end_at=appt.end_at,
                    status=AppointmentStatus.FINISHED, visit_outcome=appt.visit_outcome,
                    connector=ConnectorType.MOCK, provider_booking_id=None, action_id=appt.action_id,
                    attempt_number=appt.attempt_number, availability_revision=1,
                    provenance=Provenance.FIXTURE,
                )
            )
            counts["appointments"] += 1

        await session.flush()  # appointments before reports referencing appointment_id

        for i, appt in enumerate(case.appointments):
            report = case.reports[i]
            wo_model = work_order_models[appt.work_order_index]
            contractor_id = dataset.contractor_id(report.contractor_key)
            session.add(
                ContractorReportModel(
                    id=report.id, case_id=case.id, work_order_id=wo_model.id, appointment_id=appt.id,
                    contractor_id=contractor_id, text=report.text, observed_at=report.observed_at,
                    received_at=report.received_at,
                    # Mirrors POST /cases/{case_id}/reports (app/api/cases.py
                    # submit_report): SourceType.OPERATOR + Provenance.SIMULATED
                    # for both the evidence ref and the report row itself --
                    # this archive's only difference from a live submission is
                    # a stable, deterministic source_id instead of uuid4().
                    source_ref=EvidenceRef(
                        source_type=SourceType.OPERATOR,
                        source_id=uuid.UUID(stable_id(f"archive:report-source:{case.label}:{i}")),
                        observed_at=report.observed_at, provenance=Provenance.SIMULATED,
                    ).model_dump(mode="json"),
                    provenance=Provenance.SIMULATED,
                    # Every archival case is already RESOLVED/CANCELLED, so by
                    # construction every report in it has already gone through
                    # the accept_report workflow (real accept_report sets this
                    # unconditionally, whatever the outcome) -- PENDING here
                    # would misrepresent closed history as still awaiting
                    # operator review. No matching ACCEPT_REPORT action record
                    # exists in this archive, so interpreted_action_id stays
                    # None rather than pointing at a row that isn't there.
                    interpretation_status=InterpretationStatus.APPLIED,
                    interpreted_action_id=None,
                )
            )
            report_count += 1
            if appt.visit_outcome == VisitOutcome.COMPLETED:
                # Mirrors accept_report's `work_order.completion_report_id =
                # report.id`, set only on the outcome that actually finished
                # the job -- a failed/no-access attempt's report never earns
                # this on the real code path either.
                wo_model.completion_report_id = report.id

        # A BLOCKED visit's dependency is real structure, not just report
        # flavour (see dataset.py's _inject_dependency_if_applicable): a
        # genuine prerequisite work order, satisfied before the case
        # closed. Both FK targets (discovered_from_report_id/
        # satisfied_by_report_id) are already-known report ids -- dataset.py
        # builds ArchiveContractorReport.id deterministically, the same way
        # every other id in this module already is.
        for dep in case.dependencies:
            prerequisite_wo = work_order_models[dep.prerequisite_work_order_index]
            dependent_wo = work_order_models[dep.dependent_work_order_index]
            session.add(
                DependencyModel(
                    id=dep.id, case_id=case.id,
                    prerequisite_work_order_id=prerequisite_wo.id, dependent_work_order_id=dependent_wo.id,
                    status=DependencyStatus.SATISFIED, reason=dep.reason,
                    discovered_from_report_id=case.reports[dep.discovered_from_appointment_index].id,
                    satisfied_by_report_id=case.reports[dep.satisfied_by_appointment_index].id,
                    satisfied_at=dep.satisfied_at,
                )
            )
            dependency_count += 1

        # --- case event log ----------------------------------------------
        # Inserted in case.events' own order, which dataset.py already
        # sorted into strict chronological order -- every event's
        # causation_event_id (a self-referential FK on this same table)
        # points at an earlier sibling that this loop has therefore
        # already added to the session by the time it is referenced.
        for seq, event in enumerate(case.events, start=1):
            session.add(
                CaseEventModel(
                    id=event.id, case_id=case.id, seq=seq, type=event.type,
                    occurred_at=event.occurred_at, received_at=event.received_at,
                    actor_type=event.actor_type, actor_id=event.actor_id,
                    source_event_key=event.source_event_key, correlation_id=event.correlation_id,
                    causation_event_id=event.causation_event_id, payload_version=1,
                    payload=event.payload, provenance=Provenance.FIXTURE,
                )
            )
        case_event_count += len(case.events)

        # --- coordinator decision history ---------------------------------
        # `action` is already the fully-resolved inner NextAction payload
        # (dataset.py substituted real work-order/contractor/report ids in
        # directly); this wraps it in the outer ActionProposal envelope and
        # validates the whole thing against the real schema before writing
        # it -- a shape bug in the generator fails the import loudly here
        # instead of shipping a malformed JSON blob nobody notices until a
        # UI tries to render it.
        for run in case.runs:
            proposal = ActionProposal.model_validate(
                {
                    "case_id": case.id, "expected_case_version": 1, "trigger_event_id": run.trigger_event_id,
                    "decision_summary": run.decision_summary, "evidence_refs": [], "action": run.action,
                }
            ).model_dump(mode="json")

            tool_calls: list[dict] = []
            cursor = run.started_at
            for idx, tool_name in enumerate(run.tool_names):
                remaining = len(run.tool_names) - idx
                slice_end = cursor + (run.finished_at - cursor) / remaining if remaining > 1 else run.finished_at
                trace = ToolTrace(
                    id=stable_id(f"archive:tool:{run.id}:{idx}"), run_id=run.id, name=tool_name,
                    started_at=cursor, finished_at=slice_end, outcome=ToolTraceOutcome.SUCCEEDED,
                    input_resource_ids=[case.id], output_resource_ids=[],
                )
                tool_calls.append(trace.model_dump(mode="json"))
                cursor = slice_end

            session.add(
                OrchestrationRunModel(
                    id=run.id, case_id=case.id, trigger_event_id=run.trigger_event_id,
                    snapshot_version=1, model_id=MODEL_ID, started_at=run.started_at, finished_at=run.finished_at,
                    state=OrchestrationRunState.SUCCEEDED, usage={}, proposal=proposal,
                    tool_calls=tool_calls, policy_result=ActionState.SUCCEEDED.value, error_code=None,
                )
            )
        orchestration_run_count += len(case.runs)

        for cost in case.costs:
            wo_id = work_order_ids[cost.work_order_index] if cost.work_order_index is not None else None
            session.add(
                CostEntryModel(
                    id=cost.id, case_id=case.id, work_order_id=wo_id, kind=cost.kind,
                    amount_pence=cost.amount_pence, description=cost.description,
                    incurred_at=cost.incurred_at, recorded_by="archive-import",
                    recorded_at=cost.incurred_at, archive_batch_id=batch_id,
                )
            )
            counts["costs"] += 1

        for note in case.notes:
            session.add(
                NoteModel(
                    id=note.id, subject_type=RecordSubject.CASE, subject_id=case.id, body=note.body,
                    author=note.author, created_at=note.created_at, updated_at=note.created_at,
                    archive_batch_id=batch_id,
                )
            )
            counts["notes"] += 1

        for msg in case.messages:
            session.add(
                MessageModel(
                    id=msg.id, case_id=case.id, sender_type=msg.sender_type, sender_name=msg.sender_name,
                    text=msg.text, photo_url=None, created_at=msg.created_at,
                    channel=MessageChannel.INTERNAL, delivery_state=msg.delivery_state,
                    delivery_detail=None, queued_at=None, delivered_at=None, read_at=msg.read_at,
                    attachments=[], communication_id=None, archive_batch_id=batch_id,
                )
            )
            counts["messages"] += 1

        if case.document is not None:
            doc = case.document
            doc_path = settings.documents_dir / doc.stored_name
            data = doc.content.encode("utf-8")
            doc_path.write_bytes(data)
            documents_written.append(str(doc_path))
            session.add(
                DocumentModel(
                    id=stable_id(f"archive:documentrow:{case.label}"), subject_type=RecordSubject.CASE,
                    subject_id=case.id, display_name=doc.display_name, stored_name=doc.stored_name,
                    content_type="text/plain", size_bytes=len(data), description=doc.description,
                    uploaded_by="archive-import", uploaded_at=doc.uploaded_at, archive_batch_id=batch_id,
                )
            )
            counts["documents"] += 1

        await session.flush()

    return ImportResult(
        label=label, batch_id=batch_id, skipped=False, counts=counts,
        documents_written=documents_written, report_count=report_count,
        case_event_count=case_event_count, orchestration_run_count=orchestration_run_count,
        dependency_count=dependency_count,
    )


# --------------------------------------------------------------------------
# Removal
# --------------------------------------------------------------------------


async def _delete_where(session: AsyncSession, model: Any, condition: Any) -> int:
    result = await session.execute(sa.delete(model).where(condition))
    return result.rowcount or 0


async def remove_archive(label: str = DEFAULT_LABEL) -> RemovalResult:
    from app.db import session_scope

    async with session_scope() as session:
        batch = (
            await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == label))
        ).scalar_one_or_none()
        if batch is None:
            return RemovalResult(label=label, found=False)

        batch_id = batch.id

        case_ids = (
            await session.execute(sa.select(RepairCaseModel.id).where(RepairCaseModel.archive_batch_id == batch_id))
        ).scalars().all()

        settings = get_settings()
        doc_rows = (
            await session.execute(sa.select(DocumentModel).where(DocumentModel.archive_batch_id == batch_id))
        ).scalars().all()
        documents_removed: list[str] = []
        for doc in doc_rows:
            path = settings.documents_dir / doc.stored_name
            if path.exists():
                path.unlink()
                documents_removed.append(str(path))

        counts: dict[str, int] = {}
        counts["costs"] = await _delete_where(session, CostEntryModel, CostEntryModel.archive_batch_id == batch_id)
        counts["documents"] = await _delete_where(session, DocumentModel, DocumentModel.archive_batch_id == batch_id)
        counts["notes"] = await _delete_where(session, NoteModel, NoteModel.archive_batch_id == batch_id)
        counts["messages"] = await _delete_where(session, MessageModel, MessageModel.archive_batch_id == batch_id)

        if case_ids:
            # `foreign_keys=ON` (app/db.py) enforces this order: dependencies
            # reference both work_orders.id and contractor_reports.id, and
            # orchestration_runs references case_events.id, so both go
            # before the tables they point at; contractor reports reference
            # both work_orders.id and appointments.id, so they must go
            # before either of those two, and well before ContractorModel
            # further down. case_events' own causation_event_id is
            # self-referential, but every row for these case_ids is removed
            # together in one statement, so there is nothing left dangling
            # by the time it completes.
            counts["dependencies"] = await _delete_where(session, DependencyModel, DependencyModel.case_id.in_(case_ids))
            counts["orchestration_runs"] = await _delete_where(session, OrchestrationRunModel, OrchestrationRunModel.case_id.in_(case_ids))
            counts["case_events"] = await _delete_where(session, CaseEventModel, CaseEventModel.case_id.in_(case_ids))
            counts["contractor_reports"] = await _delete_where(session, ContractorReportModel, ContractorReportModel.case_id.in_(case_ids))
            counts["appointments"] = await _delete_where(session, AppointmentModel, AppointmentModel.case_id.in_(case_ids))
            counts["action_records"] = await _delete_where(session, ActionRecordModel, ActionRecordModel.case_id.in_(case_ids))
            counts["work_orders"] = await _delete_where(session, WorkOrderModel, WorkOrderModel.case_id.in_(case_ids))
            counts["issues"] = await _delete_where(session, RepairIssueModel, RepairIssueModel.case_id.in_(case_ids))
        else:
            counts["dependencies"] = counts["orchestration_runs"] = counts["case_events"] = 0
            counts["contractor_reports"] = counts["appointments"] = counts["action_records"] = counts["work_orders"] = counts["issues"] = 0

        counts["cases"] = await _delete_where(session, RepairCaseModel, RepairCaseModel.archive_batch_id == batch_id)

        # TenantModel and ContractorModel both carry archive_batch_id directly
        # (added alongside PropertyModel's), so these are plain, exact deletes --
        # no traversal or id-regeneration needed. Order still respects FK
        # direction: Tenant is RepairCaseModel's parent (deleted above),
        # Contractor is WorkOrderModel/AppointmentModel's parent (deleted above).
        counts["tenants"] = await _delete_where(session, TenantModel, TenantModel.archive_batch_id == batch_id)
        counts["properties"] = await _delete_where(session, PropertyModel, PropertyModel.archive_batch_id == batch_id)
        counts["contractors"] = await _delete_where(session, ContractorModel, ContractorModel.archive_batch_id == batch_id)

        counts["archive_batches"] = await _delete_where(session, ArchiveBatchModel, ArchiveBatchModel.id == batch_id)

        return RemovalResult(label=label, found=True, counts=counts, documents_removed=documents_removed)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


async def validate(session: AsyncSession, *, label: str = DEFAULT_LABEL, seed: int = DEFAULT_SEED) -> ValidationReport:
    report = ValidationReport(label=label)

    def check(name: str, fn) -> None:
        try:
            ok, detail = fn()
            report.checks.append(CheckResult(name=name, passed=bool(ok), detail=detail))
        except Exception as exc:  # defensive: one bad check must not blank out the rest
            report.checks.append(CheckResult(name=name, passed=False, detail=f"error: {exc!r}"))

    batch = (
        await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == label))
    ).scalar_one_or_none()
    if batch is None:
        report.checks.append(CheckResult(name="batch_exists", passed=False, detail=f"no batch with label {label!r}"))
        return report
    report.checks.append(CheckResult(name="batch_exists", passed=True, detail=batch.id))
    batch_id = batch.id

    # --- referential integrity (whole-DB; SQLite's own FK auditor) --------
    fk_rows = (await session.execute(sa.text("PRAGMA foreign_key_check"))).fetchall()

    def _fk_check():
        return (len(fk_rows) == 0, f"{len(fk_rows)} dangling FK row(s)" if fk_rows else "clean")

    check("referential_integrity", _fk_check)

    cases = (
        await session.execute(sa.select(RepairCaseModel).where(RepairCaseModel.archive_batch_id == batch_id))
    ).scalars().all()
    case_ids = [c.id for c in cases]
    cases_by_id = {c.id: c for c in cases}

    issues = (
        await session.execute(sa.select(RepairIssueModel).where(RepairIssueModel.case_id.in_(case_ids)))
    ).scalars().all() if case_ids else []
    work_orders = (
        await session.execute(sa.select(WorkOrderModel).where(WorkOrderModel.case_id.in_(case_ids)))
    ).scalars().all() if case_ids else []
    appointments = (
        await session.execute(sa.select(AppointmentModel).where(AppointmentModel.case_id.in_(case_ids)))
    ).scalars().all() if case_ids else []
    reports = (
        await session.execute(sa.select(ContractorReportModel).where(ContractorReportModel.case_id.in_(case_ids)))
    ).scalars().all() if case_ids else []
    case_events = (
        await session.execute(sa.select(CaseEventModel).where(CaseEventModel.case_id.in_(case_ids)))
    ).scalars().all() if case_ids else []
    orchestration_runs = (
        await session.execute(sa.select(OrchestrationRunModel).where(OrchestrationRunModel.case_id.in_(case_ids)))
    ).scalars().all() if case_ids else []
    costs = (
        await session.execute(sa.select(CostEntryModel).where(CostEntryModel.archive_batch_id == batch_id))
    ).scalars().all()
    messages = (
        await session.execute(sa.select(MessageModel).where(MessageModel.archive_batch_id == batch_id))
    ).scalars().all()

    work_orders_by_id = {w.id: w for w in work_orders}
    now = datetime.now(timezone.utc)

    def _timestamps_check():
        problems: list[str] = []
        for case in cases:
            if case.created_at >= now:
                problems.append(f"case {case.id} created_at not in the past")
            if case.archived_closed_at is None or case.archived_closed_at >= now:
                problems.append(f"case {case.id} archived_closed_at not in the past")
            if case.archived_closed_at is not None and case.created_at >= case.archived_closed_at:
                problems.append(f"case {case.id} created_at not before archived_closed_at")
        case_work_orders: dict[str, list[WorkOrderModel]] = {}
        for wo in work_orders:
            case_work_orders.setdefault(wo.case_id, []).append(wo)
        for case_id, wos in case_work_orders.items():
            first_wo = min(wos, key=lambda w: w.created_at)
            case = cases_by_id.get(case_id)
            if case is not None and case.created_at >= first_wo.created_at:
                problems.append(f"case {case_id} created_at not before first work order")
        for appt in appointments:
            wo = work_orders_by_id.get(appt.work_order_id)
            if wo is not None and wo.created_at > appt.start_at:
                problems.append(f"appointment {appt.id} starts before its work order was created")
            if appt.start_at >= appt.end_at:
                problems.append(f"appointment {appt.id} end_at not after start_at")
            if appt.end_at >= now:
                problems.append(f"appointment {appt.id} end_at not in the past")
            case = cases_by_id.get(appt.case_id)
            if case is not None and case.archived_closed_at is not None and appt.end_at > case.archived_closed_at:
                problems.append(f"appointment {appt.id} ends after its case's archived_closed_at")
        return (len(problems) == 0, "; ".join(problems[:5]) or "clean")

    check("timestamps_ordered_and_past", _timestamps_check)

    def _durations_costs_check():
        problems: list[str] = []
        for appt in appointments:
            if (appt.end_at - appt.start_at).total_seconds() <= 0:
                problems.append(f"appointment {appt.id} nonpositive duration")
        case_totals: dict[str, int] = {}
        for cost in costs:
            if cost.kind.value in ("QUOTE", "INVOICE") and cost.amount_pence < 0:
                problems.append(f"cost {cost.id} negative {cost.kind.value}")
            case_totals[cost.case_id] = case_totals.get(cost.case_id, 0) + cost.amount_pence
        for case_id, total in case_totals.items():
            if total <= 0:
                problems.append(f"case {case_id} total cost not positive ({total})")
        return (len(problems) == 0, "; ".join(problems[:5]) or "clean")

    check("nonnegative_durations_and_costs", _durations_costs_check)

    def _no_open_pending_check():
        problems: list[str] = []
        for case in cases:
            if case.status not in (CaseStatus.RESOLVED, CaseStatus.CANCELLED):
                problems.append(f"case {case.id} not terminal ({case.status})")
        for wo in work_orders:
            if wo.status not in (WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED):
                problems.append(f"work order {wo.id} not terminal ({wo.status})")
        for appt in appointments:
            if appt.status not in (AppointmentStatus.FINISHED, AppointmentStatus.CANCELLED):
                problems.append(f"appointment {appt.id} not terminal ({appt.status})")
            if appt.visit_outcome is None:
                problems.append(f"appointment {appt.id} missing visit_outcome")
        return (len(problems) == 0, "; ".join(problems[:5]) or "clean")

    check("no_open_or_pending_work", _no_open_pending_check)

    def _contractor_reports_check():
        """A completed visit produces a contractor's write-up, exactly as a
        real one would (docs/audit finding: the archive generated 0 of
        them). Checks the invariant end to end: every FINISHED appointment
        has exactly one report; every COMPLETED work order's
        `completion_report_id` points at a real report against the same
        work order; and no report is timestamped before the visit it
        describes or after the case it belongs to was closed."""
        problems: list[str] = []
        reports_by_appointment: dict[str, list] = {}
        for r in reports:
            reports_by_appointment.setdefault(r.appointment_id, []).append(r)

        for appt in appointments:
            matches = reports_by_appointment.get(appt.id, [])
            if not matches:
                problems.append(f"appointment {appt.id} (FINISHED) has no contractor report")
            elif len(matches) > 1:
                problems.append(f"appointment {appt.id} has {len(matches)} contractor reports")

        report_ids = {r.id for r in reports}
        for wo in work_orders:
            if wo.status != WorkOrderStatus.COMPLETED:
                continue
            if not wo.completion_report_id:
                problems.append(f"work order {wo.id} COMPLETED with no completion_report_id")
            elif wo.completion_report_id not in report_ids:
                problems.append(f"work order {wo.id} completion_report_id does not match any report")

        appts_by_id = {a.id: a for a in appointments}
        for r in reports:
            appt = appts_by_id.get(r.appointment_id)
            case = cases_by_id.get(r.case_id)
            if appt is not None and r.observed_at < appt.end_at:
                problems.append(f"report {r.id} observed_at is before its visit ended")
            if r.received_at < r.observed_at:
                problems.append(f"report {r.id} received_at is before observed_at")
            if case is not None and case.archived_closed_at is not None:
                if r.observed_at > case.archived_closed_at:
                    problems.append(f"report {r.id} observed_at is after case closure")
                if r.received_at > case.archived_closed_at:
                    problems.append(f"report {r.id} received_at is after case closure")

        return (len(problems) == 0, "; ".join(problems[:5]) or "clean")

    check("contractor_reports_complete_and_ordered", _contractor_reports_check)

    events_by_case: dict[str, list] = {}
    for e in case_events:
        events_by_case.setdefault(e.case_id, []).append(e)

    def _every_case_has_event_log_check():
        problems = [case.id for case in cases if not events_by_case.get(case.id)]
        return (len(problems) == 0, "clean" if not problems else f"{len(problems)} case(s) with no event log, e.g. {problems[:3]}")

    check("every_case_has_an_event_log", _every_case_has_event_log_check)

    def _seq_monotonic_check():
        problems: list[str] = []
        for case_id, evs in events_by_case.items():
            seqs = sorted(e.seq for e in evs)
            if seqs != list(range(1, len(seqs) + 1)):
                problems.append(f"case {case_id} seq={seqs[:8]}")
        return (len(problems) == 0, "; ".join(problems[:5]) or "clean")

    check("event_seq_monotonic_per_case", _seq_monotonic_check)

    def _no_event_postdates_closure_check():
        problems: list[str] = []
        for case_id, evs in events_by_case.items():
            case = cases_by_id.get(case_id)
            if case is None or case.archived_closed_at is None:
                continue
            for e in evs:
                if e.occurred_at > case.archived_closed_at:
                    problems.append(f"event {e.id} ({e.type}) postdates case {case_id}'s closure")
        return (len(problems) == 0, "; ".join(problems[:5]) or "clean")

    check("no_event_postdates_closure", _no_event_postdates_closure_check)

    def _terminal_event_matches_closure_check():
        # Hard requirement (CLAUDE.md/this generator's brief): the terminal
        # CASE_RESOLVED/CASE_CANCELLED event must land at exactly
        # archived_closed_at, or app.analytics.property_history_items (which
        # reads this event for a property-history resolution date) and the
        # case's own archived_closed_at column show two different closure
        # dates for the same case on two screens.
        expected_terminal = {"RESOLVED": "CASE_RESOLVED", "CANCELLED": "CASE_CANCELLED"}
        problems: list[str] = []
        for case_id, evs in events_by_case.items():
            case = cases_by_id.get(case_id)
            if case is None:
                continue
            status_value = case.status.value if hasattr(case.status, "value") else case.status
            want_type = expected_terminal.get(status_value)
            if want_type is None:
                continue
            terminal = max(evs, key=lambda e: e.seq)
            if terminal.type != want_type:
                problems.append(f"case {case_id} terminal event is {terminal.type}, expected {want_type}")
            elif case.archived_closed_at is not None and terminal.occurred_at != case.archived_closed_at:
                problems.append(
                    f"case {case_id} terminal event at {terminal.occurred_at} != archived_closed_at {case.archived_closed_at}"
                )
        return (len(problems) == 0, "; ".join(problems[:5]) or "clean")

    check("terminal_event_matches_case_closure", _terminal_event_matches_closure_check)

    def _run_trigger_resolves_check():
        event_ids_by_case: dict[str, set] = {cid: {e.id for e in evs} for cid, evs in events_by_case.items()}
        problems: list[str] = []
        for run in orchestration_runs:
            case_event_ids = event_ids_by_case.get(run.case_id, set())
            if run.trigger_event_id not in case_event_ids:
                problems.append(f"run {run.id} trigger_event_id {run.trigger_event_id} not an event on case {run.case_id}")
        return (len(problems) == 0, "; ".join(problems[:5]) or "clean")

    check("run_trigger_resolves_to_same_case_event", _run_trigger_resolves_check)

    def _no_live_model_id_check():
        # CLAUDE.md: "no fake live traces" -- an archival run's model_id
        # must never name a real model (this project's operational model
        # is Gemini; docs/13/CLAUDE.md's "Pydantic AI ... Gemini is the
        # operational reasoning model"), or a reader could mistake
        # generated reasoning for output a real model produced.
        problems = sorted({r.model_id for r in orchestration_runs if "gemini" in r.model_id.lower() or r.model_id != MODEL_ID})
        return (len(problems) == 0, "clean" if not problems else f"unexpected model_id(s): {problems[:5]}")

    check("no_live_model_id_on_archival_runs", _no_live_model_id_check)

    # Scoped to the batch's own cases, not the whole table. The claim
    # being checked is "this import created no durable work" -- a real
    # database will have thousands of legitimate jobs from genuine cases,
    # and counting those turned a passing import into a false failure the
    # first time this ran anywhere other than an empty database.
    job_count = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(JobModel)
            .where(JobModel.case_id.in_(case_ids))
        )
    ).scalar_one() if case_ids else 0
    report.checks.append(
        CheckResult(
            name="no_jobs", passed=job_count == 0,
            detail=(
                f"{job_count} job row(s) against archival cases" if job_count else "clean"
            ),
        )
    )

    def _no_future_appointments_check():
        problems = [a.id for a in appointments if a.start_at >= now or a.end_at >= now]
        return (len(problems) == 0, f"{len(problems)} future appointment(s)" if problems else "clean")

    check("no_future_appointments", _no_future_appointments_check)

    def _no_unread_messages_check():
        problems = [m.id for m in messages if m.read_at is None]
        return (len(problems) == 0, f"{len(problems)} unread message(s)" if problems else "clean")

    check("no_unread_messages", _no_unread_messages_check)

    tenants = (
        await session.execute(sa.select(TenantModel).where(TenantModel.archive_batch_id == batch_id))
    ).scalars().all()
    contractors = (
        await session.execute(sa.select(ContractorModel).where(ContractorModel.archive_batch_id == batch_id))
    ).scalars().all()

    def _batch_tagging_check():
        problems: list[str] = []
        if not tenants:
            problems.append("no tenants tagged with this batch")
        if not contractors:
            problems.append("no contractors tagged with this batch")
        tenant_ids_in_batch = {t.id for t in tenants}
        used_tenant_ids = {c.tenant_id for c in cases}
        if not used_tenant_ids <= tenant_ids_in_batch:
            problems.append("a case's tenant is not tagged with this batch")
        contractor_ids_in_batch = {c.id for c in contractors}
        used_contractor_ids = {wo.contractor_id for wo in work_orders if wo.contractor_id} | {
            a.contractor_id for a in appointments
        }
        if not used_contractor_ids <= contractor_ids_in_batch:
            problems.append("a work order/appointment contractor is not tagged with this batch")
        return (len(problems) == 0, "; ".join(problems) or "clean")

    check("tenants_and_contractors_tagged", _batch_tagging_check)

    def _not_dialable_check():
        # These two properties are what actually stop the archive from ever
        # being dialled/booked -- assert them, don't just trust construction.
        problems: list[str] = []
        for c in contractors:
            if c.approval_status == ContractorApprovalStatus.APPROVED:
                problems.append(f"contractor {c.id} is APPROVED")
            if c.contact_reference is not None:
                problems.append(f"contractor {c.id} has a contact_reference")
        for t in tenants:
            if t.contact_allowed:
                problems.append(f"tenant {t.id} contact_allowed=True")
            if t.phone_e164 is not None or t.email is not None:
                problems.append(f"tenant {t.id} has a phone/email on file")
        return (len(problems) == 0, "; ".join(problems[:5]) or "clean")

    check("archival_contacts_not_dialable", _not_dialable_check)

    def _recurrence_check():
        by_property: dict[str, dict[str, int]] = {}
        for case in cases:
            if case.category is None:
                continue
            by_property.setdefault(case.property_id, {}).setdefault(case.category.value, 0)
            by_property[case.property_id][case.category.value] += 1
        properties_with_recurrence = sum(
            1 for cat_counts in by_property.values() if any(n >= 2 for n in cat_counts.values())
        )
        return (
            properties_with_recurrence >= 3,
            f"{properties_with_recurrence} propert(y/ies) with a repeated category",
        )

    check("recurrence_grouping", _recurrence_check)

    def _cost_reconciliation_check():
        flat_total = sum(c.amount_pence for c in costs)
        by_category: dict[str, int] = {}
        by_year: dict[int, int] = {}
        case_category = {c.id: c.category.value if c.category else None for c in cases}
        for cost in costs:
            category = case_category.get(cost.case_id)
            if category is not None:
                by_category[category] = by_category.get(category, 0) + cost.amount_pence
            by_year[cost.incurred_at.year] = by_year.get(cost.incurred_at.year, 0) + cost.amount_pence
        category_total = sum(by_category.values())
        year_total = sum(by_year.values())
        ok = category_total == flat_total == year_total
        return (ok, f"flat={flat_total} by_category={category_total} by_year={year_total}")

    check("cost_totals_reconcile", _cost_reconciliation_check)

    def _quoted_totals_reconcile_with_work_orders_check():
        # cost_totals_reconcile above only self-checks CostEntryModel
        # against itself -- it would still pass if every case's quoted
        # ledger were silently incomplete. This checks the actual
        # cross-table invariant docs/audit/06/11 flagged: for each case,
        # sum(WorkOrderModel.quote_pence, status != CANCELLED) must equal
        # sum(CostEntryModel.amount_pence, kind='QUOTE') *for QUOTE rows
        # tied to a non-CANCELLED work order* -- app.analytics.
        # reconciled_quotes never counts a QUOTE entry against a CANCELLED
        # work order either (a called-off job's quote is not "quoted"
        # money, even if the importer logged an estimate for it before it
        # was cancelled -- see _fill_cancelled_case), so this mirrors that
        # rule rather than naively summing every QUOTE row. Before
        # dataset.py started ledgering every RESOLVED-case work order (not
        # just work_orders[0]), this failed for ~48% of resolved cases; it
        # is checked here, not just relied on via reconciled_quotes' own
        # read-time fallback, so a future regression in the generator
        # fails the import's own validation instead of only being masked
        # at read time.
        cancelled_wo_ids = {wo.id for wo in work_orders if wo.status == WorkOrderStatus.CANCELLED}
        wo_quote_by_case: dict[str, int] = {}
        for wo in work_orders:
            if wo.id in cancelled_wo_ids or wo.quote_pence is None:
                continue
            wo_quote_by_case[wo.case_id] = wo_quote_by_case.get(wo.case_id, 0) + wo.quote_pence
        cost_quote_by_case: dict[str, int] = {}
        for cost in costs:
            if cost.kind.value == "QUOTE" and cost.work_order_id not in cancelled_wo_ids:
                cost_quote_by_case[cost.case_id] = cost_quote_by_case.get(cost.case_id, 0) + cost.amount_pence
        mismatches = [
            case_id for case_id in set(wo_quote_by_case) | set(cost_quote_by_case)
            if wo_quote_by_case.get(case_id, 0) != cost_quote_by_case.get(case_id, 0)
        ]
        return (
            len(mismatches) == 0,
            "clean" if not mismatches else f"{len(mismatches)} case(s) disagree, e.g. {mismatches[:3]}",
        )

    check("quoted_totals_reconcile_with_work_orders", _quoted_totals_reconcile_with_work_orders_check)

    async def _idempotency_check() -> tuple[bool, str]:
        result = await import_archive(session, label=label, seed=seed)
        ok = result.skipped and sum(result.counts.values()) == 0
        return (ok, f"skipped={result.skipped} counts={result.counts}")

    ok, detail = await _idempotency_check()
    report.checks.append(CheckResult(name="import_is_idempotent", passed=ok, detail=detail))

    return report
