from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from strategist.ai.conversation import turn_stop
from strategist.tests._support.logs import logged_events


async def test_a_poll_that_fails_ends_the_watch_and_cancels_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    polled: list[UUID] = []

    async def unreachable(*, conversation_id: UUID, turn_id: UUID) -> bool:
        polled.append(turn_id)
        del conversation_id
        msg = "the database went away"
        raise OSError(msg)

    monkeypatch.setattr(turn_stop, "turn_is_cancelled", unreachable)
    cancel = asyncio.Event()
    turn = uuid4()

    await turn_stop.watch_for_cancel(
        conversation_id=uuid4(), turn_id=turn, cancel_event=cancel
    )

    assert (polled, cancel.is_set()) == ([turn], False)
    assert logged_events(caplog.records, logger=turn_stop.__name__) == [
        "Cancel watcher poll failed"
    ]
