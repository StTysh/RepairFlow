"""Tests for app.archive (dataset generation + import/remove/validate).

Uses its own fixture (not backend/tests/conftest.py's `app_db`) because the
archive importer also needs DOCUMENTS_DIR repointed at a throwaway
directory -- it writes real files under settings.documents_dir for the
DocumentModel rows it creates, and must never touch a developer's real
backend/data/documents. The fixture below follows the same pattern as
conftest.py's `app_db` (temp file DB, repoint the process-wide app.db
singleton, clear the cached Settings, clean up on teardown) plus that one
extra directory.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa

import app.db as db_module
from app.archive.dataset import DEFAULT_LABEL, build_dataset
from app.archive.importer import import_archive, remove_archive, validate
from app.config import get_settings
from app.models import (
    ActionRecordModel,
    AppointmentModel,
    ArchiveBatchModel,
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
    CaseStatus,
    ConnectorType,
    ContractorApprovalStatus,
    Provenance,
    RepairIssue,
    RoofResponsibility,
    WorkOrderStatus,
)


@pytest_asyncio.fixture
async def archive_env() -> AsyncIterator[Path]:
    """Isolated, file-backed temp database *and* a throwaway documents
    directory, for the duration of one test. Everything under test
    (import_archive/remove_archive/validate, all via app.db.session_scope)
    is repointed here."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    docs_dir = Path(tempfile.mkdtemp(prefix="archive-docs-"))

    os.environ["DATABASE_PATH"] = db_path
    os.environ["DOCUMENTS_DIR"] = str(docs_dir)
    get_settings.cache_clear()
    db_module._engine = None
    db_module._session_factory = None

    await db_module.create_all()
    try:
        yield docs_dir
    finally:
        await db_module.dispose_engine()
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("DOCUMENTS_DIR", None)
        get_settings.cache_clear()
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(db_path + suffix)
            if candidate.exists():
                candidate.unlink()
        shutil.rmtree(docs_dir, ignore_errors=True)


LABEL = "test-archive-batch"


async def _expected_counts() -> dict[str, int]:
    dataset = build_dataset(label=LABEL)
    return {
        "properties": len(dataset.properties),
        "tenants": len(dataset.tenants),
        "contractors": len(dataset.contractors),
        "cases": len(dataset.cases),
        "issues": len(dataset.cases),
        "work_orders": sum(len(c.work_orders) for c in dataset.cases),
        "appointments": sum(len(c.appointments) for c in dataset.cases),
        "action_records": sum(len(c.appointments) for c in dataset.cases),
        "costs": sum(len(c.costs) for c in dataset.cases),
        "notes": sum(len(c.notes) for c in dataset.cases),
        "messages": sum(len(c.messages) for c in dataset.cases),
        "documents": sum(1 for c in dataset.cases if c.document is not None),
    }


@pytest.mark.asyncio
async def test_import_writes_expected_counts(archive_env: Path) -> None:
    expected = await _expected_counts()
    result = await import_archive(db_module.session_scope, label=LABEL)

    assert result.skipped is False
    assert result.counts == expected
    assert len(result.documents_written) == expected["documents"]
    for path_str in result.documents_written:
        assert Path(path_str).exists()
        assert Path(path_str).parent == archive_env

    # Cross-check against the DB directly, not just the reported counts.
    async with db_module.session_scope() as session:
        batch = (
            await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == LABEL))
        ).scalar_one()

        def count_query(model, condition):
            return sa.select(sa.func.count()).select_from(model).where(condition)

        properties = (
            await session.execute(count_query(PropertyModel, PropertyModel.archive_batch_id == batch.id))
        ).scalar_one()
        cases = (
            await session.execute(count_query(RepairCaseModel, RepairCaseModel.archive_batch_id == batch.id))
        ).scalar_one()
        contractors = (
            await session.execute(count_query(ContractorModel, ContractorModel.archive_batch_id == batch.id))
        ).scalar_one()
        tenants = (
            await session.execute(count_query(TenantModel, TenantModel.archive_batch_id == batch.id))
        ).scalar_one()

        assert properties == expected["properties"]
        assert cases == expected["cases"]
        assert contractors == expected["contractors"]
        assert tenants == expected["tenants"]


@pytest.mark.asyncio
async def test_second_import_is_noop(archive_env: Path) -> None:
    first = await import_archive(db_module.session_scope, label=LABEL)
    assert first.skipped is False

    second = await import_archive(db_module.session_scope, label=LABEL)
    assert second.skipped is True
    assert sum(second.counts.values()) == 0

    async with db_module.session_scope() as session:
        batch_count = (
            await session.execute(sa.select(sa.func.count()).select_from(ArchiveBatchModel))
        ).scalar_one()
        case_count = (
            await session.execute(sa.select(sa.func.count()).select_from(RepairCaseModel))
        ).scalar_one()

    assert batch_count == 1
    assert case_count == first.counts["cases"]
    assert case_count > 0


