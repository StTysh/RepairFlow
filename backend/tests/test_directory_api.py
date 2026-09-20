"""HTTP tests for the property/contractor/tenant directory API
(app/api/properties.py, app/api/contractors.py, app/api/tenants.py),
exercised through the real ASGI client exactly as tests/test_api.py does.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main_module
from app.db import session_scope
from app.models import ArchiveBatchModel, PropertyModel, RepairCaseModel, TenantModel

AUTH = ("operator", "repairflow-demo")


def uid() -> str:
    return str(uuid.uuid4())


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=main_module.app), base_url="http://test")


async def _seed_property_and_tenant() -> tuple[str, str]:
    property_id, tenant_id = uid(), uid()
    async with session_scope() as session:
        session.add(
            PropertyModel(
                id=property_id, address_line="1 Test St", postcode="BS1 1AA",
                landlord_reference="LL-1", roof_responsibility="LANDLORD",
            )
        )
        session.add(
            TenantModel(
                id=tenant_id, property_id=property_id, display_name="Jordan Hale",
                preferred_channel="VOICE", contact_allowed=True,
            )
        )
    return property_id, tenant_id


async def _seed_archival_property_and_tenant() -> tuple[str, str, str]:
    batch_id, property_id, tenant_id = uid(), uid(), uid()
    async with session_scope() as session:
        session.add(
            ArchiveBatchModel(id=batch_id, label=f"batch-{batch_id[:8]}", generator_version="1", random_seed=1)
        )
        session.add(
            PropertyModel(
                id=property_id, address_line="9 Archive Ave", postcode="BS9 9ZZ",
                landlord_reference="LL-ARCH", roof_responsibility="LANDLORD", archive_batch_id=batch_id,
            )
        )
        session.add(
            TenantModel(
                id=tenant_id, property_id=property_id, display_name="Archived Tenant",
                preferred_channel="VOICE", contact_allowed=True,
            )
        )
    return batch_id, property_id, tenant_id


# --------------------------------------------------------------------------
# properties
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_property_list_create_get_patch_happy_path(app_db):
    async with await _client() as client:
        r = await client.post(
            "/api/v1/properties",
            json={
                "address_line": "42 Oak Avenue", "postcode": "bs1 1aa", "landlord_reference": "LL-42",
                "bedrooms": 3, "build_year": 1990, "property_type": "terrace",
            },
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["postcode"] == "BS1 1AA"
        assert created["is_archived"] is False
        assert created["open_case_count"] == 0 and created["total_case_count"] == 0 and created["tenant_count"] == 0
        property_id = created["id"]

        r = await client.get("/api/v1/properties", params={"q": "Oak Avenue"}, auth=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert any(item["id"] == property_id for item in body["items"])
        assert body["limit"] == 25 and body["offset"] == 0

        r = await client.get(f"/api/v1/properties/{property_id}", auth=AUTH)
        assert r.status_code == 200
        assert r.json()["tenants"] == []

        r = await client.patch(f"/api/v1/properties/{property_id}", json={"bedrooms": 4, "access_notes": "Key under mat"}, auth=AUTH)
        assert r.status_code == 200, r.text
        assert r.json()["bedrooms"] == 4
        assert r.json()["access_notes"] == "Key under mat"
        # untouched fields survive a partial PATCH
        assert r.json()["address_line"] == "42 Oak Avenue"


@pytest.mark.asyncio
async def test_property_validation_rejections(app_db):
    async with await _client() as client:
        r = await client.post(
            "/api/v1/properties",
            json={"address_line": "1 Bad St", "postcode": "NOTAPOSTCODE", "landlord_reference": "LL-1"},
            auth=AUTH,
        )
        assert r.status_code == 422

        r = await client.post(
            "/api/v1/properties",
            json={"address_line": "  ", "postcode": "BS1 1AA", "landlord_reference": "LL-1"},
            auth=AUTH,
        )
        assert r.status_code == 422

        r = await client.post(
            "/api/v1/properties",
            json={"address_line": "1 St", "postcode": "BS1 1AA", "landlord_reference": "LL-1", "bedrooms": -1},
            auth=AUTH,
        )
        assert r.status_code == 422

        r = await client.post(
            "/api/v1/properties",
            json={"address_line": "1 St", "postcode": "BS1 1AA", "landlord_reference": "LL-1", "build_year": 500},
            auth=AUTH,
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_property_not_found(app_db):
    async with await _client() as client:
        r = await client.get(f"/api/v1/properties/{uid()}", auth=AUTH)
        assert r.status_code == 404
        r = await client.patch(f"/api/v1/properties/{uid()}", json={"bedrooms": 2}, auth=AUTH)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_archival_properties_excluded_by_default_and_refuse_patch(app_db):
    _batch_id, property_id, _tenant_id = await _seed_archival_property_and_tenant()

    async with await _client() as client:
        r = await client.get("/api/v1/properties", auth=AUTH)
        assert r.status_code == 200
        assert all(item["id"] != property_id for item in r.json()["items"])

        r = await client.get("/api/v1/properties", params={"include_archived": "true"}, auth=AUTH)
        assert r.status_code == 200
        item = next(i for i in r.json()["items"] if i["id"] == property_id)
        assert item["is_archived"] is True

        # get-by-id still works and reports is_archived honestly
        r = await client.get(f"/api/v1/properties/{property_id}", auth=AUTH)
        assert r.status_code == 200
        assert r.json()["is_archived"] is True

        # but PATCH is refused
        r = await client.patch(f"/api/v1/properties/{property_id}", json={"bedrooms": 1}, auth=AUTH)
        assert r.status_code == 409, r.text


# --------------------------------------------------------------------------
# contractors
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contractor_list_create_get_patch_happy_path(app_db):
    async with await _client() as client:
        r = await client.post(
            "/api/v1/contractors",
            json={"display_name": "Apex Roofing", "trades": ["ROOFING"], "service_postcodes": ["BS1"]},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["approval_status"] == "PENDING"
        assert created["is_archived"] is False
        contractor_id = created["id"]

        r = await client.get("/api/v1/contractors", params={"trade": "ROOFING", "q": "Apex"}, auth=AUTH)
        assert r.status_code == 200
        assert any(i["id"] == contractor_id for i in r.json()["items"])

        r = await client.get("/api/v1/contractors", params={"trade": "PLUMBING"}, auth=AUTH)
        assert r.status_code == 200
        assert all(i["id"] != contractor_id for i in r.json()["items"])

        r = await client.get(f"/api/v1/contractors/{contractor_id}", auth=AUTH)
        assert r.status_code == 200
        assert r.json()["work_history"] == []
        assert r.json()["appointment_count"] == 0

        # approving without a verification note is refused
        r = await client.patch(f"/api/v1/contractors/{contractor_id}", json={"approval_status": "APPROVED"}, auth=AUTH)
        assert r.status_code == 409, r.text

        # approving with a verification note in the same request succeeds
        r = await client.patch(
            f"/api/v1/contractors/{contractor_id}",
            json={"approval_status": "APPROVED", "verification_note": "Checked insurance and Gas Safe ID."},
            auth=AUTH,
        )
        assert r.status_code == 200, r.text
        assert r.json()["approval_status"] == "APPROVED"

        # a later edit that doesn't touch approval_status keeps the record approved
        r = await client.patch(f"/api/v1/contractors/{contractor_id}", json={"contact_reference": "07700 900123"}, auth=AUTH)
        assert r.status_code == 200
        assert r.json()["approval_status"] == "APPROVED"


@pytest.mark.asyncio
async def test_contractor_validation_rejections(app_db):
    async with await _client() as client:
        r = await client.post("/api/v1/contractors", json={"display_name": "No Trades Ltd", "trades": []}, auth=AUTH)
        assert r.status_code == 422

        r = await client.post("/api/v1/contractors", json={"display_name": "Bad Trade Ltd", "trades": ["SPACE_REPAIR"]}, auth=AUTH)
        assert r.status_code == 422

        # POST cannot set approval_status at all -- extra="forbid" rejects it outright
        r = await client.post(
            "/api/v1/contractors",
            json={"display_name": "Sneaky Ltd", "trades": ["ROOFING"], "approval_status": "APPROVED"},
            auth=AUTH,
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_contractor_not_found(app_db):
    async with await _client() as client:
        r = await client.get(f"/api/v1/contractors/{uid()}", auth=AUTH)
        assert r.status_code == 404
        r = await client.patch(f"/api/v1/contractors/{uid()}", json={"display_name": "X"}, auth=AUTH)
        assert r.status_code == 404


# --------------------------------------------------------------------------
# tenants
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_list_create_get_patch_happy_path(app_db):
    property_id, _existing_tenant_id = await _seed_property_and_tenant()

    async with await _client() as client:
        r = await client.post(
            "/api/v1/tenants",
            json={"property_id": property_id, "display_name": "Sam Rivers", "email": "sam@example.com"},
            auth=AUTH,
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["property_address"] == "1 Test St"
        assert created["is_archived"] is False
        tenant_id = created["id"]

        r = await client.get("/api/v1/tenants", params={"q": "Sam", "property_id": property_id}, auth=AUTH)
        assert r.status_code == 200
        assert any(i["id"] == tenant_id for i in r.json()["items"])

        r = await client.get(f"/api/v1/tenants/{tenant_id}", auth=AUTH)
        assert r.status_code == 200
        assert r.json()["property"]["id"] == property_id
        assert r.json()["cases"] == []

        r = await client.patch(f"/api/v1/tenants/{tenant_id}", json={"accessibility_notes": "Uses a wheelchair"}, auth=AUTH)
        assert r.status_code == 200, r.text
        assert r.json()["accessibility_notes"] == "Uses a wheelchair"
        assert r.json()["display_name"] == "Sam Rivers"


@pytest.mark.asyncio
async def test_tenant_validation_rejections(app_db):
    property_id, _tenant_id = await _seed_property_and_tenant()
    async with await _client() as client:
        r = await client.post(
            "/api/v1/tenants",
            json={"property_id": property_id, "display_name": "Bad Phone", "phone_e164": "07700900123"},
            auth=AUTH,
        )
        assert r.status_code == 422

        r = await client.post(
            "/api/v1/tenants", json={"property_id": uid(), "display_name": "No Property"}, auth=AUTH,
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_tenant_not_found(app_db):
    async with await _client() as client:
        r = await client.get(f"/api/v1/tenants/{uid()}", auth=AUTH)
        assert r.status_code == 404
        r = await client.patch(f"/api/v1/tenants/{uid()}", json={"display_name": "X"}, auth=AUTH)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_tenant_patch_unknown_property_id_404(app_db):
    _property_id, tenant_id = await _seed_property_and_tenant()
    async with await _client() as client:
        r = await client.patch(f"/api/v1/tenants/{tenant_id}", json={"property_id": uid()}, auth=AUTH)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_archival_tenants_excluded_by_default_and_refuse_patch(app_db):
    _batch_id, _property_id, tenant_id = await _seed_archival_property_and_tenant()

    async with await _client() as client:
        r = await client.get("/api/v1/tenants", auth=AUTH)
        assert r.status_code == 200
        assert all(item["id"] != tenant_id for item in r.json()["items"])

        r = await client.get("/api/v1/tenants", params={"include_archived": "true"}, auth=AUTH)
        assert r.status_code == 200
        item = next(i for i in r.json()["items"] if i["id"] == tenant_id)
        assert item["is_archived"] is True

        r = await client.get(f"/api/v1/tenants/{tenant_id}", auth=AUTH)
        assert r.status_code == 200
        assert r.json()["is_archived"] is True

        r = await client.patch(f"/api/v1/tenants/{tenant_id}", json={"display_name": "New Name"}, auth=AUTH)
        assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_tenant_open_and_total_case_counts(app_db):
    property_id, tenant_id = await _seed_property_and_tenant()
    async with session_scope() as session:
        session.add(
            RepairCaseModel(
                id=uid(), case_number=9001, property_id=property_id, tenant_id=tenant_id,
                status="ACTIVE", version=1, title="Leaking tap",
            )
        )
        session.add(
            RepairCaseModel(
                id=uid(), case_number=9002, property_id=property_id, tenant_id=tenant_id,
                status="RESOLVED", version=1, title="Broken window (resolved)",
            )
        )

    async with await _client() as client:
        r = await client.get(f"/api/v1/tenants/{tenant_id}", auth=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["open_case_count"] == 1
        assert body["total_case_count"] == 2
        assert len(body["cases"]) == 2
