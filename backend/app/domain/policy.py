"""Deterministic authority, spend and safety policy. Source: docs/19.

Every amount here is a fictional demo fixture assigned by code, never
chosen by the model (docs/19: "Gemini cannot choose them").
"""
from __future__ import annotations

from app.schemas import Answer, RiskAssessment, Trade, WorkOrderKind

# Fictional demonstration amounts, pence. See docs/19_SAFETY_AND_ESCALATION.md.
ORDINARY_ROOFING_QUOTE_PENCE = 10_000
ORDINARY_AUTHORITY_LIMIT_PENCE = 25_000
SCAFFOLD_INSTALL_QUOTE_PENCE = 30_000
SCAFFOLD_REMOVE_QUOTE_PENCE = 7_500

FICTIONAL_QUOTES: dict[WorkOrderKind, int] = {
    WorkOrderKind.REPAIR: ORDINARY_ROOFING_QUOTE_PENCE,
    WorkOrderKind.SCAFFOLD_INSTALL: SCAFFOLD_INSTALL_QUOTE_PENCE,
    WorkOrderKind.SCAFFOLD_REMOVE: SCAFFOLD_REMOVE_QUOTE_PENCE,
}


def default_quote_pence(kind: WorkOrderKind) -> int:
    return FICTIONAL_QUOTES[kind]


def is_hazard(risk: RiskAssessment) -> bool:
    """Deterministic hazard gate, run before the coordinator and independent of it."""
    return Answer.YES in (
        risk.gas,
        risk.fire,
        risk.water_near_electrics,
        risk.structural_danger,
        risk.uncontrolled_flood,
    )


def has_unknown_critical_safety_fact(risk: RiskAssessment) -> bool:
    return Answer.UNKNOWN in (
        risk.gas,
        risk.fire,
        risk.water_near_electrics,
        risk.structural_danger,
        risk.uncontrolled_flood,
    )


def vulnerability_requires_reviewed_plan(risk: RiskAssessment) -> bool:
    """docs/19: a vulnerability or accessibility concern affecting safety or
    contact permits automatic booking "only with explicit reviewed plan".

    This is deliberately *not* part of `is_hazard`. A hazard stops the
    case dead and escalates before any model call; a vulnerability
    concern must not do that, because the repair still needs doing and
    freezing the case would help nobody. What docs/19 requires is that a
    human sees the visit before it is committed -- which is exactly what
    the approval gate already provides.

    `vulnerability_concern` was collected at intake, stored on the case
    and rendered in the UI, but no policy function read it, so the
    docs/19 row was unenforced: a case flagged as involving a vulnerable
    occupant auto-booked on the same rules as any other.
    """
    return risk.vulnerability_concern == Answer.YES


def work_order_requires_approval_to_schedule(
    kind: WorkOrderKind,
    quote_pence: int | None,
    limit_pence: int | None,
    risk: RiskAssessment | None = None,
) -> bool:
    """docs/10: "Seeded ordinary mock repair within explicit demo authority can
    auto-book; all scaffolding and real commitments need approval."
    docs/19 adds: and anything touching a vulnerable occupant.

    `risk` is optional so existing callers that genuinely have no case
    context keep working, but the executor always passes it -- an
    omitted risk must never be read as "no concern".
    """
    if risk is not None and vulnerability_requires_reviewed_plan(risk):
        return True
    if kind in (WorkOrderKind.SCAFFOLD_INSTALL, WorkOrderKind.SCAFFOLD_REMOVE):
        return True
    if quote_pence is None or limit_pence is None:
        return True
    return quote_pence > limit_pence


def report_acceptance_requires_approval(kind: WorkOrderKind) -> bool:
    """docs/10: scaffold handover/removal acceptance requires operator
    verification; ordinary mock repair may auto-accept."""
    return kind in (WorkOrderKind.SCAFFOLD_INSTALL, WorkOrderKind.SCAFFOLD_REMOVE)


def triage_requires_approval(risk: RiskAssessment) -> bool:
    return is_hazard(risk) or has_unknown_critical_safety_fact(risk) or risk.urgency == "EMERGENCY"


def trade_for_kind(kind: WorkOrderKind, fallback: Trade) -> Trade:
    if kind == WorkOrderKind.SCAFFOLD_INSTALL or kind == WorkOrderKind.SCAFFOLD_REMOVE:
        return Trade.SCAFFOLDING
    return fallback
