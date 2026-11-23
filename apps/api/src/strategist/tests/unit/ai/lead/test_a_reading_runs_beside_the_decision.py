from __future__ import annotations

import asyncio

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb_mcp.catalog import DecisionRequest, DecisionResponse

from strategist.ai.capabilities.metering import SpendMeter
from strategist.ai.lead.message_reader import read_message
from strategist.tests.unit.ai.lead.test_a_message_is_read_before_the_lead import (
    READ,
    STATED,
    _answer,
    _Decisions,
    _Model,
)


class _SlowDecisions(_Decisions):
    def __init__(
        self,
        order: list[str],
        modeled: asyncio.Event,
        *answers: DecisionResponse | None,
    ) -> None:
        super().__init__(*answers)
        self.order = order
        self.modeled = modeled

    async def __call__(self, request: DecisionRequest) -> DecisionResponse | None:
        await asyncio.wait_for(self.modeled.wait(), timeout=10)
        self.order.append("decided")
        return await super().__call__(request)


async def test_the_model_reading_starts_before_the_decision_answers() -> None:
    order: list[str] = []
    modeled = asyncio.Event()
    ask = _SlowDecisions(order, modeled, _answer(("none", 0.4), ("status", 0.4)), None)
    script = _Model(STATED, {"effect": "add", "wants": "nothing"})

    def _recorded(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "effect" in info.output_tools[0].parameters_json_schema["properties"]:
            order.append("modeled")
            modeled.set()
        return script(messages, info)

    reading, _ = await read_message(
        READ,
        model=FunctionModel(_recorded),
        model_id="openai:gpt-5.6-luna",
        meter=SpendMeter(),
        ask=ask,
    )

    assert order.index("modeled") < order.index("decided")
    assert (reading.effect, reading.read_by) == ("add", "model")


async def test_a_reading_the_decision_settles_first_is_metered_before_the_return() -> (
    None
):
    order: list[str] = []
    modeled = asyncio.Event()
    ask = _SlowDecisions(
        order,
        modeled,
        _answer(("change", 0.95), ("status", 0.9)),
        _answer(("change", 0.93), ("status", 0.88)),
    )
    script = _Model(STATED)

    async def _unanswered(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        if "effect" in info.output_tools[0].parameters_json_schema["properties"]:
            modeled.set()
            await asyncio.Event().wait()
        return script(messages, info)

    meter = SpendMeter()
    reading, _ = await read_message(
        READ,
        model=FunctionModel(_unanswered),
        model_id="openai:gpt-5.6-luna",
        meter=meter,
        ask=ask,
    )

    assert (reading.read_by, len(meter.spent)) == ("decisions", 2)
