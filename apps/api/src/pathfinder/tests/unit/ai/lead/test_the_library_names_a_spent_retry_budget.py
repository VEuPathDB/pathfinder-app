from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelRetry, UnexpectedModelBehavior

from pathfinder.ai.lead.phase_stop import PhaseStopReason
from pathfinder.ai.lead.sub_agent_stops import (
    ToolRefusal,
    early_stop,
    spent_its_output_retries,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    endless_tool_call_model,
    final_result_model,
)

_REFUSAL = "Name another search."


class _Answer(BaseModel):
    count: int


def _refuse() -> str:
    raise ModelRetry(_REFUSAL)


def _spent(agent: Agent[None, _Answer]) -> UnexpectedModelBehavior:
    with pytest.raises(UnexpectedModelBehavior) as raised:
        asyncio.run(agent.run("Answer."))
    return raised.value


def test_a_spent_output_budget_is_named_in_the_words_the_stop_reads() -> None:
    agent = Agent(final_result_model({"count": "many"}), output_type=_Answer, retries=3)

    spent = _spent(agent)

    assert spent.message == "Exceeded maximum output retries (3)"
    assert spent_its_output_retries(spent) is True
    stop = early_stop(spent, None)
    assert stop is not None
    assert (stop.reason, stop.refusal) == (PhaseStopReason.OUTPUT_RETRIES, None)


def test_a_spent_tool_budget_is_named_in_the_words_the_stop_reads() -> None:
    agent = Agent(
        endless_tool_call_model("_refuse"),
        output_type=_Answer,
        tools=[_refuse],
        retries=3,
    )
    refusal = ToolRefusal(tool_name="_refuse", text=_REFUSAL)

    spent = _spent(agent)

    assert spent.message.startswith(
        "Tool '_refuse' exceeded max retries count of 3. Consider raising the retry "
        "limit"
    )
    stop = early_stop(spent, refusal)
    assert stop is not None
    assert (stop.reason, stop.refusal) == (PhaseStopReason.TOOL_RETRIES, refusal)


def test_another_fault_of_the_class_is_no_stop() -> None:
    fault = UnexpectedModelBehavior("Received empty model response")
    refusal = ToolRefusal(tool_name="_refuse", text=_REFUSAL)

    assert (
        fault.message,
        spent_its_output_retries(fault),
        early_stop(fault, refusal),
    ) == ("Received empty model response", False, None)
