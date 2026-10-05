"""Each agent sends the model the reasoning effort its turn resolved."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import uuid4

import pytest
from assistant_core.platform import db
from assistant_core.platform.types import ReasoningEffort
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.profiles import ModelProfile

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph._lead_model import resolve_lead_model_context
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import (
    BUILD_SUB_AGENT_BY_ROLE,
    LeadDeps,
    phase_override_kwargs,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.platform.config import get_settings

_SITE = "plasmodb"
_ASKED = "Find the kinases."


class _SentError(Exception):
    """The run stops at its first model request."""


def _recording(sent: list[object]) -> FunctionModel:
    """A thinking model that records the effort each request carries."""

    def _model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        sent.append(info.model_request_parameters.thinking)
        raise _SentError

    return FunctionModel(_model, profile=ModelProfile(supports_thinking=True))


def _deps(phase_reasoning: dict[str, ReasoningEffort]) -> LeadDeps:
    user_id = uuid4()
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=user_id,
        site_id=_SITE,
        mode="strategy",
        user_prompt=_ASKED,
    )
    runtime = Context(
        site_id=_SITE,
        user_id=user_id,
        strategy_session=StrategySession(site_id=_SITE),
        db_session_factory=db.async_session_factory,
        cancel_event=asyncio.Event(),
        phase_reasoning=phase_reasoning,
    )
    return LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])


@pytest.fixture(autouse=True)
def _real_provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The mock provider skips the settings path these tests read."""
    monkeypatch.setenv("PATHFINDER_CHAT_PROVIDER", "default")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-for-model-translation")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize("role", ["frame", "execution", "verification"])
@pytest.mark.parametrize("effort", ["low", "high", "xhigh"])
async def test_a_sub_agent_sends_its_turns_effort(
    role: PhaseRole, effort: ReasoningEffort
) -> None:
    deps = _deps({role: effort})
    agent = BUILD_SUB_AGENT_BY_ROLE[role]()
    settings = phase_override_kwargs(deps.runtime, role)["model_settings"]
    sent: list[object] = []

    with (
        agent.override(model=_recording(sent), model_settings=settings),
        pytest.raises(_SentError),
    ):
        await agent.run(_ASKED, deps=agent_deps_for(deps))

    assert sent == [effort]


@pytest.mark.parametrize("effort", ["low", "high", "xhigh"])
async def test_the_lead_sends_its_turns_effort(effort: ReasoningEffort) -> None:
    agent = build_lead_agent()
    lead_model = resolve_lead_model_context(agent, reasoning_effort=effort)
    sent: list[object] = []

    with (
        lead_model.override,
        agent.override(model=_recording(sent)),
        pytest.raises(_SentError),
    ):
        await agent.run(_ASKED, deps=_deps({}))

    assert sent == [effort]
