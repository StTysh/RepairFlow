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
populate have neither column (`RepairIssueModel`, `WorkOrderModel`,
`AppointmentModel`, `ActionRecordModel` -- see NEEDS_FROM_ROOT.md), because
those columns don't exist on them at all in the current schema. Those rows
are instead scoped structurally: they belong to the batch if their `case_id`
is one of the batch's cases (found via `RepairCaseModel.archive_batch_id`).
Removal uses exactly that same traversal for those four tables, and a plain
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
    ArchiveDataset,
    build_dataset,
    stable_id,
)
from app.config import get_settings
from app.models import (
    ActionRecordModel,
    ArchiveBatchModel,
    AppointmentModel,
    ContractorModel,
    CostEntryModel,
    DocumentModel,
    JobModel,
    MessageModel,
    NoteModel,
    PropertyModel,
    RepairCaseModel,
    RepairIssueModel,
    TenantModel,
    WorkOrderModel,
)
from app.schemas import (
    ActionState,
    AppointmentStatus,
    CaseStatus,
    ConnectorType,
    ContractorApprovalStatus,
    EvidenceRef,
    MessageChannel,
    Provenance,
    RecordSubject,
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
        for wo in case.work_orders:
            contractor_id = dataset.contractor_id(wo.contractor_key) if wo.contractor_key else None
            session.add(
                WorkOrderModel(
                    id=wo.id, case_id=case.id, issue_id=issue_id, kind=wo.kind, trade=wo.trade,
                    scope=wo.scope, status=wo.status, contractor_id=contractor_id,
                    required_for_resolution=True, quote_pence=wo.quote_pence,
                    approved_limit_pence=wo.approved_limit_pence, created_at=wo.created_at,
                    updated_at=wo.updated_at,
                )
            )
            work_order_ids.append(wo.id)
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

    return ImportResult(label=label, batch_id=batch_id, skipped=False, counts=counts, documents_written=documents_written)


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
            counts["appointments"] = await _delete_where(session, AppointmentModel, AppointmentModel.case_id.in_(case_ids))
            counts["action_records"] = await _delete_where(session, ActionRecordModel, ActionRecordModel.case_id.in_(case_ids))
            counts["work_orders"] = await _delete_where(session, WorkOrderModel, WorkOrderModel.case_id.in_(case_ids))
            counts["issues"] = await _delete_where(session, RepairIssueModel, RepairIssueModel.case_id.in_(case_ids))
        else:
            counts["appointments"] = counts["action_records"] = counts["work_orders"] = counts["issues"] = 0

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
        # sum(CostEntryModel.amount_pence, kind='QUOTE'). Before dataset.py
        # started ledgering every work order (not just work_orders[0]),
        # this failed for ~48% of resolved cases; it is checked here, not
        # just relied on via app.analytics.reconciled_quotes' read-time
        # fallback, so a future regression in the generator fails the
        # import's own validation instead of only being masked at read
        # time.
        wo_quote_by_case: dict[str, int] = {}
        for wo in work_orders:
            if wo.status == WorkOrderStatus.CANCELLED or wo.quote_pence is None:
                continue
            wo_quote_by_case[wo.case_id] = wo_quote_by_case.get(wo.case_id, 0) + wo.quote_pence
        cost_quote_by_case: dict[str, int] = {}
        for cost in costs:
            if cost.kind.value == "QUOTE":
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
