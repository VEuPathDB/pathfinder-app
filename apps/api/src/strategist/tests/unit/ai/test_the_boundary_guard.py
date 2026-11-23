from __future__ import annotations

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryFeedbackPart,
    RetryInfo,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition

from strategist.tests._support.boundary_guard import (
    foreign_in_request,
    guard_the_model_boundary,
)
from strategist.tests._support.tool_names import served_tool_names


def _offering(*names: str) -> ModelRequestParameters:
    return ModelRequestParameters(
        function_tools=[ToolDefinition(name=name) for name in names]
    )


def _asked(text: str) -> list[ModelMessage]:
    return [ModelRequest(parts=[UserPromptPart(text)], instructions=text)]


def _answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del messages, info
    return ModelResponse(parts=[TextPart("done")])


@pytest.mark.foreign_tool_names("the test drives the guard itself")
async def test_the_guard_fails_a_name_the_request_does_not_offer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused = guard_the_model_boundary(monkeypatch)
    agent: Agent[None, str] = Agent(
        FunctionModel(_answer), instructions="call `create_eda_step` next"
    )

    with pytest.raises(AssertionError, match="create_eda_step"):
        await agent.run("go")

    assert refused == [
        (
            "A model request names tools it does not offer: "
            "[\"instructions names ['create_eda_step']\"]"
        )
    ]


def test_an_allowed_sentence_passes_the_guard() -> None:
    text = "- `remember`: the message asks to keep something for future conversations."

    assert foreign_in_request(_asked(text), _offering()) == []


def test_the_guard_passes_a_name_the_request_offers() -> None:
    found = foreign_in_request(
        _asked("call `create_eda_step` next"), _offering("create_eda_step")
    )

    assert found == []


def test_the_guard_reads_only_parts_new_since_the_last_response() -> None:
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart("export it")]),
        ModelResponse(parts=[ToolCallPart("create_eda_step", {}, "c1")]),
        ModelRequest(
            parts=[ToolReturnPart("create_eda_step", "create_eda_step done", "c1")]
        ),
        ModelResponse(parts=[TextPart("exported")]),
        ModelRequest(parts=[UserPromptPart("thanks")]),
    ]

    assert foreign_in_request(history, _offering()) == []


@pytest.mark.parametrize("served", [True, False])
def test_a_research_name_counts_only_when_served(served: bool) -> None:
    names = sorted(served_tool_names())
    text = f"search with {names[0]}"

    found = foreign_in_request(_asked(text), _offering(*(names if served else [])))

    assert (found == []) is served


def test_the_guard_reads_a_retry_that_answers_no_call() -> None:
    history: list[ModelMessage] = [
        ModelRequest(
            parts=[
                RetryFeedbackPart(
                    content="call `create_eda_step` now",
                    retry=RetryInfo(cause="model_retry"),
                )
            ]
        )
    ]

    assert foreign_in_request(history, _offering()) == [
        "retry feedback names ['create_eda_step']"
    ]


def test_the_guard_reads_a_retry_that_answers_a_call() -> None:
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart("export it")]),
        ModelResponse(parts=[ToolCallPart("set_eda_filters", {}, "c1")]),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    "set_eda_filters",
                    "call `create_eda_step` now",
                    "c1",
                    outcome="retried",
                )
            ]
        ),
    ]

    assert foreign_in_request(history, _offering("set_eda_filters")) == [
        "retry of set_eda_filters names ['create_eda_step']"
    ]
