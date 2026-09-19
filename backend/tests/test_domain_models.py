from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError

from app.models import (
    ActionRecordModel,
    CaseEventModel,
    PropertyModel,
    RepairCaseModel,
    RepairIssueModel,
    TenantModel,
    WorkOrderModel,
)
from app.schemas import CaseStatus, RoofResponsibility, Trade, WorkOrderKind, WorkOrderStatus


async def _seed_property_tenant(session, new_id):
    property_id = new_id()
    tenant_id = new_id()
    session.add(
        PropertyModel(
            id=property_id,
            address_line="1 Test St",
            postcode="BS1 1AA",
            landlord_reference="LL-1",
            roof_responsibility=RoofResponsibility.LANDLORD,
        )
    )
    session.add(
        TenantModel(
            id=tenant_id,
            property_id=property_id,
            display_name="Test Tenant",
            preferred_channel="VOICE",
            contact_allowed=True,
        )
    )
    await session.flush()
    return property_id, tenant_id


async def test_create_and_reload_case(db_session, new_id):
    property_id, tenant_id = await _seed_property_tenant(db_session, new_id)
    case_id = new_id()
    db_session.add(
        RepairCaseModel(
            id=case_id,
            property_id=property_id,
            tenant_id=tenant_id,
            status=CaseStatus.ACTIVE,
            version=1,
            title="Roof ingress",
            risk={},
        )
    )
    db_session.add(
        RepairIssueModel(
            id=new_id(),
            case_id=case_id,
            description="Water coming through ceiling",
            location="Rear bedroom",
        )
    )
    await db_session.commit()

    reloaded = (
        await db_session.execute(select(RepairCaseModel).where(RepairCaseModel.id == case_id))
    ).scalar_one()
    assert reloaded.status == CaseStatus.ACTIVE
    assert reloaded.version == 1
    assert reloaded.title == "Roof ingress"


async def test_work_order_rejects_unknown_case_fk(db_session, new_id):
    db_session.add(
        WorkOrderModel(
            id=new_id(),
            case_id=new_id(),  # no such case
            issue_id=new_id(),
            kind=WorkOrderKind.REPAIR,
            trade=Trade.ROOFING,
            scope="Repair roof",
            status=WorkOrderStatus.READY,
            required_for_resolution=True,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_duplicate_source_event_key_rejected(db_session, new_id):
    property_id, tenant_id = await _seed_property_tenant(db_session, new_id)
    case_id = new_id()
    db_session.add(
        RepairCaseModel(
            id=case_id, property_id=property_id, tenant_id=tenant_id,
            status=CaseStatus.ACTIVE, version=1, title="Case", risk={},
        )
    )
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add(
        CaseEventModel(
            id=new_id(), case_id=case_id, seq=1, type="CASE_CREATED",
            occurred_at=now, received_at=now, actor_type="SYSTEM", actor_id="intake",
            source_event_key="intake:abc", correlation_id="corr-1", payload={},
        )
    )
    await db_session.commit()

    db_session.add(
        CaseEventModel(
            id=new_id(), case_id=case_id, seq=2, type="CASE_CREATED",
            occurred_at=now, received_at=now, actor_type="SYSTEM", actor_id="intake",
            source_event_key="intake:abc", correlation_id="corr-2", payload={},
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_duplicate_idempotency_key_rejected(db_session, new_id):
    property_id, tenant_id = await _seed_property_tenant(db_session, new_id)
    case_id = new_id()
    db_session.add(
        RepairCaseModel(
            id=case_id, property_id=property_id, tenant_id=tenant_id,
            status=CaseStatus.ACTIVE, version=1, title="Case", risk={},
        )
    )
    await db_session.flush()

    def make_action():
        return ActionRecordModel(
            id=new_id(), case_id=case_id, kind="WAIT", idempotency_key="wait:fixed-key",
            payload_hash="h", proposal={}, state="PROPOSED",
        )

    db_session.add(make_action())
    await db_session.commit()

    db_session.add(make_action())
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_naive_datetime_rejected(db_session, new_id):
    property_id, tenant_id = await _seed_property_tenant(db_session, new_id)
    case_id = new_id()
    db_session.add(
        RepairCaseModel(
            id=case_id, property_id=property_id, tenant_id=tenant_id,
            status=CaseStatus.ACTIVE, version=1, title="Case", risk={},
            created_at=datetime(2026, 1, 1),  # naive: no tzinfo
        )
    )
    with pytest.raises((ValueError, StatementError)):
        await db_session.commit()
