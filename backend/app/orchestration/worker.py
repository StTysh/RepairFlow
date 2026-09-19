"""Single database-backed worker loop. One process, one worker (docs/05/17):
claim one due job under a short transaction, do its work, mark it DONE or
FAILED. No coroutine sleeps for days; FOLLOW_UP/EXECUTE_ACTION/COORDINATE
are all separate bounded runs woken by rows in `jobs`.
"""
from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_scope
from app.domain import services
from app.domain.services import ActorContext
from app.models import CommunicationModel, JobModel
from app.orchestration import dispatcher, executor
from app.orchestration.dispatcher import Coordinator
from app.schemas import CaseStatus

# >= coordinator.RUN_TIMEOUT_SECONDS (120s) so a COORDINATE job's lease
# can't expire while its run is still legitimately in progress. Only one
# worker task ever runs (see run_worker_loop), so a longer lease isn't a
# double-claim risk here -- it only matters for stale-lease reclaim after a
# crash, which this still bounds.
LEASE_SECONDS = 120
# COORDINATE calls a real model with real network latency (unlike the other
# job kinds, which are local or already have their own retry semantics) --
# a single slow response should not permanently kill a case's progress with
# no automatic retry. Bounded, not unlimited (CLAUDE.md: "bounded retries").
MAX_COORDINATE_ATTEMPTS = 3
COORDINATE_RETRY_DELAY_SECONDS = 5

# There is no live ElevenLabs webhook wired up (no public URL to sign
# against, see backend/.env's comment on ELEVENLABS_WEBHOOK_SECRET) --
# CLAUDE.md's "use polling" is the real mechanism here. Without this sweep,
# a real autonomous call's Communication row would sit at state=ACTIVE
# forever once the call actually ends, since nothing else ever re-checks
# it. Found live: a finished call still showed "in progress" with no
# automatic reconciliation.
RECONCILE_SWEEP_INTERVAL_SECONDS = 5
RECONCILE_MIN_CALL_AGE_SECONDS = 15


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def claim_job(session: AsyncSession) -> JobModel | None:
    now = utcnow()
    candidate = (
        await session.execute(
            select(JobModel).where(JobModel.status == "PENDING", JobModel.run_at <= now).order_by(JobModel.run_at).limit(1)
        )
    ).scalars().first()
    if candidate is None:
        candidate = (
            await session.execute(
                select(JobModel).where(JobModel.status == "LEASED", JobModel.lease_until < now).order_by(JobModel.lease_until).limit(1)
            )
        ).scalars().first()
    if candidate is None:
        return None
    candidate.status = "LEASED"
    candidate.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    candidate.attempts += 1
    await session.flush()
    return candidate


async def _handle_follow_up(case_id: str, payload: dict, coordinator: Coordinator) -> None:
    async with session_scope() as session:
        case = await services.load_case(session, case_id)
        if case.status in (CaseStatus.RESOLVED, CaseStatus.CANCELLED):
            return
        event = await services.append_event(
            session, case_id=case_id, event_type="FOLLOW_UP_DUE", payload={"reason": payload.get("reason")},
            actor=ActorContext("SYSTEM", "follow-up-timer", case_id),
            source_event_key=f"followup-due:{case_id}:{utcnow().isoformat()}",
        )
        event_id = event.id

    await dispatcher.run_coordinate(case_id=case_id, trigger_event_id=event_id, coordinator=coordinator)


