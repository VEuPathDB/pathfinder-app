"""A model runs on the researcher's key for its provider, and on nothing else."""

from __future__ import annotations

import pytest
from anthropic import AsyncAnthropic
from assistant_core.platform.types import PaidBy
from pydantic import SecretStr
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider

from pathfinder.domain.provider_keys import KeyableProvider, KeyRefusal, ProviderKeyring
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import (
    ProviderKeyRefusedError,
    ProviderKeyUnreadableError,
    ProviderNotConfiguredError,
    ProviderUnreachableError,
)
from pathfinder.platform.model_keys import (
    attach_keyring,
    build_provider,
    deployment_model,
    keyed_model,
    one_generation,
    probe_key,
    turn_paid_by,
)
from pathfinder.tests._support.provider_wire import (
    ProviderWire,
    allow_requests_to_the_wire,
)

_USER_KEY = "sk-user-sentinel-0123456789ABCD"
_DEPLOYMENT_KEY = "sk-deployment-sentinel-9876543210"
_SMALLEST: dict[KeyableProvider, str] = {
    "openai": "openai:gpt-5.6-luna",
    "anthropic": "anthropic:claude-haiku-4-5",
    "google": "google:gemini-3.5-flash-lite",
}
_KEY_HEADER: dict[KeyableProvider, tuple[str, str]] = {
    "openai": ("authorization", f"Bearer {_USER_KEY}"),
    "anthropic": ("x-api-key", _USER_KEY),
    "google": ("x-goog-api-key", _USER_KEY),
}


@pytest.fixture(autouse=True)
def _wire(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_requests_to_the_wire(monkeypatch)


@pytest.fixture
def _deployment_holds_every_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    for name in ("openai_api_key", "anthropic_api_key", "gemini_api_key"):
        monkeypatch.setattr(settings, name, _DEPLOYMENT_KEY)


def _model(model_id: str) -> Model:
    model = keyed_model(model_id)
    assert isinstance(model, Model)
    return model


@pytest.mark.usefixtures("_deployment_holds_every_key")
@pytest.mark.parametrize("provider", ["openai", "anthropic", "google"])
async def test_a_live_key_is_the_one_the_provider_receives(
    provider: KeyableProvider,
) -> None:
    wire = ProviderWire(refuse=True)
    keyring = ProviderKeyring(active={provider: SecretStr(_USER_KEY)})

    with (
        attach_keyring(keyring, build=wire.build),
        pytest.raises(ProviderKeyRefusedError),
    ):
        await one_generation(_model(_SMALLEST[provider]))

    header, value = _KEY_HEADER[provider]
    assert [headers[header] for headers in wire.sent_headers()] == [value]
    assert all(_DEPLOYMENT_KEY not in str(h) for h in wire.sent_headers())


@pytest.mark.usefixtures("_deployment_holds_every_key")
async def test_a_provider_without_a_live_key_runs_on_the_deployment_key() -> None:
    wire = ProviderWire()
    keyring = ProviderKeyring(active={"anthropic": SecretStr(_USER_KEY)})

    with attach_keyring(keyring, build=wire.build):
        await one_generation(_model("openai:gpt-5.6-luna"))

    assert [h["authorization"] for h in wire.sent_headers()] == [
        f"Bearer {_DEPLOYMENT_KEY}"
    ]


@pytest.mark.usefixtures("_deployment_holds_every_key")
@pytest.mark.parametrize(
    ("refusal", "error"),
    [
        (KeyRefusal.INVALID, ProviderKeyRefusedError),
        (KeyRefusal.UNREADABLE, ProviderKeyUnreadableError),
    ],
)
def test_a_refused_key_raises_before_any_request(
    refusal: KeyRefusal, error: type[Exception]
) -> None:
    wire = ProviderWire()
    keyring = ProviderKeyring(refused={"openai": refusal})

    with attach_keyring(keyring, build=wire.build), pytest.raises(error):
        keyed_model("openai:gpt-5.6-luna")

    assert wire.requests == []


@pytest.mark.usefixtures("_deployment_holds_every_key")
async def test_a_key_refused_during_the_turn_is_not_called_again() -> None:
    wire = ProviderWire(refuse=True)
    keyring = ProviderKeyring(active={"openai": SecretStr(_USER_KEY)})

    with attach_keyring(keyring, build=wire.build) as keys:
        with pytest.raises(ProviderKeyRefusedError):
            await one_generation(_model("openai:gpt-5.6-luna"))
        with pytest.raises(ProviderKeyRefusedError):
            keyed_model("openai:gpt-5.6-terra")

    assert keys.refusals == {"openai": KeyRefusal.INVALID}
    assert len(wire.requests) == 1


def test_a_provider_nobody_holds_a_key_for_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "openai_api_key", _DEPLOYMENT_KEY)
    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(ProviderNotConfiguredError, match="No Google key"):
        keyed_model("google:gemini-3.6-flash")


