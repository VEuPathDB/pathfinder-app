from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.platform.types import PaidBy
from pydantic_ai.exceptions import ToolRetryError, UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryFeedbackPart,
    RetryInfo,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo

from strategist.ai.capabilities.metering import SpendMeter
from strategist.ai.explore import explore_model
from strategist.ai.graph import _lead_model, _lead_reading
from strategist.ai.graph._lead_capture import LeadRunCapture
from strategist.ai.graph._lead_stops import final_reply, strategy_change
from strategist.ai.graph.lead_node import _drive_lead_stream
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.domain.strategy.session import StrategySession
from strategist.tests._support.explore_turns import (
    EXPLORE_PROMPT,
    ExploreDoubles,
    explore_state,
    install_explore_doubles,
    run_explore,
)
from strategist.tests._support.scripted import scripted_with
from strategist.tests._support.scripted_reading import read_as
from strategist.tests._support.streamed_model import streamed
from strategist.tests.unit.ai.graph._approval_turn import (
    LEAD_FINAL,
    Collector,
    scripted_model,
    tool_calls,
)
from strategist.tests.unit.ai.graph.test_lead_turn_budget import _deps, _framed_state

_ANSWERED = "The columns are listed by record type."
_READER_REFUSAL = "goal: String should have at most 500 characters"
_READER_STOP = (
    "I could not read your message into its requirements: "
    f"{_READER_REFUSAL}. Nothing was changed. Send the message again."
)
_READER_TOKENS = 700
_SPENT = "Exceeded maximum output retries (1)"
_EMPTY = "Received empty model response"


_MISTYPED_CALLS = 4


def _mistyped_then_answered(messages: list[ModelMessage]) -> ToolCallPart:
    made = len(tool_calls(messages))
    if made < _MISTYPED_CALLS:
        return ToolCallPart(
            tool_name="list_record_columns",
            args={"record_type": 5},
            tool_call_id=f"call_columns_{made}",
        )
    return ToolCallPart(
        tool_name="final_result", args=LEAD_FINAL, tool_call_id="call_final"
    )


def _explored(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del info
    made = len(tool_calls(messages))
    if made < _MISTYPED_CALLS:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="list_record_columns",
                    args={"record_type": 5},
                    tool_call_id=f"call_columns_{made}",
                )
            ]
        )
    return ModelResponse(parts=[TextPart(_ANSWERED)])


def _lead_reply(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(
        _lead_model,
        "scripted",
        scripted_with(model=lambda: scripted_model(_mistyped_then_answered)),
    )
    writer: Any = Collector()
    state = _framed_state()
    deps = _deps(state, StrategySession(site_id="plasmodb"))
    capture = LeadRunCapture()
    asyncio.run(
        _drive_lead_stream(
            state=state,
            agent=build_lead_agent(),
            deps=deps,
            capture=capture,
            writer=writer,
            message_id=uuid4(),
        ),
    )
    reply = final_reply(
        capture, deps.unanswered_stage, change=strategy_change(deps.state)
    )
    assert reply is not None
    return reply.prose


def test_a_lead_tool_mistyped_on_every_call_never_stops_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_as(monkeypatch, "extend_strategy")

    prose = _lead_reply(monkeypatch)

    assert prose == LEAD_FINAL["prose"]


async def test_an_explore_tool_mistyped_on_every_call_never_stops_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doubles = install_explore_doubles(monkeypatch)
    monkeypatch.setattr(
        explore_model, "scripted", scripted_with(model=lambda: streamed(_explored))
    )

    await run_explore(explore_state(EXPLORE_PROMPT))

    assert doubles.replies() == [_ANSWERED]


def _reader_spends_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing(*_args: object, meter: SpendMeter, **_kwargs: object) -> None:
        meter.absorb(_READER_TOKENS, Decimal("0.002"), PaidBy.DEPLOYMENT)
        feedback = RetryFeedbackPart(
            content=_READER_REFUSAL, retry=RetryInfo(cause="model_retry")
        )
        raise UnexpectedModelBehavior(_SPENT) from ToolRetryError(feedback)

    async def no_classes(site_id: str) -> dict[str, str]:
        del site_id
        return {}

    monkeypatch.setattr(_lead_reading, "is_mock_deployment", lambda: False)
    monkeypatch.setattr(_lead_reading, "record_class_names", no_classes)
    monkeypatch.setattr(_lead_reading, "keyed_model", lambda model_id: model_id)
    monkeypatch.setattr(_lead_reading, "read_message", failing)


async def test_an_explore_turn_the_reader_failed_names_it_and_charges_it(
    monkeypatch: pytest.MonkeyPatch, doubles: ExploreDoubles
) -> None:
    _reader_spends_then_fails(monkeypatch)

    await run_explore(explore_state(EXPLORE_PROMPT))

    assert doubles.replies() == [_READER_STOP]
    assert [tokens for _, tokens in doubles.charges] == [_READER_TOKENS]


def test_a_lead_turn_the_reader_failed_names_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reader_spends_then_fails(monkeypatch)

    assert _lead_reply(monkeypatch) == _READER_STOP


@pytest.fixture
def doubles(monkeypatch: pytest.MonkeyPatch) -> ExploreDoubles:
    return install_explore_doubles(monkeypatch)


async def test_an_explore_turn_that_raises_still_charges_what_it_spent(
    monkeypatch: pytest.MonkeyPatch, doubles: ExploreDoubles
) -> None:
    _reader_spends_then_fails(monkeypatch)

    async def broken(*_args: object, meter: SpendMeter, **_kwargs: object) -> None:
        meter.absorb(_READER_TOKENS, Decimal("0.002"), PaidBy.DEPLOYMENT)
        raise UnexpectedModelBehavior(_EMPTY)

    monkeypatch.setattr(_lead_reading, "read_message", broken)

    with pytest.raises(UnexpectedModelBehavior, match=_EMPTY):
        await run_explore(explore_state(EXPLORE_PROMPT))

    assert [tokens for _, tokens in doubles.charges] == [_READER_TOKENS]
