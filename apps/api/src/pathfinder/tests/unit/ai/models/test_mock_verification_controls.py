"""The mock VERIFY tests the build against controls when the request names them."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from assistant_core.models.scripted import current_scope_id, current_user_text
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

from pathfinder.ai.models.mock import PATHFINDER_SCRIPT

_VERIFY_TOOLS = ("run_control_tests_on_step", "run_control_tests_on_search")


def _info() -> AgentInfo:
    return AgentInfo(
        function_tools=[ToolDefinition(name=name) for name in _VERIFY_TOOLS],
        allow_text_output=False,
        output_tools=[],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
        instructions=None,
    )


@pytest.fixture
def scoped_text(request: pytest.FixtureRequest) -> Generator[str]:
    text: str = request.param
    text_token = current_user_text.set(text)
    scope_token = current_scope_id.set("plasmodb")
    yield text
    current_user_text.reset(text_token)
    current_scope_id.reset(scope_token)


def _work_order() -> list[ModelMessage]:
    return [ModelRequest(parts=[UserPromptPart(content="Verification work order")])]


def _call(messages: list[ModelMessage]) -> ToolCallPart:
    part = PATHFINDER_SCRIPT.response_part(messages, _info())
    assert isinstance(part, ToolCallPart)
    return part


@pytest.mark.parametrize(
    "scoped_text", ["Find kinases and check them against my controls."], indirect=True
)
def test_a_request_that_names_controls_runs_a_control_test_first(
    scoped_text: str,
) -> None:
    del scoped_text
    call = _call(_work_order())

    assert call.tool_name == "run_control_tests_on_search"
    assert call.args_as_dict() == {
        "target_search_name": "GenesByTaxon",
        "target_parameters": {
            "organism": {
                "type": "multi-pick-vocabulary",
                "values": ["Plasmodium falciparum 3D7"],
            }
        },
        "positive_controls": ["PF3D7_0102600", "PF3D7_0709000", "PF3D7_1133400"],
        "negative_controls": ["TGME49_205250"],
    }


@pytest.mark.parametrize(
    "scoped_text", ["Find kinases and check them against my controls."], indirect=True
)
def test_the_digest_follows_the_control_test(scoped_text: str) -> None:
    del scoped_text
    tested: list[ModelMessage] = [
        *_work_order(),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="run_control_tests_on_search",
                    args={},
                    tool_call_id="call_controls",
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="run_control_tests_on_search",
                    content={"stepId": 1},
                    tool_call_id="call_controls",
                )
            ]
        ),
    ]

    assert _call(tested).tool_name == "final_result"


@pytest.mark.parametrize("scoped_text", ["Find kinases in 3D7."], indirect=True)
def test_a_request_without_controls_goes_straight_to_the_digest(
    scoped_text: str,
) -> None:
    del scoped_text

    assert _call(_work_order()).tool_name == "final_result"
