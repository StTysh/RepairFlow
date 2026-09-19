"""Typed dependencies injected into the coordinator agent (docs/09).

Deliberately holds no open database session: the model call is a network
round-trip, and "no open transaction across a model/provider request"
(docs/05/17) applies to reads too under SQLite/WAL. Each read tool opens
its own short-lived session_scope() per invocation instead.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclasses.dataclass(frozen=True)
class CoordinatorDeps:
    case_id: str
    snapshot_version: int
    run_id: str
    policy_snapshot: dict
    clock: Callable[[], datetime] = utcnow
