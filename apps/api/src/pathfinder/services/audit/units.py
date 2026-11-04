"""How an audit stage tells a site that did not answer from a read that failed, how long it waits, and how it records the requests one attempt sent."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

import httpx
import pydantic
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from fastmcp.exceptions import ToolError
from veupathdb.errors import (
    DataParsingError,
    SiteNotFoundError,
    ValidationError,
    VEuPathDBError,
    WDKLoginRequiredError,
)

from pathfinder.domain.audit.stages import SIGN_IN_NEEDED, StageName
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.platform.errors import AppError, sanitize_error_for_client
from pathfinder.platform.metrics import RequestTally, counting_wdk_requests
from pathfinder.services.audit.sign_in import sign_in_check, sign_in_holds
from pathfinder.services.site_errors import SERVER_ERROR, site_status, unreached

logger = get_logger(__name__)
_FORBIDDEN = 403
_UNIT_FAILED = "An audit unit failed"
_CHECK_FAILED = "the check failed"
FIRST_WAIT_SECONDS = 30.0
LONGEST_WAIT_SECONDS = 900.0
SLICE_SECONDS = 1800.0
NOT_READ = "not read before the run's deadline"
UNIT_FAILURES = (httpx.HTTPError, VEuPathDBError, ToolError, pydantic.ValidationError)


REVOKED_AFTER = 3


def _next_link(exc: BaseException) -> BaseException | None:
    if exc.__cause__ is not None:
        return exc.__cause__
    return None if exc.__suppress_context__ else exc.__context__


def chained(exc: BaseException) -> list[BaseException]:
    links: list[BaseException] = []
    seen = {id(exc)}
    link = _next_link(exc)
    while link is not None and id(link) not in seen:
        links.append(link)
        seen.add(id(link))
        link = _next_link(link)
    return links


def _site_sentence(site_id: str, links: Sequence[BaseException]) -> str:
    answered = f"{site_id} answered {{}} to the audit reads"
    status: int | None = None
    for link in links:
        match link:
            case httpx.HTTPStatusError(response=response):
                return answered.format(response.status_code)
            case httpx.HTTPError():
                return f"{site_id} did not answer the audit reads"
            case DataParsingError() | ValidationError():
                pass
            case VEuPathDBError():
                status = status or site_status(link)
            case _:
                pass
    return _CHECK_FAILED if status is None else answered.format(status)


def _refusal_sentence(exc: VEuPathDBError[StrEnum]) -> str:
    kind = type(exc).__name__
    match exc:
        case ValidationError(__cause__=pydantic.ValidationError()):
            return f"{kind}: the site's values could not be read"
        case (
            ValidationError()
            | SiteNotFoundError()
            | WDKLoginRequiredError()
            | AppError()
        ):
            return f"{kind}: {exc}"
        case DataParsingError():
            return f"{kind}: the site's answer could not be read"
        case _:
            status = site_status(exc)
            answer = (
                f"answered {status}"
                if status is None or status >= SERVER_ERROR
                else f"refused with {status}"
            )
            return f"{kind}: the site {answer}"


def stored_failure(exc: BaseException, site_id: str) -> str:
    match exc:
        case ToolError():
            links = chained(exc)
            return _site_sentence(site_id, links) if links else str(exc)
        case VEuPathDBError():
            return _refusal_sentence(exc)
        case _:
            return f"{type(exc).__name__}: {sanitize_error_for_client(exc)}"


def failure_message(exc: BaseException, site_id: str) -> str:
    logger.warning(_UNIT_FAILED, exc_info=exc)
    return stored_failure(exc, site_id)


class SignInNeededError(Exception):
    def __init__(self) -> None:
        super().__init__(SIGN_IN_NEEDED)


class RefusalStreak:
    def __init__(
        self, site_id: str, run_id: UUID | None, count: int, *, reopened: bool
    ) -> None:
        self.site_id = site_id
        self.run_id = run_id
        self.count = count
        self.reopened = reopened

    async def _store(self, *, genuine: bool, unanswered: bool = False) -> None:
        if self.run_id is None:
            return
        run_id, count = self.run_id, self.count
        async with async_session_factory() as session:
            repo = AuditRepository(session)
            if genuine:
                await repo.clear_refusals(run_id)
            await repo.change_stages(
                run_id,
                lambda stages: stages.note_refusal_streak(
                    count
                ).note_sign_in_unanswered(unanswered=unanswered),
            )
            await session.commit()

    async def _ask_the_sign_in(self, waits: Waits) -> None:
        match await sign_in_check(self.site_id):
            case "held":
                self.count = 0
                await self._store(genuine=True)
            case "refused":
                await self._store(genuine=False)
                raise SignInNeededError
            case "unanswered":
                await self._store(genuine=False, unanswered=True)
                pause = waits.first_seconds
                if waits.clock.now() + timedelta(seconds=pause) < waits.deadline:
                    raise ContinueLaterError(
                        seconds=pause,
                        next_seconds=min(pause * 2, waits.longest_seconds),
                    )

    async def settled(self, before: int, *, answered: bool, waits: Waits) -> None:
        if self.count == before and answered:
            self.count = 0
        if self.count > before and (self.count >= REVOKED_AFTER or self.reopened):
            await self._ask_the_sign_in(waits)
        elif self.count != before:
            await self._store(genuine=False)


_STREAK: ContextVar[RefusalStreak | None] = ContextVar(
    "audit_refusal_streak", default=None
)


@contextmanager
def watching_refusals(
    site_id: str, run_id: UUID | None = None, count: int = 0, *, reopened: bool = False
) -> Iterator[RefusalStreak]:
    streak = RefusalStreak(site_id, run_id, count, reopened=reopened)
    reset = _STREAK.set(streak)
    try:
        yield streak
    finally:
        _STREAK.reset(reset)


def _note_forbidden() -> None:
    streak = _STREAK.get()
    if streak is None:
        return
    streak.count += 1


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
            return next(iter(chained(exc)), None)
        case _:
            return exc


def halt_when_signed_out(exc: BaseException) -> None:
    judged = _judged(exc)
    if signed_out(judged):
        raise SignInNeededError from exc
    if site_status(judged) == _FORBIDDEN:
        _note_forbidden()


def failure_status(exc: BaseException) -> Literal["failed", "unreached"]:
    halt_when_signed_out(exc)
    return "unreached" if unreached(_judged(exc)) else "failed"


class UnitFailure(CamelModel):
    model_config = pydantic.ConfigDict(frozen=True)

    status: Literal["failed", "unreached"]
    message: str
    refused: bool = False


def unit_failure(exc: BaseException, site_id: str) -> UnitFailure:
    return UnitFailure(
        status=failure_status(exc),
        message=failure_message(exc, site_id),
        refused=site_status(_judged(exc)) == _FORBIDDEN,
    )


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
        refused = 0 if streak is None else streak.count
        answered = await attempt(unit)
        if not answered:
            left.append(unit)
        if streak is not None:
            await streak.settled(refused, answered=answered, waits=waits)
    pause = waits.first_seconds
    if left and waits.clock.now() + timedelta(seconds=pause) < waits.deadline:
        await on_pause(pause, left)
        raise ContinueLaterError(
            seconds=pause, next_seconds=min(pause * 2, waits.longest_seconds)
        )
    return left
