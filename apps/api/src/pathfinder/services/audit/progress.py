"""Each audit stage's progress, stored on its run: how far it has come and what it last said."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from assistant_core.platform.db import async_session_factory

from pathfinder.domain.audit.stages import StageName, StageRecord
from pathfinder.persistence.models import AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.services.search_waits import waiting_for


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def waiting(site_id: str, seconds: float, count: int, word: str) -> str:
    return f"waiting {seconds:g} s for {site_id}, {plural(count, word)} unanswered"


def waiting_for_sign_in(site_id: str, seconds: float) -> str:
    return f"waiting {seconds:g} s for {site_id} to check the sign-in"


def not_read(count: int, word: str) -> str:
    return f"{plural(count, word)} not read before the run's deadline"


class StageLane(Protocol):
    async def update(self, *, done: int, total: int, message: str) -> None: ...


class _RunLane:
    def __init__(self, run_id: UUID, stored: StageRecord) -> None:
        self._run_id = run_id
        self._stage: StageName = stored.name
        self._done = stored.done
        self._total = stored.total
        self.message = stored.message

    async def update(self, *, done: int, total: int, message: str) -> None:
        self._done, self._total, self.message = done, total, message
        await self.say(message)

    async def say(self, message: str) -> None:
        async with async_session_factory() as session:
            await AuditRepository(session).record_progress(
                self._run_id,
                self._stage,
                done=self._done,
                total=self._total,
                message=message,
            )
            await session.commit()


class RunLanes:
    def __init__(self, run: AuditRunRecord) -> None:
        self._run_id = run.id
        self._stored = {stage.name: stage for stage in run.stages.stages}
        self._lanes: dict[StageName, _RunLane] = {}
        self._current: _RunLane | None = None

    def _lane(self, stage: StageName) -> _RunLane:
        if stage not in self._lanes:
            self._lanes[stage] = _RunLane(self._run_id, self._stored[stage])
        self._current = self._lanes[stage]
        return self._current

    def lane(self, stage: StageName) -> StageLane:
        return self._lane(stage)

    async def say(self, stage: StageName, message: str) -> None:
        await self._lane(stage).say(message)

    async def waiting(self, site_id: str) -> None:
        if self._current is not None:
            await self._current.say(waiting_for(site_id))

    async def running(self, site_id: str) -> None:
        del site_id
        if self._current is not None:
            await self._current.say(self._current.message)
