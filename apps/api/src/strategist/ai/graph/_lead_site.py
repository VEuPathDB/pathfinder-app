from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Iterator

from strategist.ai.graph._lead_capture import LeadRunCapture
from strategist.services.site_errors import SiteDidNotAnswerError, unanswered_site


@contextlib.contextmanager
def a_dead_site_changes_nothing() -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        site = unanswered_site(exc)
        if site is None:
            raise
        raise SiteDidNotAnswerError(site, changed_nothing=True) from exc


async def naming_a_dead_site[EventT](
    events: AsyncIterator[EventT], capture: LeadRunCapture
) -> AsyncIterator[EventT]:
    try:
        async for event in events:
            yield event
    except Exception as exc:
        capture.unanswered_site = unanswered_site(exc)
        if capture.unanswered_site is None:
            raise
        raise SiteDidNotAnswerError(
            capture.unanswered_site, changed_nothing=False
        ) from exc
