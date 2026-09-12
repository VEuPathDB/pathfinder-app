"""The Lead is told what the machine enforces, and the map stays complete.

The preamble is generated from the classification map and the tool registry's
own markers, so a tool registered without a class fails the gate here.
"""

from __future__ import annotations

import pytest
from assistant_core.graph.durable import DURABLE_TOOLS
from pydantic_ai import Agent
from pydantic_ai.exceptions import CallDeferred
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import Tool

from pathfinder.ai.lead.guarantees import (
    TOOL_REVERSIBILITY,
    Reversibility,
    machine_guarantees_pin,
    registered_tools,
    render_machine_guarantees,
)
from pathfinder.ai.lead.intent_gate import BUILDING_TOOLS
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests._support.durable_dispatch import capture_durable_dispatch
from pathfinder.tests._support.run_context import lead_run_context


def _tools() -> dict[str, Tool[LeadDeps]]:
    return registered_tools(build_lead_agent().toolsets)


def _classified(cls: Reversibility) -> set[str]:
    return {name for name, value in TOOL_REVERSIBILITY.items() if value is cls}


def test_every_registered_tool_carries_a_reversibility_class() -> None:
    """A tool the Lead can call and the map does not name fails here."""
    assert sorted(_tools()) == sorted(TOOL_REVERSIBILITY)


def test_the_map_names_no_tool_the_lead_cannot_call() -> None:
    assert set(TOOL_REVERSIBILITY) - set(_tools()) == set()


def test_every_destructive_tool_is_approval_gated_on_the_registry() -> None:
    tools = _tools()
    gated = {name for name, tool in tools.items() if tool.requires_approval is True}
    assert _classified(Reversibility.GATED_DESTRUCTIVE) <= gated
    assert _classified(Reversibility.GATED_DESTRUCTIVE) == {"clear_strategy"}


def test_every_durable_tool_is_registered_sequential() -> None:
    """One parked call is checkpointed per turn, so a batch cannot hold two."""
    tools = _tools()
    sequential = {name for name, tool in tools.items() if tool.sequential}
    assert _classified(Reversibility.DURABLE) == sequential


@pytest.mark.parametrize("name", sorted(_classified(Reversibility.DURABLE)))
async def test_a_durable_tool_defers_a_job_a_worker_declared(
    name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pin promises a worker runs these, so each one really defers to one."""
    dispatch = capture_durable_dispatch(monkeypatch)

    with pytest.raises(CallDeferred):
        await _tools()[name].function(lead_run_context(tool_call_id="call_1"))

    assert [entry["tool_name"] in DURABLE_TOOLS for entry in dispatch.created] == [True]


def test_no_building_tool_is_classified_as_a_read() -> None:
    reads = _classified(Reversibility.READ)
    assert BUILDING_TOOLS & reads == frozenset()


def test_the_preamble_states_the_four_guarantees() -> None:
    text = " ".join(render_machine_guarantees(_tools()).split())

    assert "appends a revision" in text
    assert "revert" in text
    assert "clear_strategy" in text
    assert "verify_strategy" in text
    assert "edit_strategy" in text
    assert "frame_problem" in text
    assert "run_eda_compute" in text


def test_the_preamble_names_every_tool_it_classifies() -> None:
    text = render_machine_guarantees(_tools())
    missing = [name for name in TOOL_REVERSIBILITY if name not in text]
    assert missing == []


def test_the_pin_renders_the_same_text_the_renderer_builds() -> None:
    agent = build_lead_agent()
    pin = machine_guarantees_pin(agent.toolsets)

    assert pin() == render_machine_guarantees(registered_tools(agent.toolsets))


async def test_the_preamble_reaches_the_model_that_reads_it() -> None:
    """A pin with no context argument still renders into the request."""
    seen: list[str] = []

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        request = messages[-1]
        assert isinstance(request, ModelRequest)
        seen.append(request.instructions or "")
        return ModelResponse(parts=[TextPart("done")])

    agent: Agent[None, str] = Agent(FunctionModel(_fn))
    agent.instructions(machine_guarantees_pin(build_lead_agent().toolsets))

    await agent.run("hello")

    assert "What the machine already guarantees" in seen[0]
    assert "appends a revision" in seen[0]
