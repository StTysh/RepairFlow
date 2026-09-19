"""POST /api/v1/cases/{id}/observations (docs/16)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_session, require_operator
from app.domain import services
from app.domain.services import ActorContext
from app.schemas import ObservationSubmission
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])


@router.post("/cases/{case_id}/observations", status_code=202)
async def submit_observations(case_id: str, submission: ObservationSubmission, session: AsyncSession = Depends(get_session)) -> dict:
    result = await services.record_observations(
        session, case_id=case_id, communication_id=str(submission.communication_id), submission=submission,
        actor=ActorContext("OPERATOR", "operator", str(uuid.uuid4())),
    )
    return {"result": result}
