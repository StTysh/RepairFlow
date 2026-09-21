"""Coverage guarantee for the reference contractor roster in app/seed.py.

The owner's demo goal is: create ANY repair ticket and have the system find
an appropriate APPROVED contractor rather than dead-ending at escalation.
Eligibility at execution time (app/orchestration/executor.py) only checks
`approval_status == APPROVED`; trade/area matching is left to the model's
judgement reading `trades` and `service_postcodes`. That judgement can only
ever succeed if the roster actually contains an eligible row -- so this test
pins the roster's coverage directly, independent of any model behaviour.

Asserts, after `seed()`:
  * every `Trade` value has at least one APPROVED contractor, and
  * every Bristol postcode district BS1-BS8 is served by at least one
    APPROVED contractor in every trade.

Deliberately does not assert exact counts or names -- the roster is free to
grow -- only that the coverage matrix stays whole. Revert the roster
addition in app/seed.py and this test fails.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import session_scope
from app.models import ContractorModel
from app.schemas import ContractorApprovalStatus, Trade
from app.seed import seed

BRISTOL_DISTRICTS = [f"BS{n}" for n in range(1, 9)]  # BS1..BS8


async def _approved_contractors() -> list[ContractorModel]:
    async with session_scope() as session:
        result = await session.execute(
            select(ContractorModel).where(
                ContractorModel.approval_status == ContractorApprovalStatus.APPROVED
            )
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_every_trade_has_an_approved_contractor(app_db):
    await seed()
    contractors = await _approved_contractors()

    trades_covered = {trade for c in contractors for trade in c.trades}

    missing = [trade.value for trade in Trade if trade.value not in trades_covered]
    assert not missing, (
        f"Trade(s) with zero APPROVED contractors after seed(): {missing}. "
        "A ticket in this trade has no eligible contractor and must dead-end "
        "at escalation."
    )


@pytest.mark.asyncio
async def test_every_trade_covers_bristol_bs1_to_bs8(app_db):
    await seed()
    contractors = await _approved_contractors()

    gaps: list[str] = []
    for trade in Trade:
        trade_contractors = [c for c in contractors if trade.value in c.trades]
        districts_covered = {
            postcode for c in trade_contractors for postcode in c.service_postcodes
        }
        for district in BRISTOL_DISTRICTS:
            if district not in districts_covered:
                gaps.append(f"{trade.value}/{district}")

    assert not gaps, (
        "Trade/postcode-district combinations with zero APPROVED, "
        f"in-area contractor after seed(): {gaps}. A repair ticket in one of "
        "these districts for that trade has no eligible contractor and must "
        "dead-end at escalation instead of finding one."
    )
