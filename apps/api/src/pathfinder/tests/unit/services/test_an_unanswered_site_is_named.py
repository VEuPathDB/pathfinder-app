from __future__ import annotations

import httpx

from pathfinder.services.site_errors import unanswered_site
from pathfinder.tests._support.site_failures import (
    failed_read,
    not_connected,
    refused,
    timed_out,
    unavailable,
)


async def test_a_503_names_the_site_that_answered_it() -> None:
    failure = await failed_read("plasmodb", unavailable)

    site = unanswered_site(failure)

    assert failure.status == 503
    assert site is not None
    assert site.name == "PlasmoDB"


async def test_a_timeout_names_the_site_it_was_waiting_on() -> None:
    site = unanswered_site(await failed_read("orthomcl", timed_out))

    assert site is not None
    assert site.name == "OrthoMCL"


async def test_a_connect_error_names_the_site_it_could_not_reach() -> None:
    failure = await failed_read("toxodb", not_connected)

    site = unanswered_site(failure)

    assert str(failure) == (
        "VEuPathDB service error: Request failed after retries: ConnectError"
    )
    assert failure.status == 502
    assert site is not None
    assert site.name == "ToxoDB"


async def test_a_refusal_is_an_answer_and_names_no_site() -> None:
    failure = await failed_read("plasmodb", refused)

    assert failure.status == 400
    assert unanswered_site(failure) is None


def test_an_error_with_no_site_behind_it_names_no_site() -> None:
    request = httpx.Request("GET", "https://api.openai.com/v1/responses")
    said = "plasmodb"
    errors: list[BaseException] = [
        httpx.ConnectError(said),
        httpx.ReadTimeout(said, request=request),
        RuntimeError(said),
        TimeoutError(),
    ]

    assert [unanswered_site(error) for error in errors] == [None, None, None, None]
