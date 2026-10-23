"""An audit run carried through its four stages by jobs on a queue of its own, one job per run at a time."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import httpx
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.lease import advisory_lease
from assistant_core.tasks.app import task_app
from procrastinate.exceptions import AlreadyEnqueued
from pydantic import BaseModel, ConfigDict, Field
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import ExternalServiceError, WDKLoginRequiredError
from veupathdb_mcp.search_line import told_while_waiting

from pathfinder.domain.audit.findings import AuditOutcome, counts_of
from pathfinder.domain.audit.scope import AuditScope
from pathfinder.domain.audit.stages import RunStatus, StageName
from pathfinder.persistence.models import AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_tallies import AuditTallyRepository
from pathfinder.platform.config import get_settings
from pathfinder.platform.log_ids import LogIds, log_ids_scope
from pathfinder.services.audit import units
from pathfinder.services.audit.collect import run_collect_stage
from pathfinder.services.audit.confirm import run_confirm_stage
from pathfinder.services.audit.progress import (
    RunLanes,
    StageLane,
    waiting_for_sign_in,
)
from pathfinder.services.audit.queue import AUDIT_JOB, AUDIT_QUEUE, audit_lock, working
from pathfinder.services.audit.runs import RunOwner, create_run, owned_run
from pathfinder.services.audit.screen import run_screen_stage
from pathfinder.services.audit.sign_in import (
    AuditsDisabledError,
    seal_sign_in,
    signed_in_as_owner,
)
from pathfinder.services.audit.tie_break import run_tie_break_stage
from pathfinder.services.audit.units import (
    SIGN_IN_NEEDED,
    ContinueLaterError,
    SignInNeededError,
    Waits,
)
from pathfinder.services.site_errors import unreached
from pathfinder.services.wdk_identity import require_registered_wdk_login

_BODIES: dict[
    StageName, Callable[[AuditRunRecord, StageLane, Waits], Awaitable[None]]
] = {
    "collect": run_collect_stage,
    "screen": run_screen_stage,
    "confirm": run_confirm_stage,
    "tie_break": run_tie_break_stage,
}


class AuditJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID
    deadline: datetime
    pause: float = Field(gt=0)


async def _defer(job: AuditJob, *, after: float) -> None:
    lock = audit_lock(job.run_id)
    deferrer = task_app().configure_task(
        name=AUDIT_JOB,
        queue=AUDIT_QUEUE,
        lock=lock,
        queueing_lock=lock,
        schedule_in={"seconds": after},
    )
    try:
        await deferrer.defer_async(payload=job.model_dump(mode="json"))
    except AlreadyEnqueued:
        return


async def _registered_token() -> str:
    token = veupathdb_auth_token_ctx.get()
    if token is None:
        raise WDKLoginRequiredError
    await require_registered_wdk_login()
    return token


async def _signed_in(run: AuditRunRecord) -> str:
    try:
        return await _registered_token()
    except WDKLoginRequiredError:
        if run.status != "finished":
            async with async_session_factory() as session:
                repo = AuditRepository(session)
                await repo.set_halted(run.id, SIGN_IN_NEEDED)
                await repo.set_token(run.id, None)
                await session.commit()
        raise


async def _outcome(run: AuditRunRecord) -> AuditOutcome:
    async with async_session_factory() as session:
        tally = await AuditTallyRepository(session).tally(run.id)
        genomes = await AuditRepository(session).genome_states(run.id)
    return AuditOutcome(
        run_id=run.id,
        status=run.status,
        release=run.release,
        requests=run.stages.requests,
        unfinished=run.stages.unfinished,
        counts=counts_of(tally),
        failed_genomes=tuple(g.organism for g in genomes if g.status == "failed"),
        unreached_genomes=tuple(g.organism for g in genomes if g.status == "unreached"),
        unread_genomes=tuple(g.organism for g in genomes if g.status == "unread"),
        halted=run.stages.halted,
    )


async def outcome(run_id: UUID, owner: RunOwner) -> AuditOutcome:
    return await _outcome(await owned_run(run_id, owner))


async def start_run(
    run_id: UUID, owner: RunOwner, *, retry_unreached: bool = False
) -> AuditOutcome:
    run = await owned_run(run_id, owner)
    finished = run.status == "finished"
    if await working(run_id) or (finished and not retry_unreached):
        return await _outcome(run)
    kept = seal_sign_in(run_id, owner.user_id, await _signed_in(run))
    deadline = datetime.now(UTC) + timedelta(hours=get_settings().audit_run_hours)
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        if finished and await repo.reopen_unreached(run_id) is None:
            return await _outcome(run)
        await repo.set_deadline(run_id, deadline)
        await repo.set_halted(run_id, None)
        await repo.set_token(run_id, kept)
        await session.commit()
    await _defer(
        AuditJob(run_id=run_id, deadline=deadline, pause=units.FIRST_WAIT_SECONDS),
        after=0,
    )
    return await outcome(run_id, owner)


async def begin_run(*, owner: RunOwner, scope: AuditScope) -> AuditOutcome:
    settings = get_settings()
    if settings.provider_key_cipher is None:
        raise AuditsDisabledError
    await require_registered_wdk_login()
    admitted = AuditScope.admitted(
        scope.model_dump(mode="json", by_alias=True),
        max_genomes=settings.audit_max_genomes,
    )
    return await start_run(await create_run(owner=owner, scope=admitted), owner)


async def _stored(run_id: UUID) -> AuditRunRecord | None:
    async with async_session_factory() as session:
        return await AuditRepository(session).stored_run(run_id)


async def _set_status(run_id: UUID, status: RunStatus) -> None:
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.set_status(run_id, status)
        if status == "finished":
            await repo.set_token(run_id, None)
        await session.commit()


async def _finish_stage(run_id: UUID, stage: StageName) -> None:
    async with async_session_factory() as session:
        await AuditRepository(session).finish_stage(run_id, stage)
        await session.commit()


async def _halt(
    run_id: UUID, lanes: RunLanes, stage: StageName, forbidden: tuple[str, ...] = ()
) -> None:
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.release_trying(run_id)
        await repo.reopen_refused(run_id, forbidden)
        await repo.set_halted(run_id, SIGN_IN_NEEDED)
        await repo.set_token(run_id, None)
        await session.commit()
    await lanes.say(stage, SIGN_IN_NEEDED)


async def _failed(run_id: UUID, error: Exception) -> None:
    reason = f"the audit job failed: {type(error).__name__}: {error}"
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.note_on_trying(run_id, reason)
        await repo.set_halted(run_id, reason)
        await repo.set_token(run_id, None)
        await session.commit()


async def _carry(run: AuditRunRecord, lanes: RunLanes, waits: Waits) -> None:
    while (stage := run.stages.next_stage) is not None:
        try:
            await _BODIES[stage](run, lanes.lane(stage), waits)
        except SignInNeededError as refused:
            await _halt(run.id, lanes, stage, refused.forbidden)
            return
        await _finish_stage(run.id, stage)
        found = await _stored(run.id)
        if found is None:
            return
        run = found
        waits = replace(waits, first_seconds=units.FIRST_WAIT_SECONDS)
    await _set_status(run.id, "finished")


async def _sign_in_check() -> Literal["held", "refused", "unanswered"]:
    try:
        await require_registered_wdk_login()
    except WDKLoginRequiredError:
        return "refused"
    except (httpx.TransportError, ExternalServiceError) as exc:
        if not unreached(exc):
            raise
        return "unanswered"
    return "held"


async def _waited_for_sign_in(
    run: AuditRunRecord, lanes: RunLanes, stage: StageName, job: AuditJob
) -> bool:
    left = (job.deadline - datetime.now(UTC)).total_seconds()
    if left <= 0:
        return False
    pause = min(job.pause, left)
    await lanes.say(stage, waiting_for_sign_in(run.site_id, pause))
    await _defer(
        job.model_copy(
            update={"pause": min(job.pause * 2, units.LONGEST_WAIT_SECONDS)}
        ),
        after=pause,
    )
    return True


async def _carry_signed_in(run: AuditRunRecord, job: AuditJob) -> None:
    lanes = RunLanes(run)
    stage = run.stages.next_stage
    if stage is None:
        await _set_status(run.id, "finished")
        return
    match await _sign_in_check():
        case "refused":
            await _halt(run.id, lanes, stage)
            return
        case "unanswered" if await _waited_for_sign_in(run, lanes, stage, job):
            return
        case _:
            pass
    await _set_status(run.id, "running")
    waits = units.waits_until(job.deadline, first_seconds=job.pause)
    with told_while_waiting(lanes), units.watching_refusals():
        try:
            await _carry(run, lanes, waits)
        except ContinueLaterError as later:
            await _defer(
                AuditJob(
                    run_id=run.id, deadline=job.deadline, pause=later.next_seconds
                ),
                after=later.seconds,
            )


def _run_log_ids(run: AuditRunRecord) -> LogIds:
    return LogIds(
        run_id=run.id,
        user_id=run.user_id,
        conversation_id=run.conversation_id,
        site_id=run.site_id,
    )


async def carry_run(job: AuditJob) -> None:
    async with advisory_lease(audit_lock(job.run_id)) as held:
        run = await _stored(job.run_id) if held else None
        if run is None or run.status == "finished" or run.stages.halted:
            return
        try:
            with log_ids_scope(_run_log_ids(run)):
                async with signed_in_as_owner(run):
                    await _carry_signed_in(run, job)
        except Exception as error:
            await _failed(run.id, error)
            raise


async def resume_stranded_runs() -> None:
    async with async_session_factory() as session:
        resumable = await AuditRepository(session).resumable_runs()
    for run in resumable:
        stranded = run.stages.halted is None and not await working(run.id)
        if run.deadline_at is not None and stranded:
            await _defer(
                AuditJob(
                    run_id=run.id,
                    deadline=run.deadline_at,
                    pause=units.FIRST_WAIT_SECONDS,
                ),
                after=0,
            )
