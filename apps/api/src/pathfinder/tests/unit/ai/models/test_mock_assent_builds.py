"""An imperative to run and add builds, in the deterministic script.

Assent to the assistant's own offer, and a retry after a failed task, ask for
a build. The script classifies both as building intents and dispatches FRAME.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from assistant_core.models.scripted import current_scope_id, current_user_text
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition

from pathfinder.ai.models.mock import PATHFINDER_SCRIPT

ASSENT = (
    "Yes, rerun the differential expression and then create the strategy step "
    "from the genes that pass. [[arc:assent]]"
)
IMPERATIVE = (
    "Please run the differential expression now and add the resulting genes "
    "as a step in my strategy. [[arc:assent]]"
)

_LEAD_TOOLS = (
    "classify_user_intent",
    "frame_problem",
    "build_strategy",
    "verify_strategy",
    "read_ledger_section",
)


def _info() -> AgentInfo:
    return AgentInfo(
        function_tools=[ToolDefinition(name=name) for name in _LEAD_TOOLS],
        allow_text_output=False,
        output_tools=[],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
        instructions=None,
    )


@pytest.fixture
def scoped_text(request: pytest.FixtureRequest) -> Generator[str]:
    """The user text and site the script branches on, for one test."""
    text: str = request.param
    text_token = current_user_text.set(text)
    scope_token = current_scope_id.set("plasmodb")
    yield text
    current_user_text.reset(text_token)
    current_scope_id.reset(scope_token)


def _next_call(messages: list[ModelMessage]) -> ToolCallPart:
    match PATHFINDER_SCRIPT.response_part(messages, _info()):
        case ToolCallPart() as call:
            return call
        case text:
            raise AssertionError(text)


@pytest.mark.parametrize("scoped_text", [ASSENT, IMPERATIVE], indirect=True)
def test_the_script_classifies_an_imperative_as_a_building_intent(
    scoped_text: str,
) -> None:
    call = _next_call([ModelRequest(parts=[UserPromptPart(content=scoped_text)])])

    assert call.tool_name == "classify_user_intent"
    assert call.args_as_dict()["intent"]["classification"] == "extend_strategy"


@pytest.mark.parametrize("scoped_text", [ASSENT, IMPERATIVE], indirect=True)
def test_the_script_frames_after_the_classification(scoped_text: str) -> None:
    classified = _next_call(
        [ModelRequest(parts=[UserPromptPart(content=scoped_text)])],
    )

    call = _next_call(
        [
            ModelRequest(parts=[UserPromptPart(content=scoped_text)]),
            ModelResponse(parts=[classified]),
        ],
    )

    assert call.tool_name == "frame_problem"
