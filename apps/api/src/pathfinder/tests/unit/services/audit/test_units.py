"""A pass reads its units until the deadline or the end of its slice, then asks to continue after a growing pause."""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from fastmcp.exceptions import ToolError
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import (
    DataParsingError,
    ExternalServiceError,
    WDKError,
    WDKLoginRequiredError,
)
from veupathdb.jbrowse import JBrowseError

from pathfinder.services.audit import units
from pathfinder.services.audit.units import (
    FIRST_WAIT_SECONDS,
    LONGEST_WAIT_SECONDS,
    SIGN_IN_NEEDED,
    ContinueLaterError,
    SignInNeededError,
    Waits,
    failure_status,
    in_passes,
    unreached,
    waits_until,
    watching_refusals,
)
from pathfinder.tests._support.audit import FakeClock
from pathfinder.tests._support.veupathdb_tokens import (
    SUBJECT,
    make_signing_key,
    veupathdb_token,
)

START = datetime(2026, 10, 21, 12, tzinfo=UTC)
READS_IN_SIX_HOURS = 179
_URL = "https://qa.plasmodb.org/plasmo.qa/service/"


def _answered(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", _URL)
    return httpx.HTTPStatusError(
        f"answered {status}",
        request=request,
        response=httpx.Response(status, request=request),
    )


def _caused(cause: BaseException) -> ToolError:
    error = ToolError("plasmodb did not answer the audit reads")
    error.__cause__ = cause
    return error


def test_a_transport_failure_a_server_error_and_a_failing_store_are_unreached() -> None:
    assert unreached(httpx.ConnectError("connection refused")) is True
    assert unreached(WDKError("upstream failed", status=502)) is True
    assert unreached(JBrowseError("GET", "https://qa.plasmodb.org/x", 503)) is True


def test_a_refusal_a_parse_failure_and_a_missing_cause_are_not_unreached() -> None:
    assert unreached(WDKError("organism not found", status=422)) is False
    assert (
        unreached(DataParsingError("the gene record gives no readable Orthologs"))
        is False
    )
    assert unreached(JBrowseError("GET", "https://qa.plasmodb.org/x", 200)) is False
    assert unreached(None) is False


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_caused(httpx.ConnectError("refused")), "unreached"),
        (_caused(DataParsingError("bad table")), "failed"),
        (ToolError("NOT_A_GENE names no gene of plasmodb"), "failed"),
        (httpx.ReadTimeout("slow"), "unreached"),
        (DataParsingError("bad table"), "failed"),
        (_caused(JBrowseError("GET", _URL, 503)), "unreached"),
        (_caused(JBrowseError("GET", _URL, 404)), "failed"),
        (_caused(WDKError("organism not found", status=422)), "failed"),
        (_caused(WDKError("upstream failed", status=504)), "unreached"),
        (ExternalServiceError("blast", "upstream failed", status=503), "unreached"),
        (ExternalServiceError("blast", "no such job", status=404), "failed"),
        (_answered(503), "unreached"),
        (_answered(404), "failed"),
        (httpx.DecodingError("not gzip"), "failed"),
        (httpx.TooManyRedirects("loop"), "failed"),
    ],
)
def test_a_tool_error_is_judged_by_its_cause(
    error: BaseException, expected: str
) -> None:
    assert failure_status(error) == expected


def _waits(
    clock: FakeClock,
    *,
    deadline: float,
    slice_seconds: float = 3600 * 24,
    first: float = 10,
    longest: float = 40,
) -> Waits:
    return Waits(
        deadline=START + timedelta(seconds=deadline),
        slice_ends=START + timedelta(seconds=slice_seconds),
        first_seconds=first,
        longest_seconds=longest,
        clock=clock,
    )


async def _quiet(seconds: float, left: Sequence[str]) -> None:
    del seconds, left


class _Unread:
    def __init__(self) -> None:
        self.units: list[str] = []

    async def __call__(self, left: Sequence[str]) -> None:
        self.units.extend(left)


async def test_a_pass_reads_every_unit_then_asks_to_continue_after_a_pause() -> None:
    clock = FakeClock(START)
    tries: list[str] = []
    pauses: list[tuple[float, list[str]]] = []
    unread = _Unread()

    async def attempt(unit: str) -> bool:
        tries.append(unit)
        return unit == "a"

    async def pausing(seconds: float, left: Sequence[str]) -> None:
        pauses.append((seconds, list(left)))

    with pytest.raises(ContinueLaterError) as later:
        await in_passes(
            ["a", "b", "c"],
            attempt,
            _waits(clock, deadline=100),
            unread=unread,
            on_pause=pausing,
        )
    assert (later.value.seconds, later.value.next_seconds) == (10, 20)
    assert (tries, pauses, unread.units) == (["a", "b", "c"], [(10, ["b", "c"])], [])


