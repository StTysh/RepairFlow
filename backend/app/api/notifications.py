"""Bell-icon notification feed (docs/16-adjacent; added for the Fixi UI
integration phase). Deliberately derived only from existing ActionRecord
(AWAITING_APPROVAL) and CaseEvent (CASE_ESCALATED) rows -- no new
notification-authoring system, per the project's decision to keep this
simple. See services.load_notifications for exactly how `unread` is
defined (there is no separate persisted read-state table).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain import services
from app.schemas import NotificationsResponse

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])


@router.get("/notifications")
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=200), session: AsyncSession = Depends(get_session),
) -> NotificationsResponse:
    items = await services.load_notifications(session, limit=limit)
    return NotificationsResponse(items=items, unread_count=sum(1 for item in items if item.unread))
