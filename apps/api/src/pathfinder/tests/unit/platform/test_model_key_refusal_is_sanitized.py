"""A provider's refusal reaches the turn as a status or a sentence, never its body."""

from __future__ import annotations

import logging
import traceback

import pytest
from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelRequest
from pydantic_ai.models import Model, ModelRequestParameters, infer_model

from pathfinder.domain.provider_keys import KeyRefusal, ProviderKeyring
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import (
    DeploymentKeyRefusedError,
    ProviderKeyRefusedError,
)
from pathfinder.platform.model_keys import (
    attach_keyring,
    deployment_model,
    keyed_model,
    one_generation,
    turn_deployment_refusals,
    turn_refusals,
)
from pathfinder.tests._support.models import DEFAULT_MODEL
from pathfinder.tests._support.provider_wire import (
    ProviderWire,
    allow_requests_to_the_wire,
)

_SENTINEL = "sk-proj-sentinel-0123456789WXYZ"
_BODY_FRAGMENTS = (
    _SENTINEL,
    "sk-proj-",
    "Incorrect API key",
    "WXYZ",
    "credits remaining",
    "http",
)


@pytest.fixture(autouse=True)
def _wire(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_requests_to_the_wire(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "openai_api_key", _SENTINEL)


def _printed(error: BaseException) -> str:
    return str(error) + "".join(traceback.format_exception(error))


def _leaks(text: str) -> list[str]:
    return [fragment for fragment in _BODY_FRAGMENTS if fragment in text]


async def _stream_once(model: Model) -> None:
    async with (
        model,
        model.request_stream(
            [ModelRequest.user_text_prompt("ok")], None, ModelRequestParameters()
        ) as stream,
    ):
        async for _event in stream:
            pass


async def test_the_unguarded_provider_error_carries_the_key_tail() -> None:
    """The control: without the guard, the provider's body is the message."""
    wire = ProviderWire(refuse=True)
    model = infer_model(
        DEFAULT_MODEL,
        provider_factory=lambda _: wire.build("openai", SecretStr(_SENTINEL)),
    )

    with pytest.raises(ModelHTTPError) as caught:
        await one_generation(model)

    assert "Incorrect API key" in _printed(caught.value)


async def test_a_refused_key_raises_the_sentence_and_records_the_refusal() -> None:
    wire = ProviderWire(refuse=True)
    keyring = ProviderKeyring(active={"openai": SecretStr(_SENTINEL)})

    with attach_keyring(keyring, build=wire.build):
        model = keyed_model(DEFAULT_MODEL)
        assert isinstance(model, Model)
        with pytest.raises(ProviderKeyRefusedError) as caught:
            await one_generation(model)
        refusals = turn_refusals()

    error = caught.value
    assert _leaks(_printed(error)) == []
    assert (error.__cause__, error.__context__) == (None, None)
    assert refusals == {"openai": KeyRefusal.INVALID}
    assert str(error) == (
        "OpenAI refused your key: OpenAI refused the key you added, so nothing "
        "ran on it. Replace or remove your OpenAI key in Settings, under "
        "Provider keys."
    )


async def test_a_streamed_refusal_raises_the_same_sentence() -> None:
    wire = ProviderWire(refuse=True)
    keyring = ProviderKeyring(active={"openai": SecretStr(_SENTINEL)})

    with attach_keyring(keyring, build=wire.build):
        model = keyed_model(DEFAULT_MODEL)
        assert isinstance(model, Model)
        with pytest.raises(ProviderKeyRefusedError) as caught:
            await _stream_once(model)

    assert _leaks(_printed(caught.value)) == []


async def test_a_refusal_of_the_deployment_key_raises_the_sentence() -> None:
    wire = ProviderWire(refuse=True)

    with attach_keyring(ProviderKeyring(), build=wire.build):
        model = keyed_model(DEFAULT_MODEL)
        assert isinstance(model, Model)
        with pytest.raises(DeploymentKeyRefusedError) as caught:
            await one_generation(model)
        refused = (turn_refusals(), turn_deployment_refusals())

    error = caught.value
    assert _leaks(_printed(error)) == []
    assert (error.__cause__, error.__context__) == (None, None)
    assert refused == ({}, {"openai": KeyRefusal.INVALID})
    assert str(error) == (
        "OpenAI refused the request on the deployment's account: the key is not valid"
    )


async def test_a_deployment_error_that_is_no_refusal_carries_its_status() -> None:
    wire = ProviderWire(status=503)

    with attach_keyring(ProviderKeyring(), build=wire.build):
        model = keyed_model(DEFAULT_MODEL)
        assert isinstance(model, Model)
        with pytest.raises(ModelHTTPError) as caught:
            await one_generation(model)
        refused = turn_deployment_refusals()

    assert (caught.value.status_code, caught.value.body) == (503, None)
    assert refused == {}


class _Warned(BaseModel):
    """One structured log record, read by the fields the guard writes."""

    model_config = ConfigDict(extra="ignore")

    event: str = ""
    provider_type: str | None = None
    provider_code: str | None = None


async def test_a_billing_error_inside_the_stream_refuses_the_deployment_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The SDK raises it after the stream began, with the body and no status."""
    wire = ProviderWire(fails_mid_stream="openai-no-credit-stream")

    with (
        caplog.at_level(logging.WARNING),
        attach_keyring(ProviderKeyring(), build=wire.build),
    ):
        model = keyed_model(DEFAULT_MODEL)
        assert isinstance(model, Model)
        with pytest.raises(DeploymentKeyRefusedError) as caught:
            await _stream_once(model)
        refused = (turn_refusals(), turn_deployment_refusals())

    error = caught.value
    assert str(error) == (
        "OpenAI refused the request on the deployment's account: no credit remaining"
    )
    assert _leaks(_printed(error)) == []
    assert error.__cause__ is None
    assert refused == ({}, {"openai": KeyRefusal.NO_CREDIT})
    logged = [str(record.msg) for record in caplog.records]
    warned = [
        event
        for record in caplog.records
        if (event := _Warned.model_validate(record.msg)).event == "model provider error"
    ]
    assert [(w.provider_type, w.provider_code) for w in warned] == [
        ("insufficient_quota", "credit_balance_exhausted")
    ]
    assert [line for line in logged if "credits remaining" in line] == []


async def test_a_billing_error_inside_the_stream_refuses_the_researchers_key() -> None:
    wire = ProviderWire(fails_mid_stream="openai-no-credit-stream")
    keyring = ProviderKeyring(active={"openai": SecretStr(_SENTINEL)})

    with attach_keyring(keyring, build=wire.build):
        model = keyed_model(DEFAULT_MODEL)
        assert isinstance(model, Model)
        with pytest.raises(ProviderKeyRefusedError) as caught:
            await _stream_once(model)
        refused = (turn_refusals(), turn_deployment_refusals())

    assert _leaks(_printed(caught.value)) == []
    assert refused == ({"openai": KeyRefusal.NO_CREDIT}, {})


async def test_a_model_the_deployment_always_pays_for_is_guarded_too() -> None:
    wire = ProviderWire(refuse=True)
    keyring = ProviderKeyring(active={"openai": SecretStr("sk-researcher-key")})

    with attach_keyring(keyring, build=wire.build):
        judge = deployment_model(DEFAULT_MODEL)

    with (
        attach_keyring(ProviderKeyring()),
        pytest.raises(DeploymentKeyRefusedError) as caught,
    ):
        await one_generation(judge)

    assert _leaks(_printed(caught.value)) == []
    assert "sk-researcher-key" not in str(wire.sent_headers())
