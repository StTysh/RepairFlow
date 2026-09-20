"""Operator-recorded field updates: what a person reports actually happened.

This replaces the retired "simulate an observation" demo control. The
capability is the same and the endpoints it calls are the same domain
services -- what changed is the claim being made. A demo control asserted
that a fictional contractor had reported something; these endpoints record
that a *named operator*, at a recorded time, is relaying something a real
contractor or tenant told them.

That distinction is the whole point (docs/19, and the standing rule that
external events are never silently inferred):

* The operator's identity comes from the authenticated session, never from
  the request body, so attribution cannot be spoofed by the client.
* `EvidenceRef.source_type` is OPERATOR: the system is recording hearsay
  relayed by a person, not a fact it observed itself.
* Provenance is LIVE. These describe real-world events that genuinely
  occurred; they are not simulated. What makes them *second-hand* is the
  OPERATOR source type, which downstream policy already understands --
  overloading provenance to mean "second-hand" would break the
  LIVE/SIMULATED/FIXTURE distinction that marks real provider traffic.
* Nothing here contacts anybody. An operator recording that a contractor
  phoned in a report is a write to this database and nothing else.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_operator
from app.domain import services
from app.domain.errors import DomainError, NotFoundError
from app.domain.services import ActorContext
from app.models import AppointmentModel, CommunicationModel
from app.schemas import (
    ApprovalResponse,
    EvidenceRef,
    ObservationSubmission,
    Provenance,
    ReportSubmission,
    ReportSubmitResponse,
    SourceType,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])


class ContractorReportUpdate(BaseModel):
    """A contractor told the operator what they found on site."""

    kind: Literal["CONTRACTOR_REPORT"] = "CONTRACTOR_REPORT"
    appointment_id: uuid.UUID
    text: str = Field(min_length=4, max_length=4000)
    observed_at: datetime
    # Who actually said it, in the operator's words -- so the record names
    # a source rather than attributing the statement to the system.
    reported_by: str = Field(min_length=2, max_length=128)


class TenantUpdate(BaseModel):
    """A tenant told the operator whether the issue is resolved."""

    kind: Literal["TENANT_UPDATE"] = "TENANT_UPDATE"
    confirms_resolved: bool
    text: str = Field(min_length=4, max_length=4000)
    reported_by: str = Field(min_length=2, max_length=128)


class AttendanceWindowEndedUpdate(BaseModel):
    """The booked visit window has passed with no report received."""

    kind: Literal["ATTENDANCE_WINDOW_ENDED"] = "ATTENDANCE_WINDOW_ENDED"
    appointment_id: uuid.UUID


FieldUpdate = Annotated[
    Union[ContractorReportUpdate, TenantUpdate, AttendanceWindowEndedUpdate],
    Field(discriminator="kind"),
]


class TenantUpdateResponse(BaseModel):
    communication_id: str
    result: dict | object


@router.post("/cases/{case_id}/field-updates", status_code=202)
async def record_field_update(
    case_id: str,
    update: FieldUpdate,
    session: AsyncSession = Depends(get_session),
    operator: str = Depends(require_operator),
):
    recorded_at = datetime.now(timezone.utc)
    actor = ActorContext("OPERATOR", operator, str(uuid.uuid4()))

    if isinstance(update, ContractorReportUpdate):
        if update.observed_at > recorded_at:
            raise DomainError("observed_at cannot be in the future")
        appointment = await session.get(AppointmentModel, str(update.appointment_id))
        if appointment is None or appointment.case_id != case_id:
            raise NotFoundError(f"appointment {update.appointment_id} not in case {case_id}")
        report_id, result = await services.record_contractor_report(
            session,
            submission=ReportSubmission(
                work_order_id=uuid.UUID(appointment.work_order_id),
                appointment_id=update.appointment_id,
                contractor_id=uuid.UUID(appointment.contractor_id),
                text=f"{update.text}\n\n[Relayed by {update.reported_by}; recorded by {operator}]",
                observed_at=update.observed_at,
            ),
            source_ref=EvidenceRef(
                source_type=SourceType.OPERATOR,
                source_id=f"operator:{operator}",
                observed_at=recorded_at,
                provenance=Provenance.LIVE,
            ),
            provenance=Provenance.LIVE,
            actor=actor,
        )
        return ReportSubmitResponse(report_id=report_id, result=result)

    if isinstance(update, TenantUpdate):
        case = await services.load_case(session, case_id)
        comm_id = str(uuid.uuid4())
        session.add(
            CommunicationModel(
                id=comm_id,
                case_id=case_id,
                tenant_id=case.tenant_id,
                purpose="FOLLOW_UP",
                direction="BROWSER",
                provider="OPERATOR",
                correlation_token_hash=str(uuid.uuid4()),
                state="ENDED",
                provenance=Provenance.LIVE,
                started_at=recorded_at,
                ended_at=recorded_at,
            )
        )
        await session.flush()
        result = await services.record_observations(
            session,
            case_id=case_id,
            communication_id=comm_id,
            submission=ObservationSubmission(
                communication_id=uuid.UUID(comm_id),
                tenant_confirms_resolved=update.confirms_resolved,
                source_text=f"{update.text}\n\n[Relayed by {update.reported_by}; recorded by {operator}]",
            ),
            actor=actor,
        )
        return TenantUpdateResponse(communication_id=comm_id, result=result)

    result = await services.mark_attendance_window_ended(
        session, case_id=case_id, appointment_id=str(update.appointment_id), actor=actor
    )
    return ApprovalResponse(result=result)
