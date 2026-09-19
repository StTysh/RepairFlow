"""Dependency DAG helpers. Direction: prerequisite -> dependent (docs/07)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DependencyModel
from app.schemas import DependencyStatus


async def reaches(session: AsyncSession, case_id: str, start: str, target: str) -> bool:
    """True if `target` is reachable from `start` by following prerequisite -> dependent
    edges (any status). Used to reject an edge that would close a cycle."""
    rows = (
        await session.execute(
            select(DependencyModel.prerequisite_work_order_id, DependencyModel.dependent_work_order_id).where(
                DependencyModel.case_id == case_id
            )
        )
    ).all()
    adjacency: dict[str, list[str]] = {}
    for prerequisite_id, dependent_id in rows:
        adjacency.setdefault(prerequisite_id, []).append(dependent_id)

    stack = [start]
    seen: set[str] = set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, []))
    return False


async def would_create_cycle(session: AsyncSession, case_id: str, prerequisite_id: str, dependent_id: str) -> bool:
    if prerequisite_id == dependent_id:
        return True
    # Adding prerequisite -> dependent creates a cycle iff dependent can already
    # reach prerequisite (that path plus the new edge closes the loop).
    return await reaches(session, case_id, dependent_id, prerequisite_id)


async def incoming_edges(session: AsyncSession, case_id: str, work_order_id: str) -> list[DependencyModel]:
    rows = (
        await session.execute(
            select(DependencyModel).where(
                DependencyModel.case_id == case_id,
                DependencyModel.dependent_work_order_id == work_order_id,
            )
        )
    ).scalars().all()
    return list(rows)


async def all_incoming_satisfied(session: AsyncSession, case_id: str, work_order_id: str) -> bool:
    edges = await incoming_edges(session, case_id, work_order_id)
    if not edges:
        return True
    return all(edge.status == DependencyStatus.SATISFIED for edge in edges)
