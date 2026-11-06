from __future__ import annotations

from typing import Literal

from pydantic_ai.messages import FunctionToolResultEvent, ToolReturnPart

from pathfinder.ai.lead.sub_agent_stops import ToolRefusal, refusal_of


def _result(
    content: object, outcome: Literal["success", "retried"] = "retried"
) -> FunctionToolResultEvent:
    return FunctionToolResultEvent(
        part=ToolReturnPart(
            tool_name="set_criterion",
            content=content,
            tool_call_id="c1",
            outcome=outcome,
        )
    )


def test_a_retry_in_words_is_quoted() -> None:
    assert refusal_of(_result("Name another search.")) == ToolRefusal(
        tool_name="set_criterion", text="Name another search."
    )


def test_a_retry_on_the_arguments_names_each_message() -> None:
    errors = [
        {"type": "missing", "loc": ["value"], "msg": "Field required"},
        {"type": "string_type", "loc": ["param"], "msg": "Input should be a string"},
    ]

    assert refusal_of(_result(errors)) == ToolRefusal(
        tool_name="set_criterion",
        text="Field required; Input should be a string",
    )


def test_an_answered_call_is_no_refusal() -> None:
    assert [refusal_of(_result("bound", outcome="success"))] == [None]
