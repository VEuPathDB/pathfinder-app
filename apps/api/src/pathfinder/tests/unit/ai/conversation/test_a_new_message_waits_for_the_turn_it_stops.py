"""A new message stops the thread's running turn and waits for it to close
before the message is logged, so the log never interleaves two turns."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.errors import ConversationNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.conversation import dispatcher
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.tests._support.second_assistant import build_helper_spec

_SPEC = build_helper_spec()


class _Messages:
    def __init__(self, session: object) -> None:
        del session

    async def insert_message(self, **_: object) -> None:
        return None


class _Writer:
    def __init__(self, **_: object) -> None:
        return None

    async def write(self, chunk: dict[str, Any]) -> int:
        del chunk
        return 1


def _body(conversation_id: UUID) -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "id": str(conversation_id),
            "trigger": "submit-message",
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "/clear"}],
                },
            ],
            "conversationId": str(conversation_id),
            "siteId": "plasmodb",
        },
    )


@pytest.fixture
def order(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    closed: set[UUID] = set()

    async def stop_and_wait(conversation_ids: Sequence[UUID]) -> list[UUID]:
        calls.append("stop")
        closed.update(conversation_ids)
        return []

    async def append(*, conversation_id: UUID, **_: object) -> None:
        calls.append("logged" if conversation_id in closed else "logged-while-open")

    async def boundary(conversation_id: UUID) -> int:
        calls.append("boundary" if conversation_id in closed else "boundary-while-open")
        return 7

    async def nothing(*_: object, **__: object) -> None:
        return None

    async def deferred(**_: object) -> int:
        calls.append("deferred")
        return 1

    @asynccontextmanager
    async def held(conversation_id: UUID) -> AsyncIterator[None]:
        del conversation_id
        calls.append("held")
        yield
        calls.append("released")

    async def owned(*_: object, **__: object) -> None:
        calls.append("owned")

    async def begun(**_: object) -> SimpleNamespace:
        return SimpleNamespace(
            conversation=SimpleNamespace(assistant_id=_SPEC.assistant_id), is_new=False
        )

    monkeypatch.setattr(dispatcher, "stop_turns_and_wait", stop_and_wait)
    monkeypatch.setattr(dispatcher, "append_user_message_once", append)
    monkeypatch.setattr(dispatcher, "latest_turn_boundary", boundary)
    monkeypatch.setattr(dispatcher, "require_a_free_turn", nothing)
    monkeypatch.setattr(dispatcher, "scan_user_input", nothing)
    monkeypatch.setattr(dispatcher, "defer_chat_turn", deferred)
    monkeypatch.setattr(dispatcher, "hold_thread", held)
    monkeypatch.setattr(dispatcher, "refuse_a_thread_of_another_caller", owned)
    monkeypatch.setattr(dispatcher, "begin_conversation", begun)
    monkeypatch.setattr(dispatcher, "MessagesRepository", _Messages)
    monkeypatch.setattr(dispatcher, "ChatEventWriter", _Writer)
    monkeypatch.setattr(dispatcher, "event_tail", lambda *_, **__: None)
    return calls


async def test_the_running_turn_closes_before_the_new_message_is_logged(
    order: list[str],
) -> None:
    await dispatcher.dispatch(
        body=_body(uuid4()),
        session=AsyncSession(),
        user_id=uuid4(),
        spec=_SPEC,
    )

    assert order == [
        "owned",
        "held",
        "stop",
        "logged",
        "boundary",
        "deferred",
        "released",
    ]


async def test_a_thread_of_another_caller_is_refused_before_the_lock(
    order: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()

    async def foreign(*_: object, **__: object) -> None:
        raise ConversationNotFoundError(conversation_id)

    monkeypatch.setattr(dispatcher, "refuse_a_thread_of_another_caller", foreign)

    with pytest.raises(ConversationNotFoundError):
        await dispatcher.dispatch(
            body=_body(conversation_id),
            session=AsyncSession(),
            user_id=uuid4(),
            spec=_SPEC,
        )

    assert order == []
