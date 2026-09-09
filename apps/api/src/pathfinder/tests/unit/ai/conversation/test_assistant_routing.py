"""Which assistant a turn runs under, and what a mismatch does."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from pathfinder.ai.conversation import assistant_routing
from pathfinder.ai.conversation.assistant_routing import (
    resolve_assistant,
    resolve_turn_assistant,
)
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.platform.errors import (
    AssistantMismatchError,
    AssistantNotFoundError,
    ErrorCode,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


def _body(**extra: object) -> ChatRequestBody:
    payload: dict[str, object] = {
        "conversationId": str(uuid4()),
        "siteId": "plasmodb",
        "messages": [
            {
                "id": str(uuid4()),
                "role": "user",
                "parts": [{"type": "text", "text": "hi"}],
            },
        ],
    }
    payload.update(extra)
    return ChatRequestBody.model_validate(payload)


def _install_existing(
    monkeypatch: pytest.MonkeyPatch,
    assistant_id: str | None,
) -> None:
    async def _read(_conversation_id: UUID) -> str | None:
        return assistant_id

    monkeypatch.setattr(assistant_routing, "conversation_assistant_id", _read)


def test_the_body_carries_no_assistant_by_default() -> None:
    assert _body().assistant_id is None


def test_the_body_parses_a_camel_case_assistant_id() -> None:
    assert _body(assistantId="pathfinder").assistant_id == "pathfinder"


def test_the_registry_default_resolves_to_a_spec() -> None:
    """A turn that names no assistant runs the one the registry defaults to."""
    registry = get_assistant_registry()

    assert registry.default_id == PATHFINDER_ASSISTANT_ID
    assert registry.resolve(PATHFINDER_ASSISTANT_ID) is not None


def test_an_unknown_id_is_a_404_shaped_refusal() -> None:
    with pytest.raises(AssistantNotFoundError) as raised:
        resolve_assistant(get_assistant_registry(), "no_such_assistant")

    assert raised.value.status == 404
    assert raised.value.code == ErrorCode.ASSISTANT_NOT_FOUND


async def test_a_new_conversation_takes_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_existing(monkeypatch, None)

    spec = await resolve_turn_assistant(
        registry=get_assistant_registry(),
        conversation_id=uuid4(),
        requested_id=None,
    )

    assert spec.assistant_id == PATHFINDER_ASSISTANT_ID


async def test_a_new_conversation_takes_the_requested_assistant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_existing(monkeypatch, None)

    spec = await resolve_turn_assistant(
        registry=get_assistant_registry(),
        conversation_id=uuid4(),
        requested_id="pathfinder",
    )

    assert spec.assistant_id == "pathfinder"


async def test_a_new_conversation_naming_an_unknown_assistant_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_existing(monkeypatch, None)

    with pytest.raises(AssistantNotFoundError):
        await resolve_turn_assistant(
            registry=get_assistant_registry(),
            conversation_id=uuid4(),
            requested_id="no_such_assistant",
        )


async def test_an_existing_conversation_keeps_its_assistant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A silent request inherits the thread's assistant, not the default."""
    _install_existing(monkeypatch, "pathfinder")

    spec = await resolve_turn_assistant(
        registry=get_assistant_registry(),
        conversation_id=uuid4(),
        requested_id=None,
    )

    assert spec.assistant_id == "pathfinder"


async def test_naming_another_assistant_on_an_existing_thread_is_a_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The thread never changes assistant, so the caller is answered loudly."""
    _install_existing(monkeypatch, "pathfinder")

    with pytest.raises(AssistantMismatchError) as raised:
        await resolve_turn_assistant(
            registry=get_assistant_registry(),
            conversation_id=uuid4(),
            requested_id="site_help",
        )

    assert raised.value.status == 409
    assert raised.value.code == ErrorCode.ASSISTANT_MISMATCH
    assert "site_help" in (raised.value.detail or "")


async def test_naming_the_same_assistant_on_an_existing_thread_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_existing(monkeypatch, "pathfinder")

    spec = await resolve_turn_assistant(
        registry=get_assistant_registry(),
        conversation_id=uuid4(),
        requested_id="pathfinder",
    )

    assert spec.assistant_id == "pathfinder"


async def test_a_thread_that_does_not_exist_yet_takes_the_default() -> None:
    """The open route resolves before the row exists, so it reads no row."""
    spec = await resolve_turn_assistant(
        registry=get_assistant_registry(),
        conversation_id=None,
        requested_id=None,
    )

    assert spec.assistant_id == PATHFINDER_ASSISTANT_ID


async def test_a_thread_that_does_not_exist_yet_takes_the_requested_assistant() -> None:
    spec = await resolve_turn_assistant(
        registry=get_assistant_registry(),
        conversation_id=None,
        requested_id="site_help",
    )

    assert spec.assistant_id == "site_help"


async def test_a_thread_that_does_not_exist_yet_refuses_an_unknown_assistant() -> None:
    with pytest.raises(AssistantNotFoundError) as raised:
        await resolve_turn_assistant(
            registry=get_assistant_registry(),
            conversation_id=None,
            requested_id="no_such_assistant",
        )

    assert raised.value.status == 404
    assert raised.value.code == ErrorCode.ASSISTANT_NOT_FOUND