@pytest.mark.asyncio
async def test_validate_passes_every_check(archive_env: Path) -> None:
    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        report = await validate(session, label=LABEL)

    failing = [(c.name, c.detail) for c in report.checks if not c.passed]
    assert not failing, f"validation checks failed: {failing}"
    assert report.passed is True
    check_names = {c.name for c in report.checks}
    assert {
        "referential_integrity",
        "timestamps_ordered_and_past",
        "nonnegative_durations_and_costs",
        "no_open_or_pending_work",
        "no_jobs",
        "no_future_appointments",
        "no_unread_messages",
        "tenants_and_contractors_tagged",
        "archival_contacts_not_dialable",
        "recurrence_grouping",
        "cost_totals_reconcile",
        "quoted_totals_reconcile_with_work_orders",
        "import_is_idempotent",
    } <= check_names


@pytest.mark.asyncio
async def test_quoted_totals_reconcile_with_work_orders_per_case(archive_env: Path) -> None:
    """The archival instance of docs/audit/06 Finding 1 / docs/audit/11
    Finding 3: before app/archive/dataset.py ledgered every work order (not
    just work_orders[0]), ~48% of resolved archival cases had
    sum(WorkOrderModel.quote_pence, non-cancelled) != sum(CostEntryModel,
    kind=QUOTE) for the same case, by up to 3.4x. Proves, against a real
    import (not a hand-built fixture), that every case now reconciles
    exactly, including cases with 2 or 3 work orders -- the exact shape the
    pre-fix bug needed to reproduce.
    """
    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        batch = (
            await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == LABEL))
        ).scalar_one()
        cases = (
            await session.execute(sa.select(RepairCaseModel).where(RepairCaseModel.archive_batch_id == batch.id))
        ).scalars().all()
        case_ids = [c.id for c in cases]
        work_orders = (
            await session.execute(sa.select(WorkOrderModel).where(WorkOrderModel.case_id.in_(case_ids)))
        ).scalars().all()
        costs = (
            await session.execute(sa.select(CostEntryModel).where(CostEntryModel.archive_batch_id == batch.id))
        ).scalars().all()

    # Mirrors app.analytics.reconciled_quotes: a QUOTE entry tied to a
    # CANCELLED work order (the cancelled-case generator logs one, "work
    # never carried out") is not "quoted" money either, same as the work
    # order's own quote_pence isn't -- both sides of the comparison must
    # exclude it, not just the WorkOrderModel side.
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

    assert wo_quote_by_case == cost_quote_by_case

    # Not vacuous: at least one case has 2+ non-cancelled work orders, the
    # exact shape that used to disagree (work_orders[1]/[2] had no ledger
    # row at all).
    multi_wo_cases = {
        case_id for case_id in wo_quote_by_case
        if sum(1 for wo in work_orders if wo.case_id == case_id and wo.status != WorkOrderStatus.CANCELLED) >= 2
    }
    assert multi_wo_cases, "expected at least one case with 2+ work orders in the generated dataset"


async def _insert_control_rows(session) -> dict[str, str]:
    """A minimal non-archival property/tenant/contractor/case -- every one
    with `archive_batch_id=None` -- inserted *before* the archive import, to
    prove removal only ever touches batch-tagged rows and never a bare
    delete that happens to also match a real row."""
    property_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    contractor_id = str(uuid.uuid4())
    case_id = str(uuid.uuid4())

    session.add(
        PropertyModel(
            id=property_id, address_line="1 Real Street, Bristol", postcode="BS1 1AA",
            landlord_reference="REAL-LL-001", roof_responsibility=RoofResponsibility.LANDLORD,
            build_year=2000, property_type="House", bedrooms=3, photo_key=None, archive_batch_id=None,
        )
    )
    session.add(
        TenantModel(
            id=tenant_id, property_id=property_id, display_name="Real Tenant", phone_e164="+441234567890",
            email="real@example.com", preferred_channel="VOICE", contact_allowed=True,
            accessibility_notes=None, archive_batch_id=None,
        )
    )
    session.add(
        ContractorModel(
            id=contractor_id, display_name="Real Contractor Co", trades=["ROOFING"],
            service_postcodes=["BS1"], approval_status=ContractorApprovalStatus.APPROVED,
            connector=ConnectorType.MOCK, contact_reference="mock:real-contractor",
            verification_note=None, provenance=Provenance.SIMULATED, workers=[], archive_batch_id=None,
        )
    )
    await session.flush()
    session.add(
        RepairCaseModel(
            id=case_id, case_number=1, property_id=property_id, tenant_id=tenant_id,
            status=CaseStatus.ACTIVE, version=1, title="A real, current ticket", risk={},
            archive_batch_id=None,
        )
    )
    await session.flush()
    return {"property_id": property_id, "tenant_id": tenant_id, "contractor_id": contractor_id, "case_id": case_id}


