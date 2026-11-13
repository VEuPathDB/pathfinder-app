"""A structured output Anthropic refuses as too large to compile is asked for again as prompted JSON."""

from __future__ import annotations

import json

import pytest
from assistant_core.models.settings import build_model_settings
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models import Model

from strategist.domain.provider_keys import ProviderKeyring
from strategist.platform.config import get_settings
from strategist.platform.model_keys import attach_keyring, keyed_model
from strategist.tests._support.provider_wire import (
    ProviderWire,
    allow_requests_to_the_wire,
)

_HAIKU = "anthropic:claude-haiku-5-5"
_TOO_LARGE = (
    400,
    {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": (
                "The compiled grammar is too large, which would cause performance "
                "issues. Simplify your tool schemas or reduce the number of strict tools."
            ),
        },
    },
)
_OTHER = (
    400,
    {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "messages: at least one"},
    },
)


class _Reading(BaseModel):
    kind: str


@pytest.fixture(autouse=True)
def _wire(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_requests_to_the_wire(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "strategist_chat_provider", "default")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-0000")


def _agent(model: Model) -> Agent[None, _Reading]:
    return Agent(
        model,
        output_type=_Reading,
        model_settings=build_model_settings(_HAIKU, thinking="medium"),
    )


class _Sent(BaseModel):
    output_config: dict[str, object] = {}


def _formats(wire: ProviderWire) -> list[bool]:
    return [
        "format" in _Sent.model_validate(json.loads(request.content)).output_config
        for request in wire.requests
    ]


async def test_a_refused_request_is_asked_again_as_prompted_json() -> None:
    wire = ProviderWire(answers=[_TOO_LARGE], anthropic_text='{"kind": "greeting"}')

    with attach_keyring(ProviderKeyring(), build=wire.build):
        model = keyed_model(_HAIKU)
        assert isinstance(model, Model)
        output = (await _agent(model).run("hi")).output

    assert output == _Reading(kind="greeting")
    assert _formats(wire) == [True, False]


async def test_a_refused_stream_is_asked_again_as_prompted_json() -> None:
    wire = ProviderWire(answers=[_TOO_LARGE], anthropic_text='{"kind": "greeting"}')

    with attach_keyring(ProviderKeyring(), build=wire.build):
        model = keyed_model(_HAIKU)
        assert isinstance(model, Model)
        async with _agent(model).run_stream("hi") as streamed:
            output = await streamed.get_output()

    assert output == _Reading(kind="greeting")
    assert _formats(wire) == [True, False]


async def test_another_rejection_is_not_asked_again() -> None:
    wire = ProviderWire(answers=[_OTHER], anthropic_text='{"kind": "greeting"}')

    with attach_keyring(ProviderKeyring(), build=wire.build):
        model = keyed_model(_HAIKU)
        assert isinstance(model, Model)
        with pytest.raises(ModelHTTPError):
            await _agent(model).run("hi")

    assert len(wire.requests) == 1
