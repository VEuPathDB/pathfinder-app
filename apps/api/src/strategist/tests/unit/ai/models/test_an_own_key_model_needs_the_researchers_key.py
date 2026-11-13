from __future__ import annotations

from collections.abc import Callable

import pytest
from assistant_core.platform.types import PaidBy
from pydantic import SecretStr
from pydantic_ai.models import Model

from strategist.ai.agents.compactor import build_compactor_agent
from strategist.ai.capabilities.metering import SpendMeter
from strategist.ai.graph._lead_model import resolve_lead_model_context
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.ai.lead.sub_agent_stream import _phase_agent
from strategist.domain.provider_keys import KeyStatuses, ProviderKeyring
from strategist.platform.config import get_settings
from strategist.platform.errors import (
    DeploymentKeyRefusedError,
    OwnKeyRequiredError,
    ProviderKeyRefusedError,
)
from strategist.platform.model_keys import (
    attach_keyring,
    deployment_model,
    keyed_model,
    one_generation,
)
from strategist.services.provider_keys import require_payers
from strategist.tests._support.models import ANTHROPIC_SMALL, DEFAULT_MODEL
from strategist.tests._support.provider_wire import (
    ProviderWire,
    allow_requests_to_the_wire,
)
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

OPUS = "anthropic:claude-opus-5-5"
FABLE = "anthropic:claude-fable-5-1"
_USER_KEY = "sk-ant-user-sentinel-0123456789"
_DEPLOYMENT_KEY = "sk-ant-deployment-sentinel-98765"
_OWN_ANTHROPIC = ProviderKeyring(active={"anthropic": SecretStr(_USER_KEY)})


@pytest.fixture(autouse=True)
def _deployment_holds_an_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_requests_to_the_wire(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "strategist_chat_provider", "default")
    monkeypatch.setattr(settings, "default_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", _DEPLOYMENT_KEY)
    monkeypatch.setattr(settings, "anthropic_api_key", _DEPLOYMENT_KEY)


def _lead(model_id: str) -> object:
    return resolve_lead_model_context(build_lead_agent(), model_override=model_id)


def _stage(model_id: str) -> object:
    deps = lead_deps(pipeline_state())
    deps.runtime.phase_models["frame"] = model_id
    return _phase_agent(deps, "frame")


def _compactor(model_id: str) -> object:
    return build_compactor_agent(meter=SpendMeter(), model_id=model_id)


_PATHS: list[Callable[[str], object]] = [
    _lead,
    _stage,
    _compactor,
    keyed_model,
]


@pytest.mark.parametrize("resolve", _PATHS, ids=lambda f: f.__name__)
@pytest.mark.parametrize("model_id", [OPUS, FABLE])
def test_a_pick_of_an_own_key_model_without_the_key_is_refused(
    resolve: Callable[[str], object], model_id: str
) -> None:
    wire = ProviderWire()

    with (
        attach_keyring(ProviderKeyring(), build=wire.build),
        pytest.raises(OwnKeyRequiredError),
    ):
        resolve(model_id)

    assert wire.sent_headers() == []


@pytest.mark.parametrize("model_id", [OPUS, FABLE])
async def test_the_researchers_anthropic_key_runs_an_own_key_model(
    model_id: str,
) -> None:
    wire = ProviderWire(refuse=True)

    with attach_keyring(_OWN_ANTHROPIC, build=wire.build):
        model = keyed_model(model_id)
        assert isinstance(model, Model)
        with pytest.raises(ProviderKeyRefusedError):
            await one_generation(model)

    assert [h["authorization"] for h in wire.sent_headers()] == [f"Bearer {_USER_KEY}"]


async def test_the_deployment_runs_haiku_on_its_own_key() -> None:
    wire = ProviderWire(refuse=True)

    with attach_keyring(ProviderKeyring(), build=wire.build):
        model = keyed_model(ANTHROPIC_SMALL)
        assert isinstance(model, Model)
        with pytest.raises(DeploymentKeyRefusedError):
            await one_generation(model)

    assert [h["authorization"] for h in wire.sent_headers()] == [
        f"Bearer {_DEPLOYMENT_KEY}"
    ]


@pytest.mark.parametrize("model_id", [OPUS, FABLE, "openai:not-in-the-catalog"])
def test_the_judges_deployment_model_is_only_one_the_deployment_pays_for(
    model_id: str,
) -> None:
    with pytest.raises(OwnKeyRequiredError):
        deployment_model(model_id)


def test_a_turn_naming_opus_without_the_key_is_refused_at_the_gate() -> None:
    with pytest.raises(OwnKeyRequiredError) as caught:
        require_payers([DEFAULT_MODEL, OPUS], KeyStatuses())

    assert (caught.value.status, caught.value.title) == (
        422,
        "Claude Opus 5.5 runs on your own Anthropic key",
    )


def test_a_turn_naming_opus_on_the_researchers_key_passes_the_gate() -> None:
    paid = require_payers(
        [DEFAULT_MODEL, OPUS], KeyStatuses(active=frozenset({"anthropic"}))
    )

    assert paid == {"openai": PaidBy.DEPLOYMENT, "anthropic": PaidBy.USER}
