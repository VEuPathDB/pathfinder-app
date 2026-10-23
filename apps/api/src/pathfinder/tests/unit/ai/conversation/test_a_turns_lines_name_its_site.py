from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from pathfinder.ai.conversation import turn_runner
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.tests._support.rendered_logs import rendered_logs


@dataclass
class _Writer:
    conversation_id: UUID = field(default_factory=uuid4)
    turn_id: UUID = field(default_factory=uuid4)

    async def write(self, chunk: dict[str, Any]) -> int:
        del chunk
        return 1


@dataclass(frozen=True)
class _Conversation:
    site_id: str = "toxodb"
    name: str = "named"


class _Spec:
    tool_sources: tuple[Any, ...] = ()
    assistant_id = "pathfinder"

    async def build_turn_context(self, request: object) -> object:
        del request
        return object()


def _spec() -> Any:
    return _Spec()


async def _thread(conversation_id: UUID) -> _Conversation:
    del conversation_id
    return _Conversation()


async def _logging_turn(**kwargs: Any) -> None:
    del kwargs
    logging.getLogger("pydantic_ai").warning("turn line")


async def test_a_turn_with_no_site_in_its_body_names_the_threads_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(turn_runner, "load_conversation", _thread)
    monkeypatch.setattr(turn_runner, "_run_turn_with_context", _logging_turn)
    writer = _Writer()

    with rendered_logs() as logs:
        await turn_runner.run_turn(
            request=turn_runner.TurnRequest(
                body=ChatRequestBody(conversation_id=writer.conversation_id),
                user_id=uuid4(),
            ),
            spec=_spec(),
            compiled_graph=None,
            memory_store=None,
            writer=writer,
        )
        logging.getLogger("pydantic_ai").warning("after the turn")

    assert logs.line("turn line")["site_id"] == "toxodb"
    assert "site_id" not in logs.line("after the turn")