@pytest.mark.asyncio
async def test_removal_leaves_zero_batch_rows_and_no_orphans(archive_env: Path) -> None:
    async with db_module.session_scope() as session:
        control_ids = await _insert_control_rows(session)

    dataset = build_dataset(label=LABEL)
    result = await import_archive(db_module.session_scope, label=LABEL)
    assert result.skipped is False
    written_paths = [Path(p) for p in result.documents_written]
    assert written_paths and all(p.exists() for p in written_paths)

    removal = await remove_archive(LABEL)
    assert removal.found is True
    assert removal.counts["cases"] == result.counts["cases"]
    assert removal.counts["properties"] == result.counts["properties"]
    assert removal.counts["contractors"] == result.counts["contractors"]
    assert removal.counts["tenants"] == result.counts["tenants"]
    assert removal.counts["archive_batches"] == 1

    # Document files are actually gone from disk, not just the DB row.
    for p in written_paths:
        assert not p.exists()

    async with db_module.session_scope() as session:
        fk_rows = (await session.execute(sa.text("PRAGMA foreign_key_check"))).fetchall()
        assert fk_rows == []

        # Zero rows carry the removed batch id, in every one of the eight
        # tables that have an archive_batch_id column.
        for model in (
            PropertyModel, RepairCaseModel, TenantModel, ContractorModel,
            CostEntryModel, NoteModel, DocumentModel, MessageModel,
        ):
            tagged = (
                await session.execute(
                    sa.select(sa.func.count()).select_from(model).where(model.archive_batch_id.isnot(None))
                )
            ).scalar_one()
            assert tagged == 0, f"{model.__tablename__} still has a batch-tagged row after removal"

        # And the four traversal-only tables (no archive_batch_id column at
        # all) are fully empty too, since every row in them belonged to an
        # archival case.
        for model in (RepairIssueModel, WorkOrderModel, AppointmentModel, ActionRecordModel):
            count = (await session.execute(sa.select(sa.func.count()).select_from(model))).scalar_one()
            assert count == 0, f"{model.__tablename__} still has {count} row(s) after removal"

        assert (await session.execute(sa.select(sa.func.count()).select_from(ArchiveBatchModel))).scalar_one() == 0

        # The control rows -- never tagged with this batch -- are untouched.
        assert await session.get(PropertyModel, control_ids["property_id"]) is not None
        assert await session.get(TenantModel, control_ids["tenant_id"]) is not None
        assert await session.get(ContractorModel, control_ids["contractor_id"]) is not None
        control_case = await session.get(RepairCaseModel, control_ids["case_id"])
        assert control_case is not None
        assert control_case.status == CaseStatus.ACTIVE

    # Removing a second time is a clean no-op, not an error.
    second_removal = await remove_archive(LABEL)
    assert second_removal.found is False


@pytest.mark.asyncio
async def test_no_job_rows_after_import(archive_env: Path) -> None:
    await import_archive(db_module.session_scope, label=LABEL)
    async with db_module.session_scope() as session:
        job_count = (await session.execute(sa.select(sa.func.count()).select_from(JobModel))).scalar_one()
    assert job_count == 0


@pytest.mark.asyncio
async def test_evidence_refs_are_schema_valid_and_marked_illustrative(archive_env: Path) -> None:
    """RepairIssue.evidence_refs is `list[EvidenceRef]`, and EvidenceRef is a
    StrictModel (extra="forbid"). Confirm the archive's evidence dicts
    survive that strict validation, and that their `locator` carries the
    "not captured evidence" marker (paired with provenance=FIXTURE, the
    schema's existing signal for a non-real record)."""
    await import_archive(db_module.session_scope, label=LABEL)

    async with db_module.session_scope() as session:
        rows = (
            await session.execute(
                sa.select(RepairIssueModel).where(sa.func.json_array_length(RepairIssueModel.evidence_refs) > 0)
            )
        ).scalars().all()

    assert rows, "expected at least one archival issue with evidence_refs"
    for row in rows:
        parsed = RepairIssue.model_validate(row)  # raises on any extra/invalid key
        assert parsed.evidence_refs
        for ref in parsed.evidence_refs:
            assert ref.locator is not None and ref.locator.startswith("illustrative-sample:")
            assert ref.provenance.value == "FIXTURE"


@pytest.mark.asyncio
async def test_default_label_matches_module_default(archive_env: Path) -> None:
    result = await import_archive(db_module.session_scope)
    assert result.skipped is False
    async with db_module.session_scope() as session:
        batch = (
            await session.execute(sa.select(ArchiveBatchModel).where(ArchiveBatchModel.label == DEFAULT_LABEL))
        ).scalar_one_or_none()
    assert batch is not None
