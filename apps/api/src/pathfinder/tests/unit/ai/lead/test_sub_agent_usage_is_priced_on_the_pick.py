"""A stage's spend is priced on the model the researcher picked, and names its payer."""

from __future__ import annotations

import dataclasses

import pytest
from assistant_core.platform.types import PaidBy
from pydantic import SecretStr
from pydantic_ai.usage import RunUsage

from pathfinder.ai.lead.sub_agent_progress import record_stopped_usage
from pathfinder.ai.lead.sub_agent_tools import SubAgentRunUsage
from pathfinder.domain.provider_keys import ProviderKeyring
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_keys import attach_keyring
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_PICK = "anthropic:claude-opus-5"


@pytest.fixture(autouse=True)
def _cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "pathfinder_chat_provider", "default")


def _stopped_pass(keyring: ProviderKeyring) -> SubAgentRunUsage:
    recorded: list[SubAgentRunUsage] = []
    deps = lead_deps(pipeline_state(), record_usage=recorded.append)
    deps.runtime = dataclasses.replace(deps.runtime, phase_models={"frame": _PICK})

    with attach_keyring(keyring):
        record_stopped_usage(deps, "frame", "call_frame_1", RunUsage(input_tokens=90))

    [one] = recorded
    return one


def test_a_stopped_pass_is_priced_on_the_pick() -> None:
    stopped = _stopped_pass(ProviderKeyring())

    assert (stopped.provider_name, stopped.model_name) == ("anthropic", "claude-opus-5")
    assert stopped.paid_by is PaidBy.DEPLOYMENT


def test_a_stopped_pass_on_the_researchers_key_is_theirs() -> None:
    keyring = ProviderKeyring(active={"anthropic": SecretStr("sk-ant-0123456789")})

    assert _stopped_pass(keyring).paid_by is PaidBy.USER
