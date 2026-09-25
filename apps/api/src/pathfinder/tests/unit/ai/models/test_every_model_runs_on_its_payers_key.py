"""Every place a turn resolves a model sends the key that pays for it."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from assistant_core.models.capture import (
    reset_llm_capture_hook,
    set_llm_capture_hook,
)
from assistant_core.platform.types import PaidBy
from pydantic import SecretStr
from pydantic_ai.models import Model

from pathfinder.ai.agents.compactor import build_compactor_agent
from pathfinder.ai.capabilities.metering import SpendMeter
from pathfinder.ai.conversation.title_generator import generate_conversation_title
from pathfinder.ai.graph._lead_model import resolve_lead_model_context
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_stream import _phase_agent
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.assistants.site_help.agent import build_site_help_agent
from pathfinder.domain.provider_keys import ProviderKeyring
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_keys import attach_keyring, one_generation
from pathfinder.tests._support.provider_wire import (
    ANSWER_TEXT,
    ProviderWire,
    allow_requests_to_the_wire,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_USER_KEY = "sk-user-sentinel-0123456789ABCD"
_DEPLOYMENT_KEY = "sk-deployment-sentinel-9876543210"
_KEYRING = ProviderKeyring(active={"openai": SecretStr(_USER_KEY)})


@dataclass
class _Resolved:
    """The model each role resolved to, as the capture seam receives it."""

    by_role: dict[str, Model | str] = field(default_factory=dict)

    def __call__(self, model: Model | str, role: str) -> Model:
        self.by_role[role] = model
        assert isinstance(model, Model)
        return model


@pytest.fixture(autouse=True)
def _cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_requests_to_the_wire(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "default_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", _DEPLOYMENT_KEY)


@pytest.fixture
def resolved() -> Iterator[_Resolved]:
    seen = _Resolved()
    token = set_llm_capture_hook(seen)
    try:
        yield seen
    finally:
        reset_llm_capture_hook(token)


async def _sent_key(model: Model | str, wire: ProviderWire) -> str:
    assert isinstance(model, Model)
    await one_generation(model)
    return wire.sent_headers()[-1]["authorization"]


async def test_the_lead_runs_on_the_researchers_key(resolved: _Resolved) -> None:
    wire = ProviderWire()

    with attach_keyring(_KEYRING, build=wire.build):
        resolve_lead_model_context(build_lead_agent())

    assert await _sent_key(resolved.by_role["lead"], wire) == f"Bearer {_USER_KEY}"


async def test_a_stage_runs_on_the_researchers_key(resolved: _Resolved) -> None:
    wire = ProviderWire()

    with attach_keyring(_KEYRING, build=wire.build):
        _phase_agent(lead_deps(pipeline_state()), "frame")

    assert await _sent_key(resolved.by_role["frame"], wire) == f"Bearer {_USER_KEY}"


async def test_site_help_runs_on_the_researchers_key() -> None:
    wire = ProviderWire()

    with attach_keyring(_KEYRING, build=wire.build):
        agent = build_site_help_agent()

    assert await _sent_key(agent.model or "", wire) == f"Bearer {_USER_KEY}"


async def test_the_compactor_runs_on_the_researchers_key() -> None:
    wire = ProviderWire()

    with attach_keyring(_KEYRING, build=wire.build):
        agent = build_compactor_agent(meter=SpendMeter())

    assert await _sent_key(agent.model or "", wire) == f"Bearer {_USER_KEY}"


async def test_the_title_runs_on_the_researchers_key() -> None:
    wire = ProviderWire()
    meter = SpendMeter()

    with attach_keyring(_KEYRING, build=wire.build):
        title = await generate_conversation_title(
            "list the kinases", build_pathfinder_spec().build_mock_model, meter
        )

    assert title == ANSWER_TEXT.rstrip(".")
    assert [h["authorization"] for h in wire.sent_headers()] == [f"Bearer {_USER_KEY}"]
    assert [(s.tokens, s.cost_usd, s.paid_by) for s in meter.spent] == [
        (17, Decimal("0.0000084"), PaidBy.USER)
    ]


async def test_a_title_on_a_refused_key_falls_back_to_the_message() -> None:
    wire = ProviderWire(refuse=True)

    with attach_keyring(_KEYRING, build=wire.build) as keys:
        title = await generate_conversation_title(
            "list the kinases", build_pathfinder_spec().build_mock_model, SpendMeter()
        )

    assert title == "list the kinases"
    assert list(keys.refusals) == ["openai"]
