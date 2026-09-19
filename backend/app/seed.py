"""Synthetic reference data for the hero demo: properties, tenants, approved
fictional roofers and a scaffolder. Does not create a case — the case is
created through intake (docs/04: "create case from browser voice or
labelled captured intake"), so the initial state never contains the
scaffold branch.

Seeding is idempotent per row (checked individually, not "bail if the demo
property exists") so this can be re-run safely against a database that
already has real, in-progress demo data on it -- adding a new property here
must not require wiping anything. Existing rows are left untouched; only
rows that don't yet exist are inserted.

Run with: python -m app.seed
"""
from __future__ import annotations

import asyncio
import uuid

from app.db import create_all, session_scope
from app.models import ContractorModel, PropertyModel, TenantModel
from app.schemas import ConnectorType, ContractorApprovalStatus, Provenance, RoofResponsibility, Trade

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "repairflow.demo")


def _demo_id(label: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, label))


# --- Original hero-path fixtures --------------------------------------------
# Do not change these values: they're baked into already-recorded LIVE call
# evidence from real ElevenLabs testing. Only add alongside, never edit.
DEMO_PROPERTY_ID = _demo_id("property:14-elm-court")
DEMO_TENANT_ID = _demo_id("tenant:jordan-hale")
DEMO_ROOFER_ID = _demo_id("contractor:apex-roofing")
DEMO_ROOFER_2_ID = _demo_id("contractor:bristol-roof-and-gutter")
DEMO_ROOFER_3_ID = _demo_id("contractor:summit-heights-roofing")
DEMO_SCAFFOLDER_ID = _demo_id("contractor:steadfast-scaffold")

# --- Additional properties/tenants (portfolio breadth for the maintenance
# dashboard -- distinct addresses so tickets don't all land on one property).
DEMO_PROPERTY_2_ID = _demo_id("property:27-cathedral-walk")
DEMO_TENANT_2_ID = _demo_id("tenant:priya-desai")
DEMO_PROPERTY_3_ID = _demo_id("property:58-gloucester-road")
DEMO_TENANT_3_ID = _demo_id("tenant:tomasz-nowak")
DEMO_PROPERTY_4_ID = _demo_id("property:9-redcliffe-parade")
DEMO_TENANT_4_ID = _demo_id("tenant:aaliyah-bennett")


PROPERTIES: list[dict] = [
    dict(
        id=DEMO_PROPERTY_ID,
        address_line="14 Elm Court, Bristol",
        postcode="BS1 4ND",
        timezone="Europe/London",
        landlord_reference="LL-2201",
        roof_responsibility=RoofResponsibility.LANDLORD,
        access_notes="Terraced house; roof accessed from rear garden only.",
        # Fictional-but-plausible construction year for this demo persona
        # (CLAUDE.md's honesty boundary is about not touching a
        # LIVE-provenance case/communication, not about leaving fictional
        # property metadata null forever -- a build year on a fictional
        # address is exactly the kind of invented detail seed data exists
        # for). Applied via the update-if-null pass below for rows that
        # already exist from a prior seed run.
        build_year=1961,
    ),
    dict(
        id=DEMO_PROPERTY_2_ID,
        address_line="27 Cathedral Walk, Bristol",
        postcode="BS8 1JX",
        timezone="Europe/London",
        landlord_reference="LL-2202",
        roof_responsibility=RoofResponsibility.LANDLORD,
        access_notes="Flat 3B, top floor; roof access via communal stairwell, managing agent holds the key.",
        build_year=2005,
    ),
    dict(
        id=DEMO_PROPERTY_3_ID,
        address_line="58 Gloucester Road, Bristol",
        postcode="BS7 8BT",
        timezone="Europe/London",
        landlord_reference="LL-2203",
        roof_responsibility=RoofResponsibility.OTHER,
        access_notes="Mid-terrace; loft hatch access only, no external ladder point.",
        build_year=1978,
    ),
    dict(
        id=DEMO_PROPERTY_4_ID,
        address_line="9 Redcliffe Parade, Bristol",
        postcode="BS1 6SP",
        timezone="Europe/London",
        landlord_reference="LL-2204",
        roof_responsibility=RoofResponsibility.UNKNOWN,
        access_notes="Ground-floor flat; shared roof, access managed by the freeholder.",
        build_year=1967,
    ),
]

TENANTS: list[dict] = [
    dict(
        id=DEMO_TENANT_ID,
        property_id=DEMO_PROPERTY_ID,
        display_name="Jordan Hale",
        phone_e164="+441179460000",
        preferred_channel="VOICE",
        contact_allowed=True,
        accessibility_notes=None,
    ),
    dict(
        id=DEMO_TENANT_2_ID,
        property_id=DEMO_PROPERTY_2_ID,
        display_name="Priya Desai",
        phone_e164="+441179460011",
        preferred_channel="VOICE",
        contact_allowed=True,
        accessibility_notes=None,
    ),
    dict(
        id=DEMO_TENANT_3_ID,
        property_id=DEMO_PROPERTY_3_ID,
        display_name="Tomasz Nowak",
        phone_e164="+441179460022",
        preferred_channel="VOICE",
        contact_allowed=True,
        accessibility_notes=None,
    ),
    dict(
        id=DEMO_TENANT_4_ID,
        property_id=DEMO_PROPERTY_4_ID,
        display_name="Aaliyah Bennett",
        phone_e164="+441179460033",
        preferred_channel="VOICE",
        contact_allowed=True,
        accessibility_notes=None,
    ),
]

CONTRACTORS: list[dict] = [
    dict(
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
    ),
    dict(
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
    ),
    dict(
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
    ),
    dict(
        id=DEMO_SCAFFOLDER_ID,
        display_name="Steadfast Scaffold Co (fictional, SIMULATED)",
        trades=[Trade.SCAFFOLDING.value],
        service_postcodes=["BS1", "BS2", "BS3"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:steadfast-scaffold",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[],
    ),
]


async def seed() -> None:
    await create_all()
    added_properties = added_tenants = added_contractors = 0
    updated_properties = 0
    async with session_scope() as session:
        for row in PROPERTIES:
            existing_property = await session.get(PropertyModel, row["id"])
            if existing_property is None:
                session.add(PropertyModel(**row))
                added_properties += 1
            elif existing_property.build_year is None and row.get("build_year") is not None:
                # Backfill for a property inserted by an earlier seed run,
                # before build_year existed/was populated here. Never
                # overwrites a build_year that's already set.
                existing_property.build_year = row["build_year"]
                updated_properties += 1
        for row in TENANTS:
            if await session.get(TenantModel, row["id"]) is None:
                session.add(TenantModel(**row))
                added_tenants += 1
        for row in CONTRACTORS:
            if await session.get(ContractorModel, row["id"]) is None:
                session.add(ContractorModel(**row))
                added_contractors += 1
    print(
        f"Seed complete: {added_properties} propert(y/ies), {added_tenants} tenant(s), "
        f"{added_contractors} contractor(s) newly added, {updated_properties} propert(y/ies) "
        f"backfilled with build_year "
        f"({len(PROPERTIES)} properties / {len(TENANTS)} tenants / {len(CONTRACTORS)} contractors total)."
    )


if __name__ == "__main__":
    asyncio.run(seed())