async def process_one_job(
    coordinator: Coordinator, *, elevenlabs_configured: bool = False, research_adapter=None, raise_on_error: bool = False,
) -> bool:
    """Claims and processes at most one due job. Returns True if a job was
    processed (regardless of success/failure), False if none was due.

    raise_on_error=True (tests only) re-raises instead of swallowing into
    JobModel.last_error -- the production default stays False so one bad
    job can never take down the worker loop."""
    async with session_scope() as session:
        job = await claim_job(session)
        if job is None:
            return False
        job_id, kind, payload, case_id = job.id, job.kind, dict(job.payload or {}), job.case_id

    try:
        if kind == "COORDINATE":
            await dispatcher.run_coordinate(
                case_id=case_id, trigger_event_id=payload["trigger_event_id"], coordinator=coordinator,
            )
        elif kind == "EXECUTE_ACTION":
            await executor.execute_action(
                payload["action_id"], elevenlabs_configured=elevenlabs_configured, research_adapter=research_adapter,
            )
        elif kind == "FOLLOW_UP":
            await _handle_follow_up(case_id, payload, coordinator)
        elif kind == "FETCH_RECORDING":
            from app.integrations import elevenlabs as elevenlabs_integration

            await elevenlabs_integration.fetch_recording(payload["communication_id"])
        elif kind == "PLACE_CALL":
            from app.integrations import elevenlabs as elevenlabs_integration

            await elevenlabs_integration.place_call(payload["communication_id"], question=payload.get("question", ""))
        else:
            raise ValueError(f"unknown job kind {kind}")

        async with session_scope() as session:
            done_job = await session.get(JobModel, job_id)
            if done_job is not None:
                done_job.status = "DONE"
        return True
    except Exception as exc:  # noqa: BLE001 - isolate one job's failure from the worker loop
        async with session_scope() as session:
            failed_job = await session.get(JobModel, job_id)
            if failed_job is not None:
                failed_job.last_error = f"{exc}\n{traceback.format_exc()}"[:4000]
                if kind == "COORDINATE" and failed_job.attempts < MAX_COORDINATE_ATTEMPTS:
                    # Retry in place rather than a dead job with no path
                    # back: same row, same dedupe_key, so nothing double-
                    # enqueues it meanwhile.
                    failed_job.status = "PENDING"
                    failed_job.run_at = datetime.now(timezone.utc) + timedelta(seconds=COORDINATE_RETRY_DELAY_SECONDS)
                else:
                    failed_job.status = "FAILED"
        if raise_on_error:
            raise
        return True


async def sweep_stale_live_calls() -> None:
    """Finds real calls (provenance=LIVE, a bound provider_conversation_id)
    still sitting at state ACTIVE/REQUESTED after a minimum age, and
    enqueues FETCH_RECORDING for each. fetch_recording itself now checks
    the remote call status and no-ops if it isn't actually over yet, so
    this is safe to call on the same rows repeatedly. Bucketing the
    dedupe_key by sweep interval (not a fixed key) lets retries happen on
    the next sweep instead of being permanently blocked by enqueue_job's
    dedupe-forever-by-key behavior, while still not spamming a new job
    every worker tick."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=RECONCILE_MIN_CALL_AGE_SECONDS)
    bucket = int(datetime.now(timezone.utc).timestamp() // RECONCILE_SWEEP_INTERVAL_SECONDS)
    async with session_scope() as session:
        stale = (
            await session.execute(
                select(CommunicationModel).where(
                    CommunicationModel.state.in_(["ACTIVE", "REQUESTED"]),
                    CommunicationModel.provider_conversation_id.is_not(None),
                    CommunicationModel.provenance == "LIVE",
                    CommunicationModel.started_at < cutoff,
                )
            )
        ).scalars().all()
        for comm in stale:
            await services.enqueue_job(
                session, case_id=comm.case_id, kind="FETCH_RECORDING",
                dedupe_key=f"recording:sweep:{comm.id}:{bucket}",
                payload={"communication_id": comm.id},
            )


async def drain_due_jobs(
    coordinator: Coordinator, *, max_jobs: int = 50, elevenlabs_configured: bool = False,
    research_adapter=None, raise_on_error: bool = False,
) -> int:
    """Test/dev helper: process due jobs synchronously until none remain or
    max_jobs is hit. Returns the number processed."""
    count = 0
    while count < max_jobs:
        processed = await process_one_job(
            coordinator, elevenlabs_configured=elevenlabs_configured, research_adapter=research_adapter,
            raise_on_error=raise_on_error,
        )
        if not processed:
            break
        count += 1
    return count


async def run_worker_loop(
    coordinator: Coordinator, *, stop_event: asyncio.Event, elevenlabs_configured: bool = False,
    research_adapter=None, poll_interval: float = 0.75,
) -> None:
    last_sweep = 0.0
    while not stop_event.is_set():
        processed = await process_one_job(coordinator, elevenlabs_configured=elevenlabs_configured, research_adapter=research_adapter)

        loop_time = asyncio.get_event_loop().time()
        if elevenlabs_configured and loop_time - last_sweep >= RECONCILE_SWEEP_INTERVAL_SECONDS:
            await sweep_stale_live_calls()
            last_sweep = loop_time

        if not processed:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                pass