@pytest.mark.parametrize(
    ("first", "longest", "expected"), [(10, 40, 20), (40, 40, 40), (240, 400, 400)]
)
async def test_the_next_pause_doubles_up_to_the_longest(
    first: float, longest: float, expected: float
) -> None:
    async def attempt(unit: str) -> bool:
        del unit
        return False

    waits = _waits(FakeClock(START), deadline=3600, first=first, longest=longest)
    with pytest.raises(ContinueLaterError) as later:
        await in_passes(["a"], attempt, waits, unread=_Unread(), on_pause=_quiet)
    assert later.value.next_seconds == expected


async def test_a_pass_starts_no_read_once_the_deadline_has_passed() -> None:
    clock = FakeClock(START)
    tries: list[str] = []
    unread = _Unread()

    async def attempt(unit: str) -> bool:
        tries.append(unit)
        await clock.sleep(20)
        return False

    left = await in_passes(
        ["a", "b", "c", "d"],
        attempt,
        _waits(clock, deadline=50),
        unread=unread,
        on_pause=_quiet,
    )
    assert (tries, unread.units, left) == (["a", "b", "c"], ["d"], ["a", "b", "c", "d"])
    assert clock.at == START + timedelta(seconds=60)


async def test_a_continuation_started_past_the_deadline_reads_nothing() -> None:
    clock = FakeClock(START + timedelta(seconds=1))
    unread = _Unread()

    async def attempt(unit: str) -> bool:
        raise AssertionError(unit)

    left = await in_passes(
        ["a", "b"], attempt, _waits(clock, deadline=0), unread=unread, on_pause=_quiet
    )
    assert (left, unread.units) == (["a", "b"], ["a", "b"])


async def test_a_pause_that_would_end_past_the_deadline_ends_the_stage() -> None:
    async def attempt(unit: str) -> bool:
        del unit
        return False

    waits = _waits(FakeClock(START), deadline=20, first=30)
    assert await in_passes(
        ["a"], attempt, waits, unread=_Unread(), on_pause=_quiet
    ) == ["a"]


async def test_a_pass_yields_its_slot_at_the_end_of_its_slice() -> None:
    clock = FakeClock(START)
    tries: list[str] = []
    unread = _Unread()

    async def attempt(unit: str) -> bool:
        tries.append(unit)
        await clock.sleep(20)
        return True

    waits = _waits(clock, deadline=3600, slice_seconds=30, first=60)
    with pytest.raises(ContinueLaterError) as later:
        await in_passes(["a", "b", "c"], attempt, waits, unread=unread, on_pause=_quiet)
    assert (later.value.seconds, later.value.next_seconds) == (0.0, 60)
    assert (tries, unread.units) == (["a", "b"], [])


async def test_slow_unanswered_reads_overrun_the_deadline_by_at_most_one_read() -> None:
    clock = FakeClock(START)
    genomes = [f"genome{k}" for k in range(48)]
    reads: list[str] = []
    unread = _Unread()

    async def attempt(unit: str) -> bool:
        reads.append(unit)
        await clock.sleep(120)
        return False

    deadline = START + timedelta(hours=6)
    waits = Waits(
        deadline=deadline,
        slice_ends=deadline,
        first_seconds=FIRST_WAIT_SECONDS,
        longest_seconds=LONGEST_WAIT_SECONDS,
        clock=clock,
    )
    while True:
        try:
            left = await in_passes(
                genomes, attempt, waits, unread=unread, on_pause=_quiet
            )
        except ContinueLaterError as later:
            await clock.sleep(later.seconds)
            waits = Waits(
                deadline=deadline,
                slice_ends=deadline,
                first_seconds=later.next_seconds,
                longest_seconds=LONGEST_WAIT_SECONDS,
                clock=clock,
            )
        else:
            break
    assert left == genomes
    assert len(reads) == READS_IN_SIX_HOURS
    assert unread.units == genomes[READS_IN_SIX_HOURS % 48 :]
    assert deadline <= clock.at <= deadline + timedelta(seconds=120)


