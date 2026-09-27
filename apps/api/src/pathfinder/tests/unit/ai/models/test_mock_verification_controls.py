"""The mock VERIFY, picked by its tools, tests the root against the saved set the
listing names when the message names the controls-test arc, and samples a root
first."""

from __future__ import annotations

import contextvars

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition

from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.verify_dispatch import work_order
from pathfinder.ai.models.mock import PATHFINDER_SCRIPT
from pathfinder.tests.unit.ai.models._mock_turns import CONTROL_SET_ID, verify_order

_VERIFY_TOOLS = (
    "run_control_tests_on_step",
    "list_control_sets",
    "get_strategy",
    "get_sample_records",
)
_STRATEGY = {"steps": [{"id": "step_root", "wdkStepId": 555}]}


def _info() -> AgentInfo:
    return AgentInfo(
        function_tools=[ToolDefinition(name=name) for name in _VERIFY_TOOLS],
        allow_text_output=False,
        output_tools=[],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
        instructions=None,
    )


def _next(text: str, messages: list[ModelMessage]) -> str | dict[str, object]:
    def run() -> str | dict[str, object]:
        bind_scripted_scope("vectorbase", text)
        match PATHFINDER_SCRIPT.response_part(messages, _info()):
            case ToolCallPart() as call:
                return call.args_as_dict()
            case prose:
                return prose.content

    return contextvars.copy_context().run(run)


def _answered(
    tool_name: str, content: object, messages: list[ModelMessage]
) -> list[ModelMessage]:
    call = ToolCallPart(tool_name=tool_name, args={}, tool_call_id=tool_name)
    return [
        *messages,
        ModelResponse(parts=[call]),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name=tool_name, content=content, tool_call_id=tool_name
                )
            ]
        ),
    ]


def _read_strategy(order: str) -> list[ModelMessage]:
    return _answered(
        "get_strategy", _STRATEGY, [ModelRequest(parts=[UserPromptPart(content=order)])]
    )


def test_a_root_the_order_does_not_name_is_tested_as_the_strategy_read_names_it() -> (
    None
):
    order = work_order("mock verification", None, None)
    listed = _answered(
        "list_control_sets",
        [{"controlSetId": CONTROL_SET_ID, "name": "Controls from this message"}],
        _read_strategy(order),
    )

    first = _next("Test it [[arc:controls-test]]", _read_strategy(order))
    args = _next("Test it [[arc:controls-test]]", listed)

    assert first == {}
    assert args == {"wdk_step_id": 555, "control_set_id": CONTROL_SET_ID}


def test_an_arc_without_controls_samples_the_root() -> None:
    args = _next("Find genes [[arc:single]]", _read_strategy(verify_order(12)))

    assert args == {"wdk_step_id": 555, "limit": 2}
