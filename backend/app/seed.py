"""Synthetic reference data for the hero demo: property, tenant, approved
fictional roofer and scaffolder. Does not create a case — the case is
created through intake (docs/04: "create case from browser voice or
labelled captured intake"), so the initial state never contains the
scaffold branch.

Run with: python -m app.seed
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.db import create_all, session_scope
from app.models import ContractorModel, PropertyModel, TenantModel
from app.schemas import ConnectorType, ContractorApprovalStatus, Provenance, RoofResponsibility, Trade

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "repairflow.demo")


def _demo_id(label: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, label))


DEMO_PROPERTY_ID = _demo_id("property:14-elm-court")
DEMO_TENANT_ID = _demo_id("tenant:jordan-hale")
DEMO_ROOFER_ID = _demo_id("contractor:apex-roofing")
DEMO_ROOFER_2_ID = _demo_id("contractor:bristol-roof-and-gutter")
DEMO_ROOFER_3_ID = _demo_id("contractor:summit-heights-roofing")
DEMO_SCAFFOLDER_ID = _demo_id("contractor:steadfast-scaffold")


async def seed() -> None:
    await create_all()
    async with session_scope() as session:
        existing = await session.execute(select(PropertyModel).where(PropertyModel.id == DEMO_PROPERTY_ID))
        if existing.scalar_one_or_none() is not None:
            print("Seed data already present; skipping.")
            return

        session.add(
            PropertyModel(
                id=DEMO_PROPERTY_ID,
                address_line="14 Elm Court, Bristol",
                postcode="BS1 4ND",
                timezone="Europe/London",
                landlord_reference="LL-2201",
                roof_responsibility=RoofResponsibility.LANDLORD,
                access_notes="Terraced house; roof accessed from rear garden only.",
            )
        )
        session.add(
            TenantModel(
                id=DEMO_TENANT_ID,
                property_id=DEMO_PROPERTY_ID,
                display_name="Jordan Hale",
                phone_e164="+441179460000",
                preferred_channel="VOICE",
                contact_allowed=True,
                accessibility_notes=None,
            )
        )
        session.add(
            ContractorModel(
                id=DEMO_ROOFER_ID,
                display_name="Apex Roofing (fictional, SIMULATED)",
                trades=[Trade.ROOFING.value],
                service_postcodes=["BS1", "BS2", "BS3"],
                approval_status=ContractorApprovalStatus.APPROVED,
                connector=ConnectorType.MOCK,
                contact_reference="mock:apex-roofing",
                verification_note="Seeded demo fixture; not a real company.",
                provenance=Provenance.SIMULATED,
                workers=[
                    {"name": "Dave Okafor", "role": "Site lead, height-access certified"},
                    {"name": "Priya Chandra", "role": "Roofer"},
                ],
            )
        )
        session.add(
            ContractorModel(
                id=DEMO_ROOFER_2_ID,
                display_name="Bristol Roof & Gutter (fictional, SIMULATED)",
                trades=[Trade.ROOFING.value],
                service_postcodes=["BS1", "BS2"],
                approval_status=ContractorApprovalStatus.APPROVED,
                connector=ConnectorType.MOCK,
                contact_reference="mock:bristol-roof-and-gutter",
                verification_note="Seeded demo fixture; not a real company.",
                provenance=Provenance.SIMULATED,
                workers=[{"name": "Marcus Webb", "role": "Roofer"}],
            )
        )
        session.add(
            ContractorModel(
                id=DEMO_ROOFER_3_ID,
                display_name="Summit Heights Roofing (fictional, SIMULATED)",
                trades=[Trade.ROOFING.value],
                service_postcodes=["BS3", "BS4"],
                approval_status=ContractorApprovalStatus.APPROVED,
                connector=ConnectorType.MOCK,
                contact_reference="mock:summit-heights-roofing",
                verification_note="Seeded demo fixture; not a real company. Specialises in steep-pitch and chimney-adjacent work.",
                provenance=Provenance.SIMULATED,
                workers=[{"name": "Aisha Rahman", "role": "Site lead, steep-pitch specialist"}],
            )
        )
        session.add(
            ContractorModel(
                id=DEMO_SCAFFOLDER_ID,
                display_name="Steadfast Scaffold Co (fictional, SIMULATED)",
                trades=[Trade.SCAFFOLDING.value],
                service_postcodes=["BS1", "BS2", "BS3"],
                approval_status=ContractorApprovalStatus.APPROVED,
                connector=ConnectorType.MOCK,
                contact_reference="mock:steadfast-scaffold",
                verification_note="Seeded demo fixture; not a real company.",
                provenance=Provenance.SIMULATED,
            )
        )
    print("Seeded property, tenant and four approved fictional contractors (three roofers, one scaffolder).")


if __name__ == "__main__":
    asyncio.run(seed())