async def test_no_pause_is_taken_once_every_unit_answered() -> None:
    async def attempt(unit: str) -> bool:
        del unit
        return True

    waits = _waits(FakeClock(START), deadline=3600)
    assert (
        await in_passes(["a", "b"], attempt, waits, unread=_Unread(), on_pause=_quiet)
        == []
    )


def test_the_waits_of_a_job_carry_its_pause_and_a_thirty_minute_slice() -> None:
    before = datetime.now(UTC)
    waits = waits_until(START, first_seconds=120.0)
    assert (waits.deadline, waits.first_seconds, waits.longest_seconds) == (
        START,
        120.0,
        900.0,
    )
    assert (units.FIRST_WAIT_SECONDS, units.SLICE_SECONDS) == (30.0, 1800.0)
    assert before + timedelta(minutes=30) <= waits.slice_ends
    assert waits.slice_ends <= datetime.now(UTC) + timedelta(minutes=30)


@pytest.mark.parametrize(
    "error",
    [
        _caused(WDKError("GET /record-types -> HTTP 401: expired", status=401)),
        WDKLoginRequiredError(),
        _answered(401),
        _caused(JBrowseError("GET", _URL, 401)),
        ExternalServiceError("blast", "token expired", status=401),
        _caused(WDKError("GET /record-types -> HTTP 403: forbidden", status=403)),
        _caused(JBrowseError("GET", _URL, 403)),
        _answered(403),
    ],
)
def test_a_read_refused_for_its_sign_in_halts_instead_of_settling(
    error: BaseException,
) -> None:
    with pytest.raises(SignInNeededError) as halted:
        failure_status(error)
    assert str(halted.value) == SIGN_IN_NEEDED == "sign-in needed"
    assert halted.value.__cause__ is error


_KEY = make_signing_key()


def _expired() -> str:
    return jwt.encode(
        {"sub": SUBJECT, "is_guest": False, "exp": int(time.time()) - 60},
        _KEY,
        algorithm="ES512",
    )


@pytest.mark.parametrize(
    "error",
    [
        _caused(WDKError("GET /record-types -> HTTP 403: forbidden", status=403)),
        _caused(JBrowseError("GET", _URL, 403)),
        _answered(403),
    ],
)
def test_a_forbidden_read_on_a_sign_in_that_still_holds_is_a_failed_unit(
    error: BaseException,
) -> None:
    held = veupathdb_auth_token_ctx.set(veupathdb_token(_KEY))
    try:
        assert failure_status(error) == "failed"
    finally:
        veupathdb_auth_token_ctx.reset(held)


@pytest.mark.parametrize(
    "token", ["not-a-token", veupathdb_token(_KEY, is_guest=True), _expired()]
)
def test_a_forbidden_read_on_a_lapsed_or_unreadable_sign_in_halts(token: str) -> None:
    held = veupathdb_auth_token_ctx.set(token)
    try:
        with pytest.raises(SignInNeededError):
            failure_status(_answered(403))
    finally:
        veupathdb_auth_token_ctx.reset(held)


def test_an_unauthorized_read_halts_even_on_a_sign_in_that_holds() -> None:
    held = veupathdb_auth_token_ctx.set(veupathdb_token(_KEY))
    try:
        with pytest.raises(SignInNeededError):
            failure_status(_answered(401))
    finally:
        veupathdb_auth_token_ctx.reset(held)


def test_three_forbidden_reads_in_a_row_on_a_valid_sign_in_halt_as_revoked() -> None:
    held = veupathdb_auth_token_ctx.set(veupathdb_token(_KEY))
    try:
        with watching_refusals():
            assert failure_status(_answered(403)) == "failed"
            assert failure_status(_answered(403)) == "failed"
            with pytest.raises(SignInNeededError) as revoked:
                failure_status(_answered(403))
    finally:
        veupathdb_auth_token_ctx.reset(held)
    assert revoked.value.forbidden == (str(_answered(403)),) * 3


async def test_an_answered_unit_between_forbidden_reads_breaks_the_streak() -> None:
    held = veupathdb_auth_token_ctx.set(veupathdb_token(_KEY))
    outcomes = iter([False, False, True, False, False])

    async def attempt(unit: str) -> bool:
        del unit
        if next(outcomes):
            return True
        assert failure_status(_answered(403)) == "failed"
        return True

    try:
        with watching_refusals():
            left = await in_passes(
                ["a", "b", "c", "d", "e"],
                attempt,
                _waits(FakeClock(START), deadline=3600),
                unread=_Unread(),
                on_pause=_quiet,
            )
    finally:
        veupathdb_auth_token_ctx.reset(held)
    assert left == []
