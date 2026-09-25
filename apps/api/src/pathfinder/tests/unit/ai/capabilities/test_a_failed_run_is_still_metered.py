"""A run beside the Lead that fails is still metered for what it spent."""

from __future__ import annotations

from decimal import Decimal

import pytest
from assistant_core.platform.types import PaidBy
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.capabilities.metering import ModelSpend, SpendMeter


def _answers_prose(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del messages, info
    return ModelResponse(parts=[TextPart(content="not a number")])


async def test_a_run_whose_output_never_validates_is_recorded() -> None:
    meter = SpendMeter()
    agent = Agent(
        FunctionModel(_answers_prose),
        output_type=int,
        retries=0,
        capabilities=[meter.on("openai:gpt-5.6-luna")],
    )

    with pytest.raises(UnexpectedModelBehavior):
        await agent.run("how many kinases")

    assert meter.spent == [
        ModelSpend(tokens=56, cost_usd=Decimal(0), paid_by=PaidBy.DEPLOYMENT)
    ]
