from __future__ import annotations

import httpx
from veupathdb.errors import WDKError

from pathfinder.services.site_errors import answered_with_a_status

_URL = "https://qa.plasmodb.org/plasmo.qa/service/users/1/steps/1/reports/standard"


def _after(cause: Exception, status: int) -> WDKError:
    failed = WDKError(f"Request failed after retries: {cause}", status=status)
    failed.__cause__ = cause
    return failed


def test_a_status_the_site_sent_is_an_answer() -> None:
    request = httpx.Request("POST", _URL)
    response = httpx.Response(500, text="Internal Error", request=request)
    sent = httpx.HTTPStatusError("Internal Error", request=request, response=response)

    assert answered_with_a_status(_after(sent, 500)) is True


def test_a_transport_failure_a_timeout_and_no_cause_are_no_answer() -> None:
    assert answered_with_a_status(_after(httpx.ConnectError("refused"), 502)) is False
    assert answered_with_a_status(_after(httpx.ReadTimeout("slow"), 502)) is False
    assert answered_with_a_status(WDKError("upstream failed", status=502)) is False
    assert answered_with_a_status(TimeoutError()) is False
    assert answered_with_a_status(None) is False
