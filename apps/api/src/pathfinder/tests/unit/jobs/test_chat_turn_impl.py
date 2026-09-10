"""Worker boundary: run_chat_turn sets the ctxvar from the payload."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.context import DEFAULT_APPLICATION_ID, application_id_ctx
from assistant_core.spec import AssistantSpec
from assistant_core.tasks import scope
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.jobs.impls import chat_turn_impl
from pathfinder.jobs.impls.chat_turn_impl import run_chat_turn
from pathfinder.jobs.payloads import ChatTurnPayload

HOLDING_APPLICATION = "companion"


def _body() -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "conversationId": str(uuid4()),
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "hi"}],
                },
            ],
            "siteId": "plasmodb",
        },
    )


class _FakeGraph:
    async def ainvoke(self, *args: object, **kwargs: object) -> None:
        del args, kwargs


@asynccontextmanager
async def _fake_checkpointer_ctx(
    *args: object, **kwargs: object
) -> AsyncIterator[None]:
    del args, kwargs
    yield None


@asynccontextmanager
async def _fake_memory_ctx(*args: object, **kwargs: object) -> AsyncIterator[None]:
    del args, kwargs
    yield None


def _fake_build_graph(*args: object, **kwargs: object) -> _FakeGraph:
    del args, kwargs
    return _FakeGraph()


def _fake_resolve_assistant(registry: object, assistant_id: str) -> AssistantSpec:
    """The resolved spec, with only its graph factory replaced."""
    del registry
    real = build_pathfinder_spec()
    assert real.assistant_id == assistant_id
    return real.model_copy(update={"build_graph": _fake_build_graph})


class _ObservingRunTurn:
    """Records the ctxvar values at the moment run_turn is invoked."""

    def __init__(self) -> None:
        self.observed_token: str | object | None = _sentinel
        self.observed_application: str | None = None
        self.call_count = 0

    async def __call__(self, **kwargs: Any) -> None:
        del kwargs
        self.observed_token = veupathdb_auth_token_ctx.get()
        self.observed_application = application_id_ctx.get()
        self.call_count += 1


_sentinel = object()


async def _holding_application(conversation_id: UUID) -> str:
    del conversation_id
    return HOLDING_APPLICATION


@pytest.fixture(autouse=True)
def _conversation_application(monkeypatch: pytest.MonkeyPatch) -> None:
    """The row lookup the worker uses to name its application."""
    monkeypatch.setattr(scope, "conversation_application_id", _holding_application)


@pytest.mark.asyncio
async def test_run_chat_turn_sets_ctxvar_from_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = _ObservingRunTurn()
    monkeypatch.setattr(chat_turn_impl, "run_turn", observer)
    monkeypatch.setattr(
        chat_turn_impl,
        "lifespan_checkpointer",
        _fake_checkpointer_ctx,
    )
    monkeypatch.setattr(
        chat_turn_impl,
        "lifespan_memory_store",
        _fake_memory_ctx,
    )
    monkeypatch.setattr(chat_turn_impl, "resolve_assistant", _fake_resolve_assistant)

    payload = ChatTurnPayload(
        body=_body(),
        user_id=uuid4(),
        turn_id=uuid4(),
        veupathdb_auth_token="user-token-abc",
        assistant_id="pathfinder",
    )

    await run_chat_turn(payload.model_dump(mode="json", by_alias=True))

    assert observer.call_count == 1
    assert observer.observed_token == "user-token-abc"
    assert observer.observed_application == HOLDING_APPLICATION
    assert application_id_ctx.get() == DEFAULT_APPLICATION_ID


@pytest.mark.asyncio
async def test_run_chat_turn_resets_ctxvar_after_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = _ObservingRunTurn()
    monkeypatch.setattr(chat_turn_impl, "run_turn", observer)
    monkeypatch.setattr(
        chat_turn_impl,
        "lifespan_checkpointer",
        _fake_checkpointer_ctx,
    )
    monkeypatch.setattr(
        chat_turn_impl,
        "lifespan_memory_store",
        _fake_memory_ctx,
    )
    monkeypatch.setattr(chat_turn_impl, "resolve_assistant", _fake_resolve_assistant)

    assert veupathdb_auth_token_ctx.get() is None
    payload = ChatTurnPayload(
        body=_body(),
        user_id=uuid4(),
        turn_id=uuid4(),
        veupathdb_auth_token="user-token-xyz",
        assistant_id="pathfinder",
    )
    await run_chat_turn(payload.model_dump(mode="json", by_alias=True))
    assert veupathdb_auth_token_ctx.get() is None


@pytest.mark.asyncio
async def test_run_chat_turn_tolerates_missing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An anonymous caller (no cookie) dispatches with token=None. The
    worker still runs — WDK calls fall through to settings (service)."""
    observer = _ObservingRunTurn()
    monkeypatch.setattr(chat_turn_impl, "run_turn", observer)
    monkeypatch.setattr(
        chat_turn_impl,
        "lifespan_checkpointer",
        _fake_checkpointer_ctx,
    )
    monkeypatch.setattr(
        chat_turn_impl,
        "lifespan_memory_store",
        _fake_memory_ctx,
    )
    monkeypatch.setattr(chat_turn_impl, "resolve_assistant", _fake_resolve_assistant)

    payload = ChatTurnPayload(
        body=_body(),
        user_id=uuid4(),
        turn_id=uuid4(),
        assistant_id="pathfinder",
    )
    await run_chat_turn(payload.model_dump(mode="json", by_alias=True))

    assert observer.observed_token is None
