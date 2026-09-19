"""POST /api/v1/actions/{id}/approval (docs/16)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain.errors import ConflictError
from app.domain.services import ActorContext
from app.orchestration.executor import decide_approval
from app.schemas import ApprovalDecision, ApprovalResponse

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])


@router.post("/actions/{action_id}/approval", status_code=202)
async def decide_approval_endpoint(action_id: str, decision: ApprovalDecision, operator: str = Depends(require_operator), session: AsyncSession = Depends(get_session)) -> ApprovalResponse:
    # decide_approval acts purely on decision.action_id, never the path
    # segment -- without this check a stale UI/copy-paste body could
    # silently approve or reject a DIFFERENT action than the URL names.
    # This gates spend/scheduling (docs/19: "Approval binds operator ID...
    # and permitted spend"), so a disagreement must be a hard error, not a
    # best-effort guess at which one was meant.
    if str(decision.action_id) != action_id:
        raise ConflictError(f"path action_id {action_id} does not match request body action_id {decision.action_id}")
    result = await decide_approval(session, decision, ActorContext("OPERATOR", operator, str(uuid.uuid4())))
    return ApprovalResponse(result=result)
