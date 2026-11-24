from __future__ import annotations

from strategist.services.site_errors import site_words
from strategist.tests._support.site_failures import failed_read, unavailable


async def test_a_server_error_after_retries_names_the_status_and_no_link() -> None:
    failure = await failed_read("plasmodb", unavailable)

    assert site_words(failure) == (
        "HTTP 503: VEuPathDB service error: Request failed after retries: "
        "Service Unavailable"
    )
