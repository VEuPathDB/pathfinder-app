"""A run the researcher approves on a card is asked on the card alone."""

from __future__ import annotations

import pytest
from pydantic_ai.toolsets import FunctionToolset, WrapperToolset

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.lead_agent import build_lead_agent

_CARD_RUNS = ("separate_controls", "optimize_search_parameters")
_PROSE_ASKS = ("says yes", "in prose first", "then wait", "offer ``")


def _registered_description(name: str) -> str:
    for mounted in build_lead_agent().toolsets:
        toolset = mounted
        while isinstance(toolset, WrapperToolset):
            toolset = toolset.wrapped
        if isinstance(toolset, FunctionToolset) and name in toolset.tools:
            return toolset.tools[name].description or ""
    msg = f"{name} is not registered on the Lead"
    raise AssertionError(msg)


@pytest.mark.parametrize("name", _CARD_RUNS)
def test_the_description_sends_the_ask_to_the_card(name: str) -> None:
    description = " ".join(_registered_description(name).split()).lower()

    assert [phrase for phrase in _PROSE_ASKS if phrase in description] == []
    assert "approves the run on its card" in description


def test_the_lead_instructions_send_both_runs_to_their_card() -> None:
    text = " ".join(LEAD_INSTRUCTIONS.split()).lower()

    assert [phrase for phrase in _PROSE_ASKS if phrase in text] == []
    for name in _CARD_RUNS:
        assert f"call ``{name}``; the researcher approves the run on its card" in text
