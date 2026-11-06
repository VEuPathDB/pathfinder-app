from __future__ import annotations

from collections.abc import Iterator

import pytest
from assistant_core.models.scripted import scripted_call
from pydantic import TypeAdapter
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition

from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.models.mock import PATHFINDER_SCRIPT, role_script
from pathfinder.ai.models.mock.arc import EXPLORE_ECHO
from pathfinder.ai.models.mock.explore_arc import (
    EXPLORE_ARC,
    FIRST_LABEL,
    NO_READING,
    ONE_READING,
    ONE_READING_ARC,
    SECOND_LABEL,
)
from pathfinder.ai.models.mock.registry import ARCS
from pathfinder.ai.models.mock.strategy_specs import SIGNAL_PEPTIDE

_EXPLORE_TOOLS = AgentInfo(
    function_tools=[ToolDefinition(name="propose_readings")],
    allow_text_output=True,
    output_tools=[],
    model_settings=None,
    model_request_parameters=ModelRequestParameters(),
    instructions=None,
)
_CALL = TypeAdapter(ToolCallPart)
_TEXT = TypeAdapter(TextPart)


@pytest.fixture
def prompt(request: pytest.FixtureRequest) -> Iterator[str]:
    said = str(request.param)
    bind_scripted_scope("plasmodb", said)
    yield said
    bind_scripted_scope("", "")


def _asked(said: str) -> list[ModelMessage]:
    return [ModelRequest(parts=[UserPromptPart(content=said)])]


def _after(messages: list[ModelMessage], call: ToolCallPart) -> list[ModelMessage]:
    returned = ToolReturnPart(
        tool_name=call.tool_name, content="done", tool_call_id=call.tool_call_id
    )
    return [
        *messages,
        ModelResponse(parts=[call]),
        ModelRequest(parts=[returned]),
    ]


def _explore(messages: list[ModelMessage]) -> ToolCallPart | TextPart:
    return PATHFINDER_SCRIPT.response_part(messages, _EXPLORE_TOOLS)


def test_the_explore_arc_is_registered_under_its_name() -> None:
    assert {EXPLORE_ARC, ONE_READING_ARC, "explore-no-reading"} <= set(ARCS)


@pytest.mark.parametrize(
    "prompt", ["Which genes carry a signal peptide? [[arc:explore]]"], indirect=True
)
def test_the_explore_arc_counts_two_readings_then_offers_them(prompt: str) -> None:
    messages = _asked(prompt)

    counted = _CALL.validate_python(_explore(messages))
    readings = counted.args_as_dict()["readings"]
    offered = _CALL.validate_python(_explore(_after(messages, counted)))
    [question] = offered.args_as_dict()["questions"]

    assert counted.tool_name == "propose_readings"
    assert [(r["label"], r["search_name"]) for r in readings] == [
        (FIRST_LABEL, SIGNAL_PEPTIDE),
        (SECOND_LABEL, "GenesByGeneType"),
    ]
    assert offered.tool_name == "consult_user"
    assert [o["label"] for o in question["options"]] == [FIRST_LABEL, SECOND_LABEL]
    assert question["allowNotes"] is False
    assert "hypothesis" in offered.args_as_dict()["reply"]


@pytest.mark.parametrize(
    "prompt",
    ["I prefer SignalP 6.0. Which genes carry a signal peptide? [[arc:explore]]"],
    indirect=True,
)
def test_a_stated_preference_is_remembered_before_the_card(prompt: str) -> None:
    counted = _CALL.validate_python(_explore(_asked(prompt)))

    kept = _CALL.validate_python(_explore(_after(_asked(prompt), counted)))

    assert kept.tool_name == "remember"
    assert kept.args_as_dict()["kind"] == "preference"


@pytest.mark.parametrize(
    "prompt",
    ["What is known about this family? [[arc:explore-no-reading]]"],
    indirect=True,
)
def test_a_reply_with_no_reading_is_text(prompt: str) -> None:
    assert _TEXT.validate_python(_explore(_asked(prompt))).content == NO_READING


@pytest.mark.parametrize(
    "prompt",
    ["Which genes carry a signal peptide? [[arc:explore-one-reading]]"],
    indirect=True,
)
def test_the_one_reading_arc_counts_it_then_names_build(prompt: str) -> None:
    messages = _asked(prompt)

    counted = _CALL.validate_python(_explore(messages))
    readings = counted.args_as_dict()["readings"]
    reply = _TEXT.validate_python(_explore(_after(messages, counted)))

    assert counted.tool_name == "propose_readings"
    assert [(r["label"], r["search_name"]) for r in readings] == [
        (FIRST_LABEL, SIGNAL_PEPTIDE)
    ]
    assert reply.content == ONE_READING
    assert "Build" in ONE_READING


@pytest.mark.parametrize("prompt", ["What does this search read?"], indirect=True)
def test_an_arc_with_no_explore_script_answers_with_the_echo(prompt: str) -> None:
    assert _TEXT.validate_python(_explore(_asked(prompt))).content == EXPLORE_ECHO


@pytest.mark.parametrize(
    "prompt", ["Which genes carry a signal peptide? [[arc:explore]]"], indirect=True
)
def test_the_lead_frames_the_picked_reading_on_a_thread_with_no_spec(
    prompt: str,
) -> None:
    card = scripted_call("consult_user", {"questions": [], "reply": "Pick one."})

    resumed = role_script("lead")(_after(_asked(prompt), card))

    assert resumed.tool_name == "frame_problem"
