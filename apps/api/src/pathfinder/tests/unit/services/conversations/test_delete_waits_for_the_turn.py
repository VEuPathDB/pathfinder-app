"""A conversation is removed only after its running turn has closed."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from pathfinder.platform.errors import ErrorCode, TurnStillRunningError
from pathfinder.services.conversations import cancellation


async def test_a_thread_whose_worker_closed_is_released_for_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[Sequence[UUID]] = []

    async def stopped(ids: Sequence[UUID], *, timeout_seconds: float = 0) -> list[UUID]:
        asked.append(ids)
        return []

    monkeypatch.setattr(cancellation, "stop_turns_and_wait", stopped)
    conversation_id = uuid4()

    await cancellation.stop_turn_before_delete(conversation_id)

    assert asked == [[conversation_id]]


async def test_a_thread_whose_worker_keeps_writing_is_not_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()

    async def still_running(
        ids: Sequence[UUID], *, timeout_seconds: float = 0
    ) -> list[UUID]:
        return list(ids)

    monkeypatch.setattr(cancellation, "stop_turns_and_wait", still_running)

    with pytest.raises(TurnStillRunningError) as caught:
        await cancellation.stop_turn_before_delete(conversation_id)

    assert caught.value.status == 409
    assert caught.value.code == ErrorCode.SESSION_CONFLICT
    assert str(conversation_id) in (caught.value.detail or "")
