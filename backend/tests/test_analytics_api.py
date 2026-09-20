"""Tests for app/analytics.py and its four routers (overview, insights,
reports, search) -- style from tests/test_api.py: real ASGI requests, plus
direct calls into app.analytics for the pure/arithmetic pieces that don't
need HTTP at all. main.py does not wire these routers yet (that is the
root-migration agent's job -- see
backend/app/api/NEEDS_FROM_ROOT_analytics.md), so a small local FastAPI app
mounts just these four routers, with the same error-handler wiring as
app.main, for the ASGI-level tests.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import analytics
from app.api import costs as costs_api
from app.api import insights, overview, reports, search
from app.api.errors import register_error_handlers
from app.db import session_scope
from app.models import (
    ArchiveBatchModel,
    CaseEventModel,
    CostEntryModel,
    PropertyModel,
    RepairCaseModel,
    RepairIssueModel,
    TenantModel,
    WorkOrderModel,
)
from app.schemas import CaseStatus, CostKind, Trade, WorkOrderKind, WorkOrderStatus

AUTH = ("operator", "repairflow-demo")


def uid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(overview.router)
    app.include_router(insights.router)
    app.include_router(reports.router)
    app.include_router(search.router)
    register_error_handlers(app)
    return app


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test")


async def _seed_property_tenant(session, *, address="1 Test St", postcode="BS1 1AA", archive_batch_id=None):
    property_id, tenant_id = uid(), uid()
    session.add(
        PropertyModel(
            id=property_id, address_line=address, postcode=postcode, landlord_reference="LL-1",
            roof_responsibility="LANDLORD", archive_batch_id=archive_batch_id,
        )
    )
    session.add(
        TenantModel(
            id=tenant_id, property_id=property_id, display_name="Jordan Hale", email="jordan@example.com",
            preferred_channel="VOICE", contact_allowed=True,
        )
    )
    await session.flush()
    return property_id, tenant_id


_case_counter = 0


def _next_case_number() -> int:
    global _case_counter
    _case_counter += 1
    return _case_counter


def _make_case(
    *, property_id, tenant_id, status=CaseStatus.ACTIVE, category=None, created_at=None, updated_at=None,
    archive_batch_id=None, archived_closed_at=None, next_follow_up_at=None, escalation_reason=None,
    title="Water ingress",
) -> RepairCaseModel:
    now = created_at or utcnow()
    return RepairCaseModel(
        id=uid(), case_number=_next_case_number(), property_id=property_id, tenant_id=tenant_id, status=status,
        version=1, title=title, risk={}, created_at=now, updated_at=updated_at or now, category=category,
        archive_batch_id=archive_batch_id, archived_closed_at=archived_closed_at,
        next_follow_up_at=next_follow_up_at, escalation_reason=escalation_reason,
    )


# --------------------------------------------------------------------------
# Pure functions: no DB needed
# --------------------------------------------------------------------------


def test_case_status_predicates():
    assert analytics.case_is_open(CaseStatus.ACTIVE) is True
    assert analytics.case_is_open(CaseStatus.AWAITING_CONFIRMATION) is True
    assert analytics.case_is_open(CaseStatus.ESCALATED) is True
    assert analytics.case_is_open(CaseStatus.RESOLVED) is False
    assert analytics.case_is_open(CaseStatus.CANCELLED) is False

    assert analytics.case_is_resolved(CaseStatus.RESOLVED) is True
    assert analytics.case_is_resolved(CaseStatus.CANCELLED) is False
    assert analytics.case_is_resolved(CaseStatus.ACTIVE) is False

    assert analytics.case_is_waiting(CaseStatus.AWAITING_CONFIRMATION) is True
    assert analytics.case_is_waiting(CaseStatus.ESCALATED) is False
    assert analytics.case_is_waiting(CaseStatus.ACTIVE) is False


def test_period_comparison_zero_baseline():
    # previous == 0, current == 0 -> a real, honest 0%, not "new".
    both_zero = analytics.period_comparison(0, 0)
    assert both_zero.change_pct == 0.0
    assert both_zero.is_new is False

    # previous == 0, current > 0 -> None + is_new, never a fake "inf%".
    from_zero = analytics.period_comparison(7, 0)
    assert from_zero.change_pct is None
    assert from_zero.is_new is True

    # ordinary cases.
    up = analytics.period_comparison(15, 10)
    assert up.change_pct == 50.0
    assert up.is_new is False

    down = analytics.period_comparison(5, 10)
    assert down.change_pct == -50.0


def test_largest_remainder_percentages_thirds_sum_to_100():
    # 3 categories at 1/3 each -- naive independent rounding gives
    # 33%+33%+33% = 99% or, with a different rounding rule, overshoots;
    # the largest-remainder method must land on exactly 100.
    percentages = analytics._largest_remainder_percentages([1, 1, 1])
    assert sum(percentages) == 100
    assert sorted(percentages) == [33, 33, 34]


def test_largest_remainder_percentages_51_5_48_5_split_sums_to_100():
    # 103/200 = 51.5%, 97/200 = 48.5% -- the exact "52% + 49% = 101%" bug
    # shape being replaced. Hand-computed: floors [51, 48], one remainder
    # point to distribute, tied at .5 each -> first index wins (stable).
    percentages = analytics._largest_remainder_percentages([103, 97])
    assert percentages == [52, 48]
    assert sum(percentages) == 100


def test_largest_remainder_percentages_zero_total():
    assert analytics._largest_remainder_percentages([0, 0]) == [0, 0]


def test_resolution_hours_pure_negative_duration_excluded():
    created = datetime(2026, 1, 10, tzinfo=timezone.utc)
    bad_close = datetime(2026, 1, 9, tzinfo=timezone.utc)  # before created_at
    inputs = analytics.ResolutionInputs(
        case_id="x", created_at=created, archive_batch_id="batch", archived_closed_at=bad_close,
        terminal_event_at=None, updated_at=created,
    )
    assert analytics.resolution_hours(inputs) is None


def test_resolution_hours_pure_archival_and_real_case():
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closed = datetime(2026, 1, 3, tzinfo=timezone.utc)  # +48h
    archival = analytics.ResolutionInputs(
        case_id="a", created_at=created, archive_batch_id="batch", archived_closed_at=closed,
        terminal_event_at=None, updated_at=created,
    )
    assert analytics.resolution_hours(archival) == 48.0

    real = analytics.ResolutionInputs(
        case_id="b", created_at=created, archive_batch_id=None, archived_closed_at=None,
        terminal_event_at=closed, updated_at=created,
    )
    assert analytics.resolution_hours(real) == 48.0

    # No terminal event -> falls back to updated_at.
    fallback = analytics.ResolutionInputs(
        case_id="c", created_at=created, archive_batch_id=None, archived_closed_at=None,
        terminal_event_at=None, updated_at=closed,
    )
    assert analytics.resolution_hours(fallback) == 48.0


# --------------------------------------------------------------------------
# DB-backed analytics.py functions
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_category_breakdown_sums_to_100(app_db):
    async with session_scope() as session:
        property_id, tenant_id = await _seed_property_tenant(session)
        for trade in (Trade.ELECTRICAL, Trade.PLUMBING, Trade.ROOFING):
            session.add(_make_case(property_id=property_id, tenant_id=tenant_id, category=trade))

    async with session_scope() as session:
        breakdown = await analytics.category_breakdown(session, include_archived=True)

    assert sum(c.percentage for c in breakdown) == 100
    by_category = {c.category: c.percentage for c in breakdown}
    # Deterministic tie-break (alphabetical among equal counts): ELECTRICAL
    # sorts first, so it absorbs the one leftover remainder point.
    assert by_category[Trade.ELECTRICAL] == 34
    assert by_category[Trade.PLUMBING] == 33
    assert by_category[Trade.ROOFING] == 33


@pytest.mark.asyncio
async def test_spend_by_year_pence_totals(app_db):
    async with session_scope() as session:
        property_id, tenant_id = await _seed_property_tenant(session)
        case = _make_case(property_id=property_id, tenant_id=tenant_id, category=Trade.ROOFING)
        session.add(case)
        await session.flush()

        session.add_all([
            CostEntryModel(
                id=uid(), case_id=case.id, kind=CostKind.QUOTE, amount_pence=10_000,
                description="Quote", incurred_at=datetime(2024, 3, 1, tzinfo=timezone.utc), recorded_by="operator",
            ),
            CostEntryModel(
                id=uid(), case_id=case.id, kind=CostKind.INVOICE, amount_pence=9_500,
                description="Invoice", incurred_at=datetime(2024, 6, 1, tzinfo=timezone.utc), recorded_by="operator",
            ),
            CostEntryModel(
                id=uid(), case_id=case.id, kind=CostKind.ADJUSTMENT, amount_pence=-500,
                description="Credit note", incurred_at=datetime(2024, 6, 15, tzinfo=timezone.utc), recorded_by="operator",
            ),
            CostEntryModel(
                id=uid(), case_id=case.id, kind=CostKind.QUOTE, amount_pence=20_000,
                description="Quote 2025", incurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc), recorded_by="operator",
            ),
        ])

    async with session_scope() as session:
        by_year = await analytics.spend_by_year(session, include_archived=True)

    totals = {y.year: y for y in by_year}
    assert totals[2024].quoted_pence == 10_000
    assert totals[2024].actual_pence == 9_500 - 500  # INVOICE + ADJUSTMENT
    assert totals[2025].quoted_pence == 20_000
    assert totals[2025].actual_pence == 0


@pytest.mark.asyncio
async def test_recurring_issues_returns_contributing_case_ids(app_db):
    async with session_scope() as session:
        property_id, tenant_id = await _seed_property_tenant(session)
        roof_1 = _make_case(property_id=property_id, tenant_id=tenant_id, category=Trade.ROOFING)
        roof_2 = _make_case(property_id=property_id, tenant_id=tenant_id, category=Trade.ROOFING)
        plumbing = _make_case(property_id=property_id, tenant_id=tenant_id, category=Trade.PLUMBING)
        session.add_all([roof_1, roof_2, plumbing])
        await session.flush()
        roof_ids = {roof_1.id, roof_2.id}

    async with session_scope() as session:
        groups = await analytics.recurring_issues(session, include_archived=True)

    assert len(groups) == 1
    group = groups[0]
    assert group.category == Trade.ROOFING
    assert group.count == 2
    assert set(group.case_ids) == roof_ids


@pytest.mark.asyncio
async def test_archival_excluded_operational_included_historical(app_db):
    batch_id = uid()
    async with session_scope() as session:
        session.add(
            ArchiveBatchModel(id=batch_id, label="test-batch", generator_version="1", random_seed=1)
        )
        property_id, tenant_id = await _seed_property_tenant(session)

        real_case = _make_case(property_id=property_id, tenant_id=tenant_id, status=CaseStatus.ACTIVE, category=Trade.ROOFING)
        archival_case = _make_case(
            property_id=property_id, tenant_id=tenant_id, status=CaseStatus.RESOLVED, category=Trade.ROOFING,
            archive_batch_id=batch_id, archived_closed_at=utcnow(),
        )
        session.add_all([real_case, archival_case])

    async with session_scope() as session:
        # Operational: archival row excluded unconditionally -- may
        # honestly be zero for resolved/etc, never padded.
        status_counts = await analytics.operational_status_counts(session)
        assert status_counts.total == 1
        assert status_counts.active == 1
        assert status_counts.resolved == 0

        # Historical, opted out: same as operational.
        excluded = await analytics.category_breakdown(session, include_archived=False)
        assert sum(c.count for c in excluded) == 1

        # Historical, opted in: both rows counted, flagged via
        # archived_case_count.
        included = await analytics.category_breakdown(session, include_archived=True)
        assert sum(c.count for c in included) == 2

        count = await analytics.archived_case_count(session)
        assert count == 1


@pytest.mark.asyncio
async def test_resolution_time_distribution_skips_negative_duration(app_db):
    batch_id = uid()
    async with session_scope() as session:
        session.add(ArchiveBatchModel(id=batch_id, label="bad-batch", generator_version="1", random_seed=1))
        property_id, tenant_id = await _seed_property_tenant(session)
        created = datetime(2026, 1, 10, tzinfo=timezone.utc)
        bad_close = datetime(2026, 1, 9, tzinfo=timezone.utc)
        session.add(
            _make_case(
                property_id=property_id, tenant_id=tenant_id, status=CaseStatus.RESOLVED, category=Trade.ROOFING,
                archive_batch_id=batch_id, archived_closed_at=bad_close, created_at=created,
            )
        )

    async with session_scope() as session:
        distribution = await analytics.resolution_time_distribution(session, include_archived=True)

    assert distribution.sample_count == 0
    assert distribution.skipped_count == 1
    assert distribution.average_hours is None
    assert distribution.median_hours is None


@pytest.mark.asyncio
async def test_resolution_time_distribution_real_case_via_terminal_event(app_db):
    async with session_scope() as session:
        property_id, tenant_id = await _seed_property_tenant(session)
        created = datetime(2026, 2, 1, tzinfo=timezone.utc)
        case = _make_case(
            property_id=property_id, tenant_id=tenant_id, status=CaseStatus.RESOLVED, category=Trade.PLUMBING,
            created_at=created, updated_at=created,
        )
        session.add(case)
        await session.flush()
        resolved_at = created + timedelta(hours=30)
        session.add(
            CaseEventModel(
                id=uid(), case_id=case.id, seq=1, type="CASE_RESOLVED", occurred_at=resolved_at,
                received_at=resolved_at, actor_type="OPERATOR", actor_id="operator", source_event_key=f"k:{case.id}",
                correlation_id="c1",
            )
        )

    async with session_scope() as session:
        distribution = await analytics.resolution_time_distribution(session, include_archived=False)

    assert distribution.sample_count == 1
    assert distribution.skipped_count == 0
    assert distribution.average_hours == 30.0
    assert distribution.median_hours == 30.0
    assert distribution.buckets[1] == ("1-3 days", 1)  # 24h <= 30h < 72h


# --------------------------------------------------------------------------
# Endpoint-level: reconciliation between /reports/summary and
# /reports/export.csv, and /search's minimum-length behaviour.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_csv_export_totals_match_reports_summary(app_db):
    async with session_scope() as session:
        property_id, tenant_id = await _seed_property_tenant(session)
        case_a = _make_case(property_id=property_id, tenant_id=tenant_id, status=CaseStatus.RESOLVED, category=Trade.ROOFING)
        case_b = _make_case(property_id=property_id, tenant_id=tenant_id, status=CaseStatus.ACTIVE, category=Trade.PLUMBING)
        session.add_all([case_a, case_b])
        await session.flush()
        now = utcnow()
        session.add(
            CaseEventModel(
                id=uid(), case_id=case_a.id, seq=1, type="CASE_RESOLVED", occurred_at=now, received_at=now,
                actor_type="OPERATOR", actor_id="operator", source_event_key=f"k:{case_a.id}", correlation_id="c1",
            )
        )
        session.add_all([
            CostEntryModel(
                id=uid(), case_id=case_a.id, kind=CostKind.QUOTE, amount_pence=15_000, description="q",
                incurred_at=now, recorded_by="operator",
            ),
            CostEntryModel(
                id=uid(), case_id=case_a.id, kind=CostKind.INVOICE, amount_pence=14_000, description="i",
                incurred_at=now, recorded_by="operator",
            ),
            CostEntryModel(
                id=uid(), case_id=case_b.id, kind=CostKind.QUOTE, amount_pence=5_000, description="q2",
                incurred_at=now, recorded_by="operator",
            ),
        ])

    async with await _client() as client:
        summary_resp = await client.get("/api/v1/reports/summary", auth=AUTH)
        assert summary_resp.status_code == 200, summary_resp.text
        summary = summary_resp.json()

        csv_resp = await client.get("/api/v1/reports/export.csv", auth=AUTH)
        assert csv_resp.status_code == 200, csv_resp.text
        assert csv_resp.headers["content-type"].startswith("text/csv")

    reader = csv.DictReader(io.StringIO(csv_resp.text))
    csv_rows = list(reader)

    assert len(csv_rows) == len(summary["rows"]) == summary["maintenance"]["total_cases"] == 2

    csv_quoted_total = sum(int(r["quoted_pence"]) for r in csv_rows)
    csv_invoiced_total = sum(int(r["invoiced_pence"]) for r in csv_rows)
    assert csv_quoted_total == summary["spend"]["quoted_pence"] == 20_000
    assert csv_invoiced_total == summary["spend"]["actual_pence"] == 14_000

    record_sources = {r["record_source"] for r in csv_rows}
    assert record_sources == {"operational"}


@pytest.mark.asyncio
async def test_csv_export_archival_rows_flagged_and_reconcile(app_db):
    batch_id = uid()
    async with session_scope() as session:
        session.add(ArchiveBatchModel(id=batch_id, label="flag-batch", generator_version="1", random_seed=1))
        property_id, tenant_id = await _seed_property_tenant(session, archive_batch_id=batch_id)
        archival_case = _make_case(
            property_id=property_id, tenant_id=tenant_id, status=CaseStatus.RESOLVED, category=Trade.ROOFING,
            archive_batch_id=batch_id, archived_closed_at=utcnow(),
        )
        session.add(archival_case)

    async with await _client() as client:
        summary_resp = await client.get("/api/v1/reports/summary", params={"include_archived": "true"}, auth=AUTH)
        assert summary_resp.status_code == 200, summary_resp.text
        summary = summary_resp.json()
        csv_resp = await client.get("/api/v1/reports/export.csv", params={"include_archived": "true"}, auth=AUTH)

    assert summary["includes_archived_history"] is True
    assert summary["archived_case_count"] == 1

    reader = csv.DictReader(io.StringIO(csv_resp.text))
    csv_rows = list(reader)
    assert len(csv_rows) == len(summary["rows"]) == 1
    assert csv_rows[0]["record_source"] == "archival-sample"


@pytest.mark.asyncio
async def test_search_minimum_query_length(app_db):
    async with session_scope() as session:
        property_id, tenant_id = await _seed_property_tenant(session, address="42 Willow Court")
        session.add(_make_case(property_id=property_id, tenant_id=tenant_id, title="Willow leak"))

    async with await _client() as client:
        too_short = await client.get("/api/v1/search", params={"q": "w"}, auth=AUTH)
        assert too_short.status_code == 200
        assert too_short.json()["groups"] == []

        matched = await client.get("/api/v1/search", params={"q": "Willow"}, auth=AUTH)
        assert matched.status_code == 200
        groups_by_type = {g["type"]: g for g in matched.json()["groups"]}
        assert any(item["label"] == "42 Willow Court" for item in groups_by_type["property"]["items"])
        assert any("Willow" in item["label"] for item in groups_by_type["case"]["items"])


@pytest.mark.asyncio
async def test_overview_operational_scope_excludes_archival(app_db):
    batch_id = uid()
    async with session_scope() as session:
        session.add(ArchiveBatchModel(id=batch_id, label="ov-batch", generator_version="1", random_seed=1))
        property_id, tenant_id = await _seed_property_tenant(session, archive_batch_id=batch_id)
        session.add(
            _make_case(
                property_id=property_id, tenant_id=tenant_id, status=CaseStatus.RESOLVED,
                archive_batch_id=batch_id, archived_closed_at=utcnow(),
            )
        )

    async with await _client() as client:
        resp = await client.get("/api/v1/overview", auth=AUTH)
        assert resp.status_code == 200, resp.text
        body = resp.json()

    # The only case and property in this DB are archival -- operational
    # scope must show zero, not a padded number.
    assert body["status_counts"]["total"] == 0
    assert body["property_count"] == 0


@pytest.mark.asyncio
async def test_insights_case_volume_comparison_new_when_previous_window_empty(app_db):
    async with session_scope() as session:
        property_id, tenant_id = await _seed_property_tenant(session)
        session.add(_make_case(property_id=property_id, tenant_id=tenant_id, category=Trade.ROOFING))

    async with await _client() as client:
        resp = await client.get(
            "/api/v1/insights",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            auth=AUTH,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

    comparison = body["case_volume_comparison"]
    assert comparison["previous"] == 0
    if comparison["current"] > 0:
        assert comparison["is_new"] is True
        assert comparison["change_pct"] is None
    else:
        assert comparison["change_pct"] == 0.0


# --------------------------------------------------------------------------
# Quoted-money reconciliation (docs/audit/06 Finding 1, docs/audit/11
# Finding 3, docs/26 2026-09-20): WorkOrderModel.quote_pence and
# CostEntryModel(kind=QUOTE) used to be two unreconciled sources for the
# same figure. app.analytics.reconciled_quotes is now the one place that
# decides which wins, and every screen below is proved to agree.
# --------------------------------------------------------------------------


def _make_work_order(
    *, case_id, issue_id, trade=Trade.ROOFING, status=WorkOrderStatus.COMPLETED, quote_pence,
) -> WorkOrderModel:
    return WorkOrderModel(
        id=uid(), case_id=case_id, issue_id=issue_id, kind=WorkOrderKind.REPAIR, trade=trade,
        scope="Repair work", status=status, quote_pence=quote_pence,
    )


async def _costs_client() -> AsyncClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(costs_api.router)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_quoted_money_reconciles_across_screens_with_no_cost_entries(app_db):
    """The exact scenario docs/audit/06 Finding 1 measured: a case with
    work orders but zero logged cost entries used to show a real total on
    Property Stats/History and 0p on Insights/Reports/CSV and the Costs
    tab. Two non-cancelled work orders, 12,345p + 6,789p = 19,134p, no
    CostEntryModel rows at all -- proves the chart (property_stats), the
    detail table (property_history_items), the row (case_detail_rows), the
    year total (spend_by_year) and the Costs tab total all agree on
    19,134p for the same case/scope.
    """
    async with session_scope() as session:
        property_id, tenant_id = await _seed_property_tenant(session)
        case = _make_case(
            property_id=property_id, tenant_id=tenant_id, category=Trade.ROOFING, status=CaseStatus.RESOLVED,
        )
        session.add(case)
        await session.flush()
        issue_id = uid()
        session.add(RepairIssueModel(id=issue_id, case_id=case.id, description="Roof leak", location="Loft"))
        await session.flush()
        session.add_all([
            _make_work_order(case_id=case.id, issue_id=issue_id, quote_pence=12_345),
            _make_work_order(case_id=case.id, issue_id=issue_id, quote_pence=6_789),
        ])
        case_id = case.id

    EXPECTED = 19_134

    async with session_scope() as session:
        stats = await analytics.property_stats(session, property_id, build_year=None)
        history = await analytics.property_history_items(session, property_id)
        rows = await analytics.case_detail_rows(session, include_archived=True)
        spend = await analytics.spend_by_year(session, include_archived=True)

    assert sum(t.quoted_pence for t in stats.quoted_by_trade) == EXPECTED
    assert sum(y.quoted_pence for y in stats.quoted_by_year) == EXPECTED

    # PropertyHistoryItem.case_id is a pydantic UUID field, not a plain
    # str, so compare via str() rather than == against the raw id.
    [history_row] = [i for i in history if str(i.case_id) == case_id]
    assert history_row.quoted_pence == EXPECTED

    [detail_row] = [r for r in rows if r.case_id == case_id]
    assert detail_row.quoted_pence == EXPECTED

    assert sum(y.quoted_pence for y in spend) == EXPECTED

    async with await _costs_client() as client:
        resp = await client.get(f"/api/v1/cases/{case_id}/costs", auth=AUTH)
        assert resp.status_code == 200, resp.text
        body = resp.json()

    assert body["items"] == []  # zero real ledger rows -- this is the fallback path
    assert body["totals"]["quoted_pence"] == EXPECTED
    assert body["totals"]["committed_pence"] == EXPECTED


@pytest.mark.asyncio
async def test_quoted_money_cost_entry_supersedes_quote_pence_no_double_count(app_db):
    """Once a QUOTE CostEntryModel row exists for a work order, it wins
    over that work order's own quote_pence -- never both summed (CLAUDE.md:
    no double counting). 50,000p on the work order, a 35,471p ledger
    entry: the reconciled figure is 35,471p everywhere, not 85,471p and
    not 50,000p.
    """
    async with session_scope() as session:
        property_id, tenant_id = await _seed_property_tenant(session)
        case = _make_case(property_id=property_id, tenant_id=tenant_id, category=Trade.ELECTRICAL)
        session.add(case)
        await session.flush()
        issue_id = uid()
        session.add(RepairIssueModel(id=issue_id, case_id=case.id, description="Socket", location="Kitchen"))
        await session.flush()
        wo = _make_work_order(case_id=case.id, issue_id=issue_id, trade=Trade.ELECTRICAL, quote_pence=50_000)
        session.add(wo)
        await session.flush()
        session.add(
            CostEntryModel(
                id=uid(), case_id=case.id, work_order_id=wo.id, kind=CostKind.QUOTE, amount_pence=35_471,
                description="Revised quote after survey", incurred_at=utcnow(), recorded_by="operator",
            )
        )
        case_id = case.id

    async with session_scope() as session:
        contributions = await analytics.reconciled_quotes(session, [case_id])
        rows = await analytics.case_detail_rows(session, include_archived=True)

    assert [c.quoted_pence for c in contributions] == [35_471]
    assert contributions[0].from_cost_entry is True

    [detail_row] = [r for r in rows if r.case_id == case_id]
    assert detail_row.quoted_pence == 35_471

    async with await _costs_client() as client:
        resp = await client.get(f"/api/v1/cases/{case_id}/costs", auth=AUTH)
        body = resp.json()
    assert body["totals"]["quoted_pence"] == 35_471


@pytest.mark.asyncio
async def test_reconciled_quotes_excludes_cancelled_work_order(app_db):
    """A CANCELLED work order's quote is money that will never be spent --
    it must not contribute even when it has no cost entry to be
    "superseded" by (matches services._pick_primary_trade's identical
    exclusion rule, applied here for the money side)."""
    async with session_scope() as session:
        property_id, tenant_id = await _seed_property_tenant(session)
        case = _make_case(property_id=property_id, tenant_id=tenant_id, category=Trade.SCAFFOLDING)
        session.add(case)
        await session.flush()
        issue_id = uid()
        session.add(RepairIssueModel(id=issue_id, case_id=case.id, description="Access", location="Rear"))
        await session.flush()
        session.add(
            _make_work_order(
                case_id=case.id, issue_id=issue_id, trade=Trade.SCAFFOLDING,
                status=WorkOrderStatus.CANCELLED, quote_pence=4_444,
            )
        )
        case_id = case.id

    async with session_scope() as session:
        contributions = await analytics.reconciled_quotes(session, [case_id])

    assert contributions == []
