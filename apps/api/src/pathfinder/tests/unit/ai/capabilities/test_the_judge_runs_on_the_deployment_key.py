"""The injection judge is the deployment's, whatever key the researcher holds."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models import Model

from pathfinder.ai.capabilities.security import _judge_model
from pathfinder.domain.provider_keys import ProviderKeyring
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_keys import attach_keyring, one_generation
from pathfinder.tests._support.provider_wire import (
    ProviderWire,
    allow_requests_to_the_wire,
)

_USER_KEY = "sk-user-sentinel-0123456789ABCD"
_DEPLOYMENT_KEY = "sk-deployment-sentinel-9876543210"


@pytest.fixture(autouse=True)
def _cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_requests_to_the_wire(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "openai_api_key", _DEPLOYMENT_KEY)


async def test_the_judge_sends_the_deployment_key_and_no_provider_body() -> None:
    wire = ProviderWire(refuse=True)
    keyring = ProviderKeyring(active={"openai": SecretStr(_USER_KEY)})

    with attach_keyring(keyring, build=wire.build):
        judge = _judge_model()
    assert isinstance(judge, Model)
    with pytest.raises(ModelHTTPError) as caught:
        await one_generation(judge)

    assert [h["authorization"] for h in wire.sent_headers()] == [
        f"Bearer {_DEPLOYMENT_KEY}"
    ]
    assert (caught.value.status_code, caught.value.body) == (401, None)
