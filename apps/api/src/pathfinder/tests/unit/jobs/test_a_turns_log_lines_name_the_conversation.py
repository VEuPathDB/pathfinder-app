from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.logging import get_logger
from assistant_core.spec import AssistantSpec
from assistant_core.tasks import scope

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.domain.provider_keys import KeyableProvider, KeyRefusal, ProviderKeyring
from pathfinder.jobs import turn_keys
from pathfinder.jobs.impls import chat_turn_impl
from pathfinder.jobs.payloads import ChatTurnPayload
from pathfinder.tests._support.rendered_logs import rendered_logs

_KEYS = ("conversation_id", "turn_id", "user_id", "site_id", "assistant_id")


@asynccontextmanager
async def _opened(*args: object, **kwargs: object) -> AsyncIterator[None]:
    del args, kwargs
    yield None


class _Registry:
    def resolve(self, assistant_id: str) -> AssistantSpec:
        real = build_pathfinder_spec()
        assert real.assistant_id == assistant_id
        return real.model_copy(update={"build_graph": lambda *_a, **_k: None})

    def checkpoint_types(self) -> tuple[type, ...]:
        return get_assistant_registry().checkpoint_types()


async def _logging_turn(**kwargs: Any) -> None:
    del kwargs
    get_logger("pathfinder.probe").info("turn line")
    logging.getLogger("httpx").warning("library turn line")


async def _application(conversation_id: UUID) -> str:
    del conversation_id
    return "pathfinder"


async def _no_keys(user_id: UUID) -> ProviderKeyring:
    del user_id
    return ProviderKeyring()


async def _no_refusals(
    user_id: UUID, refusals: dict[KeyableProvider, KeyRefusal]
) -> None:
    del user_id, refusals


@pytest.fixture(autouse=True)
def _turn_without_io(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scope, "conversation_application_id", _application)
    monkeypatch.setattr(turn_keys, "load_keyring", _no_keys)
    monkeypatch.setattr(turn_keys, "record_refusals", _no_refusals)
    monkeypatch.setattr(chat_turn_impl, "run_turn", _logging_turn)
    monkeypatch.setattr(chat_turn_impl, "lifespan_checkpointer", _opened)
    monkeypatch.setattr(chat_turn_impl, "lifespan_memory_store", _opened)
    monkeypatch.setattr(chat_turn_impl, "get_assistant_registry", _Registry)


def _payload() -> ChatTurnPayload:
    return ChatTurnPayload(
        body=ChatRequestBody.model_validate(
            {"conversationId": str(uuid4()), "siteId": "plasmodb"}
        ),
        user_id=uuid4(),
        turn_id=uuid4(),
        assistant_id="pathfinder",
    )


async def test_every_line_of_a_turn_names_the_turn_the_user_the_site_and_the_assistant() -> (
    None
):
    payload = _payload()

    with rendered_logs() as logs:
        await chat_turn_impl.run_chat_turn(payload.model_dump(mode="json"))
        logging.getLogger("httpx").warning("after the turn")

    expected = {
        "conversation_id": str(payload.body.conversation_id),
        "turn_id": str(payload.turn_id),
        "user_id": str(payload.user_id),
        "site_id": "plasmodb",
        "assistant_id": "pathfinder",
    }
    for event in ("turn line", "library turn line", "chat turn completed"):
        line = logs.line(event)
        assert {key: line[key] for key in _KEYS} == expected
    assert set(_KEYS) & set(logs.line("after the turn")) == set()


async def test_a_second_turn_names_its_own_ids_alone() -> None:
    first, second = _payload(), _payload()

    with rendered_logs() as logs:
        await chat_turn_impl.run_chat_turn(first.model_dump(mode="json"))
        await chat_turn_impl.run_chat_turn(second.model_dump(mode="json"))

    turns = [line["turn_id"] for line in logs.lines() if line["event"] == "turn line"]
    assert turns == [str(first.turn_id), str(second.turn_id)]
