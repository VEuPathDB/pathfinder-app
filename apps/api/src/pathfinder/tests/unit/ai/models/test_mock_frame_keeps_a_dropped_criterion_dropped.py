"""A criterion ``set_structure`` reports dropped is final: the FRAME script never
binds it again, even after compaction folds its own replies into the digest,
and answers ``spec_ready`` over the criteria that remain."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from assistant_core.conversation.history import compact_history
from assistant_core.models.scripted import current_scope_id, current_user_text
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition

from pathfinder.ai.models.mock import PATHFINDER_SCRIPT
from pathfinder.tests._support.tool_exchange import tool_exchange

_PEST = "Anopheles gambiae PEST"
_MESSAGE = (
    f"Find {_PEST} genes whose proteins have a predicted signal peptide. "
    "[[arc:organism-universe]]"
)
_ORDER = f"FRAME work order: build\nUser's goal: {_MESSAGE}"
_FRAME_TOOLS = ("set_criterion", "set_structure", "list_searches")


@pytest.fixture(autouse=True)
def _vectorbase_turn() -> Generator[None]:
    text_token = current_user_text.set(_MESSAGE)
    scope_token = current_scope_id.set("vectorbase")
    yield
    current_user_text.reset(text_token)
    current_scope_id.reset(scope_token)


def _next_call(messages: list[ModelMessage]) -> ToolCallPart:
    info = AgentInfo(
        function_tools=[ToolDefinition(name=name) for name in _FRAME_TOOLS],
        allow_text_output=False,
        output_tools=[],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
        instructions=None,
    )
    match PATHFINDER_SCRIPT.response_part(messages, info):
        case ToolCallPart() as call:
            return call
        case text:
            raise AssertionError(text)


def _sheet(criterion_id: str, search_name: str, *names: str) -> dict[str, Any]:
    return {
        "criterionId": criterion_id,
        "searchName": search_name,
        "paramsTemplate": dict.fromkeys(names),
    }


def _bound(criterion_id: str, search_name: str, **params: object) -> dict[str, Any]:
    return {
        "criterionId": criterion_id,
        "searchName": search_name,
        "resolvedParams": params,
    }


def _after_the_drop() -> list[ModelMessage]:
    """A FRAME run whose set_structure dropped the organism criterion, with a
    sheet reply large enough that compaction folds every earlier reply."""
    model = "GenesByGeneModelChars"
    signal = "GenesWithSignalPeptide"
    large_sheet = {
        **_sheet("signal_peptide", signal, "organism", "signalp_version"),
        "vocabulary": [f"Organism {index:060d}" for index in range(6000)],
    }
    dropped = {
        "criteriaCombined": 1,
        "dropped": [
            {
                "criterionId": "organism_genes",
                "met": True,
                "fate": f"organism_genes ('{_PEST} genes') is dropped.",
            }
        ],
    }
    history = [
        ModelRequest(parts=[UserPromptPart(content=_ORDER)]),
        *tool_exchange(7, "search_memory", []),
        *tool_exchange(0, "search_for_searches", []),
        *tool_exchange(1, "list_searches", []),
        *tool_exchange(2, "set_criterion", _sheet("organism_genes", model, "organism")),
        *tool_exchange(
            3, "set_criterion", _bound("organism_genes", model, organism=[_PEST])
        ),
        *tool_exchange(4, "set_criterion", large_sheet),
        *tool_exchange(
            5, "set_criterion", _bound("signal_peptide", signal, organism=[_PEST])
        ),
        *tool_exchange(6, "set_structure", dropped),
    ]
    compacted = compact_history(history)
    assert len(compacted) < len(history)
    return compacted


def test_the_dropped_criterion_is_not_bound_again() -> None:
    call = _next_call(_after_the_drop())

    assert (call.tool_name, call.args_as_dict()["disposition"]) == (
        "final_result",
        "spec_ready",
    )


def test_the_result_counts_the_criteria_that_remain() -> None:
    call = _next_call(_after_the_drop())

    assert call.args_as_dict()["summary"] == (
        f"Framed 1 criterion(s) for {_PEST} signal peptide genes (mock)."
    )
