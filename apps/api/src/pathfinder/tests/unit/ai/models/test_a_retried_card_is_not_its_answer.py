from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from pathfinder.ai.models.mock.consult_arc import CONSULT, since_the_answer


def test_a_retried_card_is_not_its_answer() -> None:
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="Find kinases")]),
        ModelResponse(parts=[ToolCallPart(CONSULT, {}, tool_call_id="c1")]),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    CONSULT, "Field required", tool_call_id="c1", outcome="retried"
                )
            ]
        ),
    ]

    assert since_the_answer(messages) == messages
