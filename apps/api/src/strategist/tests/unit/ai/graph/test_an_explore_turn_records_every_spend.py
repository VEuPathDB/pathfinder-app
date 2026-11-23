from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import pytest
from assistant_core.platform.types import PaidBy
from pydantic import SecretStr
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb_mcp.catalog import (
    DecisionRequest,
    DecisionResponse,
    DecisionUsage,
    use_decisions_transport,
)

from strategist.ai.capabilities import decisions_spend
from strategist.ai.capabilities.decisions_spend import decision_cost, send_decision
from strategist.ai.capabilities.metering import ModelSpend, SpendMeter
from strategist.ai.graph import _lead_reading, explore_node
from strategist.ai.lead.message_reader import (
    ReaderInput,
    decide_reading,
    read_message,
)
from strategist.domain.message_reading import MessageReading, StatedRequest
from strategist.tests._support.decisions_wire import DecisionsWire, recorded_decision
from strategist.tests._support.explore_turns import (
    EXPLORE_PROMPT,
    explore_state,
    install_explore_doubles,
    run_explore,
)

_RECORDED = recorded_decision("interpro_pick.json")


async def test_a_decision_the_explore_reader_asks_is_charged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_explore_doubles(monkeypatch)
    wire = DecisionsWire(_RECORDED["response"])
    monkeypatch.setattr(
        decisions_spend,
        "keyed_provider",
        lambda model: (wire.build("openai", SecretStr("sk-test")), PaidBy.USER),
    )
    use_decisions_transport(send_decision)
    charged: list[ModelSpend] = []

    async def charge(
        session_factory: object, *, user_id: UUID, spent: list[ModelSpend]
    ) -> None:
        del session_factory, user_id
        charged.extend(spent)

    async def reading(*_args: object, **_kwargs: object) -> tuple[Any, ...]:
        await decide_reading(DecisionRequest.model_validate(_RECORDED["request"]))
        reading = MessageReading(effect="none", wants="nothing", read_by="model")
        return reading, StatedRequest()

    async def no_classes(site_id: str) -> dict[str, str]:
        del site_id
        return {}

    monkeypatch.setattr(explore_node, "charge_spend", charge)
    monkeypatch.setattr(_lead_reading, "is_mock_deployment", lambda: False)
    monkeypatch.setattr(_lead_reading, "record_class_names", no_classes)
    monkeypatch.setattr(_lead_reading, "keyed_model", lambda model_id: model_id)
    monkeypatch.setattr(_lead_reading, "read_message", reading)

    await run_explore(explore_state(EXPLORE_PROMPT))

    tokens = DecisionResponse.model_validate(_RECORDED["response"]).usage.input_tokens
    decided = ModelSpend(
        tokens=tokens,
        cost_usd=decision_cost(DecisionUsage(input_tokens=tokens)),
        paid_by=PaidBy.USER,
    )
    assert decided in charged


class _SlowReading:
    def __init__(self) -> None:
        self.reading = asyncio.Event()

    async def __call__(
        self, messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        del messages
        if "effect" in str(info.model_request_parameters.output_object):
            self.reading.set()
            await asyncio.sleep(30)
        return ModelResponse(parts=[TextPart(json.dumps({"goal": "kinases"}))])


async def test_a_cancelled_model_reading_still_leaves_its_spend() -> None:
    slow = _SlowReading()
    meter = SpendMeter()

    async def settled(request: DecisionRequest) -> DecisionResponse:
        del request
        await slow.reading.wait()
        answers = [
            {
                "type": "choice",
                "name": name,
                "choice": picked,
                "probabilities": [{"value": picked, "probability": 0.99}],
                "confidence": 0.99,
            }
            for name, picked in (
                ("effect", "none"),
                ("wants", "nothing"),
                ("edit_direction", "other"),
            )
        ]
        return DecisionResponse.model_validate({"answers": answers})

    await read_message(
        ReaderInput(conversation="", strategy="", message="kinases"),
        model=FunctionModel(slow),
        model_id="openai:gpt-5.6-luna",
        meter=meter,
        ask=settled,
    )

    assert len(meter.spent) == 2
