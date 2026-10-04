"""An edit whose every framing pass is refused ends with the refusal's reason as
a fact and a reply naming it, never with the tool's retry budget spent."""

from __future__ import annotations

from typing import NoReturn

import pytest
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_facts import show_the_facts
from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.dispatch_context import refuse_and_restore
from pathfinder.ai.lead.edit_dispatch import edit_strategy
from pathfinder.ai.lead.frame_dispatch import unwritten_requirements_refusal
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
)

_REASON = "Loosen the fold-change cutoff of the analysis step to 1.5-fold."
_NOTE = (
    "Loosen the existing computed comparison to a 1.5-fold cutoff and verify "
    "that the resulting gene count increases."
)
_REFUSAL = unwritten_requirements_refusal([_NOTE])
_UNBOUND = (
    f"The edit was not applied: {_REASON} The planning pass refused it: {_REFUSAL}"
)


async def _refused(*, deps: LeadDeps, **_: object) -> NoReturn:
    refuse_and_restore(deps, _REFUSAL)


def _lead(calls: list[str]) -> FunctionModel:
    """Dispatch the edit again after every refusal, and answer after a result."""

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        if any(isinstance(p, ToolReturnPart) for p in last.parts):
            return ModelResponse(parts=[TextPart("The fold change could not be set.")])
        assert all(
            isinstance(p, RetryPromptPart)
            for p in last.parts
            if p.part_kind != "user-prompt"
        )
        calls.append("edit_strategy")
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "edit_strategy", {"reason": _REASON}, f"call_edit_{len(calls)}"
                )
            ]
        )

    return FunctionModel(_fn, model_name="scripted")


async def test_the_fourth_refused_pass_ends_the_edit_with_its_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(edit_dispatch, "run_edit", _refused)
    deps = lead_deps(pipeline_state(user_prompt="loosen the fold change to 1.5-fold"))
    calls: list[str] = []
    agent: Agent[LeadDeps, str] = Agent(
        _lead(calls), deps_type=LeadDeps, tools=[Tool(edit_strategy, max_retries=3)]
    )

    run = await agent.run("loosen the fold change to 1.5-fold", deps=deps)

    returned = [
        p.content
        for m in run.all_messages()
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    ]
    assert len(calls) == 4
    assert returned == [
        EditDelta.model_validate(
            {"diff": {"changes": []}, "disposition": "unbound", "summary": _UNBOUND}
        )
    ]
    assert run.output == "The fold change could not be set."
    writer = ChunkCollector()
    show_the_facts(writer, deps, _LeadRunCapture())
    assert [facts["refusal"] for facts in writer.data_of("data-facts")] == [_UNBOUND]


async def test_a_refused_pass_before_the_last_attempt_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(edit_dispatch, "run_edit", _refused)
    deps = lead_deps(pipeline_state(user_prompt="loosen the fold change to 1.5-fold"))
    calls: list[str] = []
    agent: Agent[LeadDeps, str] = Agent(
        _lead(calls), deps_type=LeadDeps, tools=[Tool(edit_strategy, max_retries=5)]
    )

    await agent.run("loosen the fold change to 1.5-fold", deps=deps)

    assert len(calls) == 6
    assert deps.state.turn_markers.unbound_edit == _UNBOUND
