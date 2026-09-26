"""The FRAME script survives an in-run compaction of its own history.

Compaction folds the run's middle into a digest the head request carries, so
the script reads its work order from the head and counts the digest's calls as
calls it has already made.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from assistant_core.conversation.history import compact_history
from assistant_core.models.scripted import (
    current_scope_id,
    current_user_text,
    last_user_text,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition
from veupathdb.domain.parameters import MultiPickValue, StringValue

from pathfinder.ai.lead.edit_messages import edit_work_order
from pathfinder.ai.models.mock import PATHFINDER_SCRIPT
from pathfinder.ai.models.mock.history import acted_tool_names, head_work_order
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.tests._support.tool_exchange import tool_exchange

_PF = "Plasmodium falciparum 3D7"
_EDIT_TEXT = "Change the transmembrane range to 1 to 99. [[arc:edit-param]]"
_BUILD_TEXT = "Find genes with a signal peptide. [[arc:single]]"
_CRITERION = "step_tm"
_FRAME_TOOLS = ("set_criterion", "set_structure", "list_searches")


@pytest.fixture
def plasmo_turn(request: pytest.FixtureRequest) -> Generator[None]:
    """The user text and site the script branches on, for one test."""
    text_token = current_user_text.set(request.param)
    scope_token = current_scope_id.set("plasmodb")
    yield
    current_user_text.reset(text_token)
    current_scope_id.reset(scope_token)


def _info() -> AgentInfo:
    return AgentInfo(
        function_tools=[ToolDefinition(name=name) for name in _FRAME_TOOLS],
        allow_text_output=False,
        output_tools=[],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
        instructions=None,
    )


def _next_call(messages: list[ModelMessage]) -> ToolCallPart:
    match PATHFINDER_SCRIPT.response_part(messages, _info()):
        case ToolCallPart() as call:
            return call
        case text:
            raise AssertionError(text)


def _edit_order() -> str:
    spec = OperationalSpec(
        goal="3D7 genes",
        criteria=[
            Criterion(
                id=_CRITERION,
                text=f"{_PF} genes with 2 to 99 transmembrane domains",
                search_name="GenesByTransmembraneDomains",
                role="seed",
                resolved_params={
                    "organism": MultiPickValue(values=[_PF]),
                    "min_tm": StringValue(value="2"),
                },
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=_CRITERION)
        ),
    )
    return edit_work_order(
        "change the domain range",
        _EDIT_TEXT,
        spec,
        pending=SpecDiff(),
        answered=spec,
        answer=None,
    )


def _oversized_listing() -> list[str]:
    """A listing large enough to push the history past the compaction point."""
    return [f"GenesBy{index:060d}" for index in range(6000)]


def _compacted(
    work_order: str,
    criterion_id: str = _CRITERION,
    search_name: str = "GenesByTransmembraneDomains",
) -> list[ModelMessage]:
    """A FRAME run whose catalog read has been folded into a digest."""
    sheet: dict[str, Any] = {
        "criterionId": criterion_id,
        "searchName": search_name,
        "paramsTemplate": {"organism": None, "min_tm": None},
    }
    bound: dict[str, Any] = {
        "criterionId": criterion_id,
        "searchName": search_name,
        "resolvedParams": {"organism": [_PF], "min_tm": "1"},
    }
    history = [
        ModelRequest(parts=[UserPromptPart(content=work_order)]),
        *tool_exchange(0, "search_for_searches", []),
        *tool_exchange(1, "list_searches", _oversized_listing()),
        *tool_exchange(2, "set_criterion", sheet),
        *tool_exchange(3, "set_criterion", bound),
    ]
    compacted = compact_history(history)
    assert compacted != history
    return compacted


def test_the_digest_replaces_the_last_user_text() -> None:
    compacted = _compacted(_edit_order())

    assert last_user_text(compacted) != _edit_order()


def test_the_work_order_is_read_from_the_head_request() -> None:
    order = _edit_order()

    assert head_work_order(_compacted(order)) == order


def test_the_digest_calls_count_as_calls_already_made() -> None:
    names = acted_tool_names(_compacted(_edit_order()))

    assert "list_searches" in names
    assert "set_criterion" in names


@pytest.mark.parametrize("plasmo_turn", [_EDIT_TEXT], indirect=True)
@pytest.mark.usefixtures("plasmo_turn")
def test_an_edit_survives_the_compaction_of_its_own_history() -> None:
    call = _next_call(_compacted(_edit_order()))

    assert call.tool_name == "final_result"
    assert call.args_as_dict()["changes"] == [
        {
            "criterionId": _CRITERION,
            "disposition": "changed",
            "changedParams": {"min_tm": "1"},
        }
    ]


@pytest.mark.parametrize("plasmo_turn", [_BUILD_TEXT], indirect=True)
@pytest.mark.usefixtures("plasmo_turn")
def test_a_build_does_not_read_the_catalog_the_digest_records() -> None:
    order = f"FRAME work order: build\nUser's goal: {_BUILD_TEXT}"

    call = _next_call(_compacted(order, "signal_peptide", "GenesWithSignalPeptide"))

    assert call.tool_name == "set_structure"
