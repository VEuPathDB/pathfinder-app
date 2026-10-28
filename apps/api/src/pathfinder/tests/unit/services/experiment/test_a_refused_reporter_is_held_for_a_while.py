from __future__ import annotations

import httpx
from veupathdb.errors import WDKError

from pathfinder.services.experiment.reporter_refusals import (
    REFUSAL_LIFETIME_SECONDS,
    ReporterRefusal,
    ReporterRefusals,
)

_STEP = "https://qa.plasmodb.org/plasmo.qa/service/users/1/steps/441126163"


def _status(url: str, status: int) -> WDKError:
    request = httpx.Request("POST", url)
    response = httpx.Response(status, text="Internal Error", request=request)
    failed = WDKError("Request failed after retries", status=status)
    failed.__cause__ = httpx.HTTPStatusError(
        "Internal Error", request=request, response=response
    )
    return failed


class _Clock:
    now = 50.0

    def __call__(self) -> float:
        return self.now


def test_a_server_error_from_the_reporter_is_held_until_it_lapses() -> None:
    clock = _Clock()
    held = ReporterRefusals(clock=clock)

    refusal = held.refused(
        "plasmodb", "byValue", _status(f"{_STEP}/columns/organism/reports/byValue", 500)
    )
    clock.now += REFUSAL_LIFETIME_SECONDS - 1
    still = held.held("plasmodb", "byValue")
    other_site = held.held("toxodb", "byValue")
    clock.now += 1

    assert refusal == ReporterRefusal(
        site_id="plasmodb",
        reporter="byValue",
        status=500,
        until=50.0 + REFUSAL_LIFETIME_SECONDS,
    )
    assert (still, other_site, held.held("plasmodb", "byValue")) == (
        refusal,
        None,
        None,
    )


def test_a_refusal_of_one_column_another_read_or_no_answer_is_not_held() -> None:
    held = ReporterRefusals(clock=_Clock())
    unanswered = WDKError("Request failed after retries", status=502)
    unanswered.__cause__ = httpx.ConnectError("connection refused")

    refused = [
        held.refused("plasmodb", "byValue", error)
        for error in (
            _status(f"{_STEP}/columns/organism/reports/byValue", 422),
            _status(_STEP, 500),
            unanswered,
        )
    ]

    assert (refused, held.held("plasmodb", "byValue")) == ([None, None, None], None)
