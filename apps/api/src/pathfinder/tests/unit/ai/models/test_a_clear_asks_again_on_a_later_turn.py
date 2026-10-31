"""A clear asks again on a later turn, whatever an earlier clear was answered."""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from pathfinder.ai.models.mock.registry import arc_named

_CLEAR = "Clear the current strategy by calling clear_strategy with confirm=true."


def _answered(call: ToolCallPart, content: str) -> list[ModelMessage]:
    return [
        ModelResponse(parts=[call]),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name=call.tool_name,
                    content=content,
                    tool_call_id=call.tool_call_id,
                )
            ]
        ),
    ]


def test_a_second_clear_asks_again_after_the_first_was_denied() -> None:
    classified = scripted_call(
        "classify_user_intent", {"intent": {"classification": "edit_strategy"}}
    )
    denied_turn: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=_CLEAR)]),
        *_answered(classified, "{}"),
        *_answered(scripted_call("clear_strategy", {"confirm": True}), "denied"),
        ModelResponse(parts=[scripted_call("final_result", {"prose": "unchanged"})]),
    ]
    later_turn: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=_CLEAR)]),
        *_answered(classified, "{}"),
    ]

    call = arc_named("clear").lead([*denied_turn, *later_turn])

    assert call.tool_name == "clear_strategy"
