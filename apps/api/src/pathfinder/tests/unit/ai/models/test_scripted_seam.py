"""The seam between the scripted test model and PathFinder's script.

The harness detects which agent it is serving, advances a sequence and wires
a ``FunctionModel``. Which tool names name which role, and what each role
answers, is the product's script.
"""

from __future__ import annotations

from types import ModuleType

import pytest
from assistant_core.models import scripted
from assistant_core.models.scripted import (
    RoleMarkers,
    RoleScript,
    ScriptedModel,
    detect_role,
    next_unmade_call,
    retry_prompt_parts,
    scripted_call,
)
from pydantic import TypeAdapter
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition

from pathfinder.ai.models.mock import PATHFINDER_SCRIPT, get_mock_model

PRODUCT_PACKAGES = (
    "pathfinder.ai.models.mock",
    "pathfinder.domain",
    "pathfinder.ai.lead",
    "pathfinder.ai.agents",
)


def _info(*names: str) -> AgentInfo:
    return AgentInfo(
        function_tools=[ToolDefinition(name=n) for n in names],
        allow_text_output=True,
        output_tools=[],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
        instructions=None,
    )


def _foreign_bindings(module: ModuleType) -> set[str]:
    found: set[str] = set()
    for value in vars(module).values():
        origin = getattr(value, "__module__", None)
        if not isinstance(origin, str):
            continue
        found.update(pkg for pkg in PRODUCT_PACKAGES if origin.startswith(pkg))
    return found


def _script_for(name: str) -> RoleScript:
    def _run(messages: list[ModelMessage]) -> ToolCallPart:
        del messages
        return scripted_call(name, {})

    return _run


def _answered_tool(model: ScriptedModel, marker: str) -> ToolCallPart:
    """The tool call a script answered with, or a failure naming what came back."""
    return TypeAdapter(ToolCallPart).validate_python(
        model.response_part([], _info(marker))
    )


def test_the_harness_binds_nothing_of_the_product() -> None:
    assert _foreign_bindings(scripted) == set()


def test_the_harness_routes_to_the_first_matching_role() -> None:
    model = ScriptedModel(
        roles=(
            RoleMarkers(role="planner", markers=frozenset({"plan", "shared"})),
            RoleMarkers(role="writer", markers=frozenset({"shared"})),
        ),
        scripts={
            "planner": _script_for("planned"),
            "writer": _script_for("wrote"),
        },
        unknown=_script_for("nothing"),
    )
    assert _answered_tool(model, "shared").tool_name == "planned"


def test_the_harness_falls_back_when_no_marker_matches() -> None:
    model = ScriptedModel(
        roles=(RoleMarkers(role="planner", markers=frozenset({"plan"})),),
        scripts={"planner": _script_for("planned")},
        unknown=_script_for("nothing"),
    )
    assert _answered_tool(model, "unrelated").tool_name == "nothing"


def test_a_sequence_skips_the_calls_already_made() -> None:
    sequence = [
        scripted_call("first", {}),
        scripted_call("second", {}),
        scripted_call("final_result", {}),
    ]
    messages: list[ModelMessage] = [
        ModelResponse(parts=[scripted_call("first", {})]),
    ]
    assert next_unmade_call(sequence, messages).tool_name == "second"


def test_a_sequence_stops_at_its_terminal_call() -> None:
    sequence = [
        scripted_call("first", {}),
        scripted_call("final_result", {}),
    ]
    messages: list[ModelMessage] = [
        ModelResponse(parts=[scripted_call("first", {})]),
    ]
    assert next_unmade_call(sequence, messages).tool_name == "final_result"


def test_the_retry_parts_are_the_ones_a_tool_refused_on() -> None:
    messages: list[ModelMessage] = [
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name="kept", content="ok", tool_call_id="k1"),
                RetryPromptPart(
                    content="refused", tool_name="refused_tool", tool_call_id="r1"
                ),
            ]
        ),
    ]
    parts = retry_prompt_parts(messages)

    assert [p.tool_name for p in parts] == ["refused_tool"]
    assert "refused" in parts[0].model_response()


def test_the_product_script_declares_its_four_roles() -> None:
    assert [entry.role for entry in PATHFINDER_SCRIPT.roles] == [
        "lead",
        "frame",
        "verification",
        "execution",
    ]


@pytest.mark.parametrize(
    ("tool", "expected"),
    [
        ("frame_problem", "lead"),
        ("set_criterion", "frame"),
        ("run_control_tests_on_step", "verification"),
        ("update_leaf_params", "execution"),
    ],
)
def test_the_product_script_still_recognizes_each_sub_agent(
    tool: str,
    expected: str,
) -> None:
    assert detect_role(_info(tool), PATHFINDER_SCRIPT.roles) == expected


def test_the_mock_model_is_built_from_the_product_script() -> None:
    assert get_mock_model().model_name == PATHFINDER_SCRIPT.model_name
