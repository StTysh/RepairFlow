"""Persistent MockBookingConnector: the only automated booking connector in
this MVP (docs/10). Slots are generated deterministically on demand and
upserted into mock_slots so reservations have something stable to reference
across restarts; reservations are the real idempotency/duplicate-effect
surface under test.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ContractorModel, MockReservationModel, MockSlotModel, new_uuid
from app.schemas import (
    AppointmentQuery,
    BookingOutcome,
    BookingRequest,
    BookingStatus,
    CancellationOutcome,
    CancellationStatus,
    Provenance,
    SlotOption,
    Trade,
)

_BUSINESS_HOURS = (9, 13)  # two fixed daily slots: 09:00 and 13:00, 3h each
_SLOT_HORIZON_DAYS = 10


def _slot_id(contractor_id: str, start_at: datetime) -> str:
    return f"{contractor_id}:{start_at.date().isoformat()}:{start_at.hour:02d}"


async def _ensure_slots(session: AsyncSession, contractor_id: str, trade: Trade) -> list[MockSlotModel]:
    now = datetime.now(timezone.utc)
    # Never 0: a same-day slot's expires_at equals its start_at (below), so
    # it would be born already-expired for any slot generated after that
    # hour. 1 is the safe floor for a compressed demo timeline.
    start_offset = max(1, get_settings().demo_slot_offset_days)
    candidates: list[MockSlotModel] = []
    for day_offset in range(start_offset, _SLOT_HORIZON_DAYS):
        day = (now + timedelta(days=day_offset)).replace(minute=0, second=0, microsecond=0)
        if day.weekday() >= 5:  # skip weekends for a believable fictional calendar
            continue
        for hour in _BUSINESS_HOURS:
            start_at = day.replace(hour=hour)
            candidates.append((start_at, start_at + timedelta(hours=3)))

    result: list[MockSlotModel] = []
    for start_at, end_at in candidates:
        slot_id = _slot_id(contractor_id, start_at)
        existing = await session.get(MockSlotModel, slot_id)
        if existing is None:
            existing = MockSlotModel(
                slot_id=slot_id, contractor_id=contractor_id, trade=trade,
                start_at=start_at, end_at=end_at, expires_at=start_at, revision=1, is_reserved=False,
            )
            session.add(existing)
            await session.flush()
        result.append(existing)
    return result


class MockBookingConnector:
    """Local, in-database "provider". No real network call is made; results
    are still produced outside the caller's write transaction so the same
    commit-intent -> call -> commit-result shape works for a real connector
    later without restructuring callers."""

    async def list_slots(self, session: AsyncSession, query: AppointmentQuery, *, trade: Trade) -> list[SlotOption]:
        contractor = await session.get(ContractorModel, str(query.contractor_id))
        if contractor is None:
            return []
        slots = await _ensure_slots(session, contractor.id, trade)
        reserved_ids = set(
            (
                await session.execute(
                    select(MockReservationModel.slot_id).where(MockReservationModel.status == "RESERVED")
                )
            ).scalars().all()
        )
        return [
            SlotOption(
                slot_id=slot.slot_id, contractor_id=contractor.id, work_order_id=query.work_order_id,
                start_at=slot.start_at, end_at=slot.end_at, expires_at=slot.expires_at,
                availability_revision=slot.revision, provenance=Provenance.SIMULATED,
            )
            for slot in slots
            if slot.slot_id not in reserved_ids
        ]

    async def book(self, session: AsyncSession, request: BookingRequest, *, action_id: str) -> BookingOutcome:
        slot = await session.get(MockSlotModel, request.slot_id)
        if slot is None:
            return BookingOutcome(status=BookingStatus.REJECTED, reason="slot no longer exists", provenance=Provenance.SIMULATED)
        if slot.expires_at < datetime.now(timezone.utc):
            return BookingOutcome(status=BookingStatus.REJECTED, reason="slot expired", provenance=Provenance.SIMULATED)

        existing = (
            await session.execute(
                select(MockReservationModel).where(MockReservationModel.idempotency_key == request.idempotency_key)
            )
        ).scalars().first()
        if existing is not None:
            return BookingOutcome(
                status=BookingStatus.CONFIRMED, provider_booking_id=existing.provider_booking_id,
                confirmed_start=slot.start_at, confirmed_end=slot.end_at, provenance=Provenance.SIMULATED,
            )

        active = (
            await session.execute(
                select(MockReservationModel).where(
                    MockReservationModel.slot_id == request.slot_id, MockReservationModel.status == "RESERVED"
                )
            )
        ).scalars().first()
        if active is not None:
            return BookingOutcome(status=BookingStatus.REJECTED, reason="slot already reserved", provenance=Provenance.SIMULATED)

        provider_booking_id = f"mock-{new_uuid()[:8]}"
        reservation = MockReservationModel(
            id=new_uuid(), slot_id=request.slot_id, work_order_id=str(request.work_order_id),
            action_id=action_id, idempotency_key=request.idempotency_key,
            provider_booking_id=provider_booking_id, status="RESERVED",
        )
        session.add(reservation)
        slot.is_reserved = True
        await session.flush()
        return BookingOutcome(
            status=BookingStatus.CONFIRMED, provider_booking_id=provider_booking_id,
            confirmed_start=slot.start_at, confirmed_end=slot.end_at, provenance=Provenance.SIMULATED,
        )

    async def cancel(self, session: AsyncSession, provider_booking_id: str, idempotency_key: str) -> CancellationOutcome:
        reservation = (
            await session.execute(
                select(MockReservationModel).where(MockReservationModel.provider_booking_id == provider_booking_id)
            )
        ).scalars().first()
        if reservation is None:
            return CancellationOutcome(status=CancellationStatus.REJECTED, reason="no such booking", provenance=Provenance.SIMULATED)
        if reservation.status == "CANCELLED":
            return CancellationOutcome(status=CancellationStatus.CANCELLED, provider_booking_id=provider_booking_id, provenance=Provenance.SIMULATED)
        reservation.status = "CANCELLED"
        slot = await session.get(MockSlotModel, reservation.slot_id)
        if slot is not None:
            slot.is_reserved = False
        await session.flush()
        return CancellationOutcome(status=CancellationStatus.CANCELLED, provider_booking_id=provider_booking_id, provenance=Provenance.SIMULATED)


mock_booking_connector = MockBookingConnector()
