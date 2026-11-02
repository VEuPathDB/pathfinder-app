"""A step whose agent offers no tool plays the Lead's arc only when it is the
Lead's run."""

from __future__ import annotations

import contextvars

from pydantic import TypeAdapter
from pydantic_ai.messages import ModelRequest, ToolCallPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo

from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.models.mock import PATHFINDER_SCRIPT
from pathfinder.ai.models.mock.prose_arcs import OFF_TOPIC_PROSE
from pathfinder.tests.unit.ai.models._mock_pins import unframed_pins

_TEXT = "Write me a poem [[arc:off-topic]]"
_NO_TOOLS = AgentInfo(
    function_tools=[],
    allow_text_output=False,
    output_tools=[],
    model_settings=None,
    model_request_parameters=ModelRequestParameters(),
    instructions=None,
)


def _answer(instructions: str) -> dict[str, object]:
    def run() -> dict[str, object]:
        bind_scripted_scope("plasmodb", _TEXT)
        request = ModelRequest(
            parts=[UserPromptPart(content=_TEXT)], instructions=instructions
        )
        part = PATHFINDER_SCRIPT.response_part([request], _NO_TOOLS)
        return TypeAdapter(ToolCallPart).validate_python(part).args_as_dict()

    return contextvars.copy_context().run(run)


def test_the_leads_step_with_no_tool_answers_from_its_arc() -> None:
    assert _answer(unframed_pins()) == {
        "prose": OFF_TOPIC_PROSE,
        "nextState": "await_user",
    }


def test_another_agents_step_with_no_tool_ends_empty() -> None:
    assert _answer("Write a short title.") == {}
