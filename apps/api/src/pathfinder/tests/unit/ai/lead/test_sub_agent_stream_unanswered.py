"""A dispatch whose model produced nothing records the stage that ran it."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

import pytest
from pydantic_ai import RunContext, Tool
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.toolsets import FunctionToolset

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import sub_agent_stream
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.sub_agent_stream import PhaseRun, stream_sub_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.platform.config import get_settings
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import (
    called_tool_names,
    final_result_model,
    lead_deps,
    pipeline_state,
    tool_script_model,
)

pytestmark = pytest.mark.usefixtures("collector")

_UNREACHABLE = "Connection error."
_DEFAULT_MODEL = "openai:gpt-5.6-luna"
_PICKED_MODEL = "anthropic:claude-haiku-4-5"


@pytest.fixture(autouse=True)
def _real_provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The suite-wide provider is the mock one, which belongs to no stage pick."""
    monkeypatch.setenv("PATHFINDER_CHAT_PROVIDER", "default")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-for-model-resolution")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pinned agent keeps its scripted model; the id resolves on its own."""
    monkeypatch.setattr(
        sub_agent_stream,
        "phase_override_kwargs",
        lambda runtime, role: {},
    )


async def ping(ctx: RunContext[AgentDeps]) -> str:
    del ctx
    return "pong"


def _crashes_at_once(messages: list[ModelMessage]) -> ToolCallPart:
    """A model the provider never answers for."""
    del messages
    raise RuntimeError(_UNREACHABLE)


def _crashes_after_one_call(messages: list[ModelMessage]) -> ToolCallPart:
    """A model that answers one step, then loses its connection."""
    if "ping" in called_tool_names(messages):
        raise RuntimeError(_UNREACHABLE)
    return ToolCallPart(tool_name="ping", args="{}", tool_call_id="call_ping_1")


def _pinned(monkeypatch: pytest.MonkeyPatch, model: FunctionModel) -> Iterator[None]:
    toolset = FunctionToolset[AgentDeps](tools=[Tool(ping)])
    with pinned_sub_agent(
        monkeypatch,
        "frame",
        model=model,
        toolsets=[toolset],
        instructions="Call the tool.",
    ):
        yield


@pytest.fixture
def unreachable_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield from _pinned(monkeypatch, tool_script_model(_crashes_at_once))


@pytest.fixture
def frame_lost_after_answering(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield from _pinned(monkeypatch, tool_script_model(_crashes_after_one_call))


@pytest.fixture
def answering_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    model = final_result_model(
        {"summary": "one criterion bound", "disposition": "needs_user"},
    )
    yield from _pinned(monkeypatch, model)


def _deps() -> LeadDeps:
    return lead_deps(pipeline_state(user_prompt="Find the kinases."))


async def _dispatch(deps: LeadDeps) -> object:
    return await stream_sub_agent(
        run=PhaseRun("frame", "bind the criteria", 1),
        agent_deps=agent_deps_for(deps),
        parent_tool_call_id="call_frame_1",
        expected_output_type=FrameResult,
        deps=deps,
    )


@pytest.mark.usefixtures("unreachable_frame")
async def test_a_pass_whose_model_never_answered_names_its_stage() -> None:
    deps = _deps()

    with pytest.raises(RuntimeError, match=_UNREACHABLE):
        await _dispatch(deps)

    stage = deps.unanswered_stage
    assert stage is not None
    assert stage.role == "frame"
    assert stage.model_id == _DEFAULT_MODEL


@pytest.mark.usefixtures("unreachable_frame")
async def test_the_stage_names_the_model_the_researcher_picked_for_it() -> None:
    """The per-stage pick is the model that ran, so it is the one to name."""
    deps = _deps()
    deps.runtime = dataclasses.replace(
        deps.runtime,
        phase_models={"frame": _PICKED_MODEL},
    )

    with pytest.raises(RuntimeError, match=_UNREACHABLE):
        await _dispatch(deps)

    stage = deps.unanswered_stage
    assert stage is not None
    assert stage.model_id == _PICKED_MODEL


@pytest.mark.usefixtures("frame_lost_after_answering")
async def test_a_pass_that_answered_before_it_failed_names_no_stage() -> None:
    deps = _deps()

    with pytest.raises(RuntimeError, match=_UNREACHABLE):
        await _dispatch(deps)

    assert deps.unanswered_stage is None


@pytest.mark.usefixtures("answering_frame")
async def test_a_pass_that_ran_to_its_answer_names_no_stage() -> None:
    deps = _deps()

    delta = await _dispatch(deps)

    assert isinstance(delta, FrameResult)
    assert delta.summary == "one criterion bound"
    assert deps.unanswered_stage is None
