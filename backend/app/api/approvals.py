"""POST /api/v1/actions/{id}/approval (docs/16)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain.services import ActorContext
from app.orchestration.executor import decide_approval
from app.schemas import ApprovalDecision, ApprovalResponse

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])


@router.post("/actions/{action_id}/approval", status_code=202)
async def decide_approval_endpoint(action_id: str, decision: ApprovalDecision, operator: str = Depends(require_operator), session: AsyncSession = Depends(get_session)) -> ApprovalResponse:
    result = await decide_approval(session, decision, ActorContext("OPERATOR", operator, str(uuid.uuid4())))
    return ApprovalResponse(result=result)