def test_a_mock_deployment_and_a_built_model_pass_unchanged() -> None:
    built = FunctionModel(lambda _messages, _info: ModelResponse(parts=[]))

    assert keyed_model("openai:gpt-5.6-luna") == "openai:gpt-5.6-luna"
    assert keyed_model(built) is built


def test_the_turn_pays_on_the_key_that_holds_the_provider() -> None:
    keyring = ProviderKeyring(active={"anthropic": SecretStr(_USER_KEY)})

    with attach_keyring(keyring):
        payers = [
            turn_paid_by("anthropic:claude-opus-5"),
            turn_paid_by("openai:gpt-5.6-luna"),
            turn_paid_by(""),
        ]

    assert payers == [PaidBy.USER, PaidBy.DEPLOYMENT, PaidBy.DEPLOYMENT]
    assert turn_paid_by("anthropic:claude-opus-5") is PaidBy.DEPLOYMENT


def test_a_built_provider_holds_the_key_it_was_given() -> None:
    openai = build_provider("openai", SecretStr(_USER_KEY))
    anthropic = build_provider("anthropic", SecretStr(_USER_KEY))

    assert isinstance(openai, OpenAIProvider)
    assert isinstance(anthropic, AnthropicProvider)
    assert isinstance(anthropic.client, AsyncAnthropic)
    assert (openai.client.api_key, anthropic.client.api_key) == (_USER_KEY, _USER_KEY)


@pytest.mark.usefixtures("_deployment_holds_every_key")
def test_a_keyed_model_never_prints_its_key() -> None:
    keyring = ProviderKeyring(active={"openai": SecretStr(_USER_KEY)})

    with attach_keyring(keyring, build=ProviderWire().build):
        model = _model("openai:gpt-5.6-luna")

    assert (repr(model) + str(model)).count(_USER_KEY) == 0


async def test_the_probe_passes_a_key_the_provider_answers() -> None:
    wire = ProviderWire()

    await probe_key("openai", _SMALLEST["openai"], SecretStr(_USER_KEY), wire.build)

    assert [h["authorization"] for h in wire.sent_headers()] == [f"Bearer {_USER_KEY}"]


@pytest.mark.parametrize("provider", ["openai", "anthropic", "google"])
async def test_the_probe_refuses_a_key_the_provider_refuses(
    provider: KeyableProvider,
) -> None:
    wire = ProviderWire(refuse=True)

    with pytest.raises(ProviderKeyRefusedError) as caught:
        await probe_key(provider, _SMALLEST[provider], SecretStr(_USER_KEY), wire.build)

    assert caught.value.status == 422


async def test_the_probe_reports_a_provider_that_did_not_answer() -> None:
    wire = ProviderWire(status=503)

    with pytest.raises(ProviderUnreachableError):
        await probe_key("openai", _SMALLEST["openai"], SecretStr(_USER_KEY), wire.build)


def test_a_deployment_model_of_a_provider_it_holds_no_key_for_fails_at_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A judge the deployment cannot pay for is reported when it is built."""
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")

    with pytest.raises(ProviderNotConfiguredError, match="No Anthropic key"):
        deployment_model("anthropic:claude-haiku-4-5")
