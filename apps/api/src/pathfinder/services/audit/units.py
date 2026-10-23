"""How an audit stage tells a site that did not answer from a read that failed, how long it waits, and how it records the requests one attempt sent."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

import httpx
import pydantic
from assistant_core.platform.db import async_session_factory
from fastmcp.exceptions import ToolError
from veupathdb.errors import VEuPathDBError

from pathfinder.domain.audit.stages import StageName
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.platform.metrics import RequestTally, counting_wdk_requests
from pathfinder.services.audit.sign_in import sign_in_holds
from pathfinder.services.site_errors import site_status, unreached

_FORBIDDEN = 403
FIRST_WAIT_SECONDS = 30.0
LONGEST_WAIT_SECONDS = 900.0
SLICE_SECONDS = 1800.0
SIGN_IN_NEEDED = "sign-in needed"
NOT_READ = "not read before the run's deadline"
UNIT_FAILURES = (httpx.HTTPError, VEuPathDBError, ToolError, pydantic.ValidationError)


REVOKED_AFTER = 3


class SignInNeededError(Exception):
    def __init__(self, forbidden: tuple[str, ...] = ()) -> None:
        super().__init__(SIGN_IN_NEEDED)
        self.forbidden = forbidden


class RefusalStreak:
    def __init__(self) -> None:
        self.messages: list[str] = []


_STREAK: ContextVar[RefusalStreak | None] = ContextVar(
    "audit_refusal_streak", default=None
)


@contextmanager
def watching_refusals() -> Iterator[RefusalStreak]:
    streak = RefusalStreak()
    reset = _STREAK.set(streak)
    try:
        yield streak
    finally:
        _STREAK.reset(reset)


def _note_forbidden(exc: BaseException) -> None:
    streak = _STREAK.get()
    if streak is None:
        return
    streak.messages.append(str(exc))
    if len(streak.messages) >= REVOKED_AFTER:
        raise SignInNeededError(tuple(streak.messages)) from exc


class ContinueLaterError(Exception):
    def __init__(self, *, seconds: float, next_seconds: float) -> None:
        super().__init__(f"the stage continues in {seconds:g} s")
        self.seconds = seconds
        self.next_seconds = next_seconds


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class Waits:
    deadline: datetime
    slice_ends: datetime
    first_seconds: float
    longest_seconds: float
    clock: Clock = field(default_factory=SystemClock)


def waits_until(deadline: datetime, *, first_seconds: float) -> Waits:
    return Waits(
        deadline=deadline,
        slice_ends=datetime.now(UTC) + timedelta(seconds=SLICE_SECONDS),
        first_seconds=first_seconds,
        longest_seconds=LONGEST_WAIT_SECONDS,
    )


def signed_out(exc: BaseException | None) -> bool:
    match site_status(exc):
        case 401:
            return True
        case 403:
            return not sign_in_holds()
        case _:
            return False


def _judged(exc: BaseException) -> BaseException | None:
    match exc:
        case ToolError():
            return exc.__cause__
        case _:
            return exc


def halt_when_signed_out(exc: BaseException) -> None:
    judged = _judged(exc)
    if signed_out(judged):
        raise SignInNeededError from exc
    if site_status(judged) == _FORBIDDEN:
        _note_forbidden(exc)


def failure_status(exc: BaseException) -> Literal["failed", "unreached"]:
    halt_when_signed_out(exc)
    return "unreached" if unreached(_judged(exc)) else "failed"


@asynccontextmanager
async def tallied(run_id: UUID, stage: StageName) -> AsyncIterator[RequestTally]:
    with counting_wdk_requests() as tally:
        try:
            yield tally
        except Exception:
            async with async_session_factory() as session:
                await AuditRepository(session).count_requests(
                    run_id, stage, tally.count, tally.store_reads
                )
                await session.commit()
            raise


async def in_passes[T](
    units: Sequence[T],
    attempt: Callable[[T], Awaitable[bool]],
    waits: Waits,
    *,
    unread: Callable[[Sequence[T]], Awaitable[None]],
    on_pause: Callable[[float, Sequence[T]], Awaitable[None]],
) -> list[T]:
    left: list[T] = []
    for k, unit in enumerate(units):
        now = waits.clock.now()
        if now >= waits.deadline:
            await unread(units[k:])
            return [*left, *units[k:]]
        if now >= waits.slice_ends:
            raise ContinueLaterError(seconds=0.0, next_seconds=waits.first_seconds)
        streak = _STREAK.get()
        refused = 0 if streak is None else len(streak.messages)
        if not await attempt(unit):
            left.append(unit)
        if streak is not None and len(streak.messages) == refused:
            streak.messages.clear()
    pause = waits.first_seconds
    if left and waits.clock.now() + timedelta(seconds=pause) < waits.deadline:
        await on_pause(pause, left)
        raise ContinueLaterError(
            seconds=pause, next_seconds=min(pause * 2, waits.longest_seconds)
        )
    return left
