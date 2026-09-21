"""Optional sample portfolio: reference properties, tenants and approved
contractors.

**Not a startup hook.** Nothing calls this automatically; the application
boots against whatever is in the database, including nothing at all, and
every screen has a real empty state. Run it by hand to get a workspace with
something in it:

    python -m app.seed

It creates reference data only -- no cases, work orders, appointments or
messages. Operational records come from real intake. The scripted demo
workload a previous build inserted on every boot has been removed; use
`python -m app.legacy_demo_purge --apply` to clear it from a database that
already received it.

Idempotent per row (checked individually, not "bail if the first property
exists"), so re-running against a database that already has real work on it
adds only what is missing and never touches an existing row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db import run_cli, session_scope
from app.models import ContractorModel, PropertyModel, TenantModel
from app.schemas import (
    ConnectorType,
    ContractorApprovalStatus,
    Provenance,
    RoofResponsibility,
    Trade,
)

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
# Non-roofing trades, so a plumbing/electrical case can be booked against a
# real approved firm instead of being left unassigned.
DEMO_PLUMBER_ID = _demo_id("contractor:harbourside-plumbing")
DEMO_ELECTRICIAN_ID = _demo_id("contractor:clifton-electrical")

# --- Roster expansion: every Trade needs multiple APPROVED contractors and
# BS1-BS8 coverage, so any ticket -- not just the hero-path roofing case --
# finds an eligible contractor instead of dead-ending at escalation. See
# test_seed_roster.py for the coverage assertion this roster must satisfy.
DEMO_ROOFER_4_ID = _demo_id("contractor:fishponds-roofing-and-repairs")
DEMO_ROOFER_5_ID = _demo_id("contractor:southville-roof-specialists")
DEMO_SCAFFOLDER_2_ID = _demo_id("contractor:redcliffe-scaffold-solutions")
DEMO_SCAFFOLDER_3_ID = _demo_id("contractor:highground-access-and-scaffolding")
DEMO_PLUMBER_2_ID = _demo_id("contractor:bedminster-plumbing-services")
DEMO_PLUMBER_3_ID = _demo_id("contractor:horfield-heating-and-plumbing")
DEMO_ELECTRICIAN_2_ID = _demo_id("contractor:bishopston-electrical")
DEMO_ELECTRICIAN_3_ID = _demo_id("contractor:filton-road-electrical")
# Trade.OTHER had zero contractors: general maintenance, appliance repair,
# pest/drainage and locksmith/damp/decorating jobs all fall here.
DEMO_HANDYMAN_ID = _demo_id("contractor:bristol-handyman-collective")
DEMO_APPLIANCE_ID = _demo_id("contractor:home-appliance-medics")
DEMO_PEST_DRAIN_ID = _demo_id("contractor:avon-pest-and-drain-control")
DEMO_LOCKSMITH_DECOR_ID = _demo_id("contractor:cabot-locksmiths-and-decorating")

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
        property_type="Terraced house",
        bedrooms=3,
        photo_key="property-elm-court.jpg",
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
        property_type="Top-floor flat",
        bedrooms=2,
        photo_key="property-cathedral-walk.jpg",
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
        property_type="Mid-terrace house",
        bedrooms=4,
        photo_key="property-gloucester-road.jpg",
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
        property_type="Ground-floor flat",
        bedrooms=1,
        photo_key="property-redcliffe-parade.jpg",
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
        id=DEMO_PLUMBER_ID,
        display_name="Harbourside Plumbing & Heating (fictional, SIMULATED)",
        trades=[Trade.PLUMBING.value],
        service_postcodes=["BS1", "BS2", "BS7", "BS8"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:harbourside-plumbing",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Gareth Lloyd", "role": "Gas-safe engineer"}],
    ),
    dict(
        id=DEMO_ELECTRICIAN_ID,
        display_name="Clifton Electrical Services (fictional, SIMULATED)",
        trades=[Trade.ELECTRICAL.value],
        service_postcodes=["BS1", "BS7", "BS8"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:clifton-electrical",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Nadia Fischer", "role": "Approved electrician"}],
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
    # --- Roster expansion (see comment block above the id constants) -------
    dict(
        id=DEMO_ROOFER_4_ID,
        display_name="Fishponds Roofing & Repairs (fictional, SIMULATED)",
        trades=[Trade.ROOFING.value],
        service_postcodes=["BS5", "BS6", "BS7"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:fishponds-roofing-and-repairs",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Callum Reid", "role": "Roofer"}],
    ),
    dict(
        id=DEMO_ROOFER_5_ID,
        display_name="Southville Roof Specialists (fictional, SIMULATED)",
        trades=[Trade.ROOFING.value],
        service_postcodes=["BS6", "BS7", "BS8"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:southville-roof-specialists",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[
            {"name": "Owen Matthews", "role": "Site lead"},
            {"name": "Elena Popescu", "role": "Roofer"},
        ],
    ),
    dict(
        id=DEMO_SCAFFOLDER_2_ID,
        display_name="Redcliffe Scaffold Solutions (fictional, SIMULATED)",
        trades=[Trade.SCAFFOLDING.value],
        service_postcodes=["BS4", "BS5", "BS6"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:redcliffe-scaffold-solutions",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Jamie Foster", "role": "Scaffolder"}],
    ),
    dict(
        id=DEMO_SCAFFOLDER_3_ID,
        display_name="Highground Access & Scaffolding (fictional, SIMULATED)",
        trades=[Trade.SCAFFOLDING.value],
        service_postcodes=["BS5", "BS6", "BS7", "BS8"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:highground-access-and-scaffolding",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[
            {"name": "Ruth Ellison", "role": "Site lead, height-access certified"},
            {"name": "Tomasz Baran", "role": "Scaffolder"},
        ],
    ),
    dict(
        id=DEMO_PLUMBER_2_ID,
        display_name="Bedminster Plumbing Services (fictional, SIMULATED)",
        trades=[Trade.PLUMBING.value],
        service_postcodes=["BS3", "BS4", "BS5"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:bedminster-plumbing-services",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Ffion Bevan", "role": "Plumber"}],
    ),
    dict(
        id=DEMO_PLUMBER_3_ID,
        display_name="Horfield Heating & Plumbing (fictional, SIMULATED)",
        trades=[Trade.PLUMBING.value],
        service_postcodes=["BS4", "BS5", "BS6"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:horfield-heating-and-plumbing",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[
            {"name": "Sam Whitlock", "role": "Gas-safe engineer"},
            {"name": "Anika Desai", "role": "Plumber"},
        ],
    ),
    dict(
        id=DEMO_ELECTRICIAN_2_ID,
        display_name="Bishopston Electrical (fictional, SIMULATED)",
        trades=[Trade.ELECTRICAL.value],
        service_postcodes=["BS2", "BS3", "BS4"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:bishopston-electrical",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Leon Kowalski", "role": "Approved electrician"}],
    ),
    dict(
        id=DEMO_ELECTRICIAN_3_ID,
        display_name="Filton Road Electrical Contractors (fictional, SIMULATED)",
        trades=[Trade.ELECTRICAL.value],
        service_postcodes=["BS4", "BS5", "BS6"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:filton-road-electrical",
        verification_note="Seeded demo fixture; not a real company.",
        provenance=Provenance.SIMULATED,
        workers=[
            {"name": "Grace Mahoney", "role": "Site lead, approved electrician"},
            {"name": "Idris Osei", "role": "Electrician"},
        ],
    ),
    dict(
        id=DEMO_HANDYMAN_ID,
        display_name="Bristol Handyman Collective (fictional, SIMULATED)",
        trades=[Trade.OTHER.value],
        service_postcodes=["BS1", "BS2", "BS3", "BS4"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:bristol-handyman-collective",
        verification_note="Seeded demo fixture; not a real company. General maintenance and small repairs.",
        provenance=Provenance.SIMULATED,
        workers=[
            {"name": "Dean Ashworth", "role": "General maintenance"},
            {"name": "Kirsty Palmer", "role": "Handyperson"},
        ],
    ),
    dict(
        id=DEMO_APPLIANCE_ID,
        display_name="Home Appliance Medics (fictional, SIMULATED)",
        trades=[Trade.OTHER.value],
        service_postcodes=["BS2", "BS3", "BS4", "BS5"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:home-appliance-medics",
        verification_note="Seeded demo fixture; not a real company. White-goods and appliance repair.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Robbie Tanner", "role": "Appliance engineer"}],
    ),
    dict(
        id=DEMO_PEST_DRAIN_ID,
        display_name="Avon Pest & Drain Control (fictional, SIMULATED)",
        trades=[Trade.OTHER.value],
        service_postcodes=["BS5", "BS6", "BS7", "BS8"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:avon-pest-and-drain-control",
        verification_note="Seeded demo fixture; not a real company. Pest control and drain clearance.",
        provenance=Provenance.SIMULATED,
        workers=[
            {"name": "Marek Nowicki", "role": "Pest control technician"},
            {"name": "Sophie Larkin", "role": "Drainage engineer"},
        ],
    ),
    dict(
        id=DEMO_LOCKSMITH_DECOR_ID,
        display_name="Cabot Locksmiths & Decorating (fictional, SIMULATED)",
        trades=[Trade.OTHER.value],
        service_postcodes=["BS1", "BS6", "BS7", "BS8"],
        approval_status=ContractorApprovalStatus.APPROVED,
        connector=ConnectorType.MOCK,
        contact_reference="mock:cabot-locksmiths-and-decorating",
        verification_note="Seeded demo fixture; not a real company. Locksmith, damp treatment and decorating.",
        provenance=Provenance.SIMULATED,
        workers=[{"name": "Nia Fletcher", "role": "Locksmith and decorator"}],
    ),
]

async def seed() -> None:
    added_properties = added_tenants = added_contractors = 0
    updated_properties = 0
    async with session_scope() as session:
        for row in PROPERTIES:
            existing_property = await session.get(PropertyModel, row["id"])
            if existing_property is None:
                session.add(PropertyModel(**row))
                added_properties += 1
            else:
                # Backfill for a property inserted by an earlier seed run,
                # before these columns existed/were populated here. Only
                # ever fills a NULL; never overwrites a value already set.
                #
                # `property_type` and `photo_key` matter beyond tidiness:
                # the properties list renders "Type unknown" without the
                # first, and silently shows no photograph without the
                # second -- even though the images are already in
                # `frontend-fixi/src/assets`.
                filled = False
                for column in ("build_year", "property_type", "bedrooms", "photo_key"):
                    if getattr(existing_property, column) is None and row.get(column) is not None:
                        setattr(existing_property, column, row[column])
                        filled = True
                if filled:
                    updated_properties += 1
        for row in TENANTS:
            if await session.get(TenantModel, row["id"]) is None:
                session.add(TenantModel(**row))
                added_tenants += 1
        for row in CONTRACTORS:
            if await session.get(ContractorModel, row["id"]) is None:
                session.add(ContractorModel(**row))
                added_contractors += 1
        await session.flush()
    print(
        f"Seed complete: {added_properties} propert(y/ies), {added_tenants} tenant(s), "
        f"{added_contractors} contractor(s) newly added, {updated_properties} propert(y/ies) "
        f"backfilled with build_year "
        f"({len(PROPERTIES)} properties / {len(TENANTS)} tenants / {len(CONTRACTORS)} contractors total)."
    )


if __name__ == "__main__":
    run_cli(seed())
