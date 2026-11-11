from __future__ import annotations

import re
from dataclasses import replace

import pytest
from pydantic_ai.toolsets import FunctionToolset

from pathfinder.ai.agents import verification
from pathfinder.ai.agents.research_reads import RESEARCH_UNAVAILABLE
from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS
from pathfinder.ai.explore._explore_instructions import EXPLORE_INSTRUCTIONS
from pathfinder.ai.lead import lead_agent
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.tests._support.instructions import pinned_instructions
from pathfinder.tests._support.offered_tools import served_tool_names
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_NAMED = re.compile(r"``([a-z_][a-z0-9_]*)``")


def _served_names(text: str) -> set[str]:
    return set(_NAMED.findall(text)) & served_tool_names()


def _served() -> FunctionToolset[object]:
    toolset: FunctionToolset[object] = FunctionToolset()
    for name in sorted(served_tool_names()):
        toolset.add_function(lambda query: query, name=name)
    return toolset


@pytest.mark.parametrize(
    "instructions",
    [LEAD_INSTRUCTIONS, EXPLORE_INSTRUCTIONS, _VERIFICATION_INSTRUCTIONS],
)
def test_no_static_instruction_names_a_research_read(instructions: str) -> None:
    assert _served_names(instructions) == set()


def test_the_lead_names_the_research_reads_when_the_source_resolved() -> None:
    deps = lead_deps(pipeline_state(user_prompt="q"))
    deps.runtime = replace(deps.runtime, tool_sources={"research": _served()})

    text = lead_agent.pinned_research_reads(run_context_for(deps))

    assert _served_names(text) == served_tool_names()


def test_the_lead_says_the_research_reads_are_unavailable_without_the_source() -> None:
    text = lead_agent.pinned_research_reads(
        run_context_for(lead_deps(pipeline_state(user_prompt="q")))
    )

    assert text == RESEARCH_UNAVAILABLE


def test_verify_names_the_research_reads_when_the_source_resolved() -> None:
    ctx = agent_run_context()
    ctx.deps.tool_sources = _served()

    assert _served_names(verification.pinned_research_reads(ctx)) == served_tool_names()


def test_verify_says_the_research_reads_are_unavailable_without_the_source() -> None:
    assert (
        verification.pinned_research_reads(agent_run_context()) == RESEARCH_UNAVAILABLE
    )


def test_the_lead_and_verify_pin_the_research_reads() -> None:
    assert "pinned_research_reads" in pinned_instructions(lead_agent.build_lead_agent())
    assert "pinned_research_reads" in pinned_instructions(
        verification.build_verification_agent()
    )
