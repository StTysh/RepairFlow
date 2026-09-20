"""Legal state transitions. Source of truth: docs/07_CASE_STATE_MACHINE.md.

These are pure guards over the enum graphs in the two Mermaid diagrams.
Nothing here touches the database; callers in services.py decide *when*
a transition should happen, these functions decide whether it is *allowed*.
"""
from __future__ import annotations

from app.domain.errors import PolicyRejectedError
from app.schemas import CaseStatus, WorkOrderStatus

_WORK_ORDER_EDGES: dict[WorkOrderStatus, set[WorkOrderStatus]] = {
    WorkOrderStatus.READY: {WorkOrderStatus.SCHEDULED, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.BLOCKED: {WorkOrderStatus.READY, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.SCHEDULED: {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.AWAITING_REPORT,
        WorkOrderStatus.READY,  # cancellation confirmed
    },
    WorkOrderStatus.IN_PROGRESS: {WorkOrderStatus.AWAITING_REPORT},
    WorkOrderStatus.AWAITING_REPORT: {
        WorkOrderStatus.BLOCKED,  # prerequisite discovered from the report
        WorkOrderStatus.COMPLETED,
        WorkOrderStatus.READY,  # no access / failed attempt
    },
    WorkOrderStatus.COMPLETED: set(),
    WorkOrderStatus.CANCELLED: set(),
}

_CASE_EDGES: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.ACTIVE: {CaseStatus.AWAITING_CONFIRMATION, CaseStatus.ESCALATED, CaseStatus.CANCELLED},
    CaseStatus.AWAITING_CONFIRMATION: {
        CaseStatus.RESOLVED,
        CaseStatus.ACTIVE,
        CaseStatus.ESCALATED,
    },
    CaseStatus.ESCALATED: {CaseStatus.ACTIVE, CaseStatus.AWAITING_CONFIRMATION, CaseStatus.CANCELLED},
    CaseStatus.RESOLVED: {CaseStatus.ACTIVE, CaseStatus.ESCALATED},
    CaseStatus.CANCELLED: set(),
}


def assert_work_order_transition(current: WorkOrderStatus, target: WorkOrderStatus) -> None:
    if current == target:
        return
    if target not in _WORK_ORDER_EDGES.get(current, set()):
        raise PolicyRejectedError(f"illegal work order transition {current} -> {target}")


def assert_case_transition(current: CaseStatus, target: CaseStatus) -> None:
    return
