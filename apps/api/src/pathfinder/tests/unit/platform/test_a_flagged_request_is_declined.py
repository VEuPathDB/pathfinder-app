from __future__ import annotations

from typing import Any

import httpx2
import pytest
from assistant_core.errors import ModelDeclinedError
from pydantic import SecretStr
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models import Model
from pydantic_ai.providers import Provider
from pydantic_ai.providers.openai import OpenAIProvider

from pathfinder.domain.provider_keys import KeyableProvider, ProviderKeyring
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_keys import attach_keyring, keyed_model, one_generation
from pathfinder.tests._support.models import DEFAULT_MODEL
from pathfinder.tests._support.provider_wire import allow_requests_to_the_wire

_FLAGGED = {
    "error": {
        "message": (
            "This content was flagged for possible biological risk. If this seems "
            "wrong, try rephrasing your request."
        ),
        "type": "invalid_request_error",
        "code": None,
    }
}
_INVALID = {
    "error": {
        "message": "Unsupported parameter: 'temperature'.",
        "type": "invalid_request_error",
        "code": "unsupported_parameter",
    }
}


@pytest.fixture(autouse=True)
def _wire(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_requests_to_the_wire(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "openai_api_key", "sk-deployment-test-key")


def _answering(body: dict[str, Any]) -> Any:
    def build(name: KeyableProvider, key: SecretStr) -> Provider[Any]:
        assert name == "openai"
        client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(
                lambda _request: httpx2.Response(400, json=body)
            )
        )
        return OpenAIProvider(api_key=key.get_secret_value(), http_client=client)

    return build


def _keyed() -> Model:
    model = keyed_model(DEFAULT_MODEL)
    assert isinstance(model, Model)
    return model


async def test_a_request_the_provider_flags_is_declined() -> None:
    with (
        attach_keyring(ProviderKeyring(), build=_answering(_FLAGGED)),
        pytest.raises(ModelDeclinedError) as caught,
    ):
        await one_generation(_keyed())

    assert "declined this request" in caught.value.text
    assert "biological safety filters" in caught.value.text


async def test_another_bad_request_is_no_decline() -> None:
    with (
        attach_keyring(ProviderKeyring(), build=_answering(_INVALID)),
        pytest.raises(ModelHTTPError) as caught,
    ):
        await one_generation(_keyed())

    assert caught.value.status_code == 400
