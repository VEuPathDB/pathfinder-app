from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from assistant_core import quota
from assistant_core.platform.types import PaidBy
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.usage import RequestUsage, RunUsage
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph._lead_capture import _charge_token_delta, _LeadRunCapture
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import detached_session

_LUNA = "openai:gpt-5.6-luna"

_CALLS = (
    (30_603, 30_388, 0, 179),
    (34_011, 33_272, 0, 92),
    (34_181, 534, 33_272, 121),
    (34_476, 295, 33_806, 215),
)


def _request(
    input_tokens: int, cache_write: int, cache_read: int, output_tokens: int
) -> RequestUsage:
    response = ModelResponse(
        parts=[TextPart("ok")],
        usage=RequestUsage(
            input_tokens=input_tokens,
            cache_write_tokens=cache_write,
            cache_read_tokens=cache_read,
            output_tokens=output_tokens,
        ),
        model_name="gpt-5.6-luna",
        provider_name="openai",
        provider_url="https://api.openai.com/v1/",
    )
    response.usage.cost = response.cost().total_price
    return response.usage


@pytest.fixture
def charges(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, Decimal]]:
    seen: list[tuple[int, Decimal]] = []

    async def _accumulate(
        session: AsyncSession,
        *,
        user_id: Any,
        tokens: int,
        cost_usd: Decimal,
        paid_by: PaidBy,
    ) -> None:
        del session, user_id, paid_by
        seen.append((tokens, cost_usd))

    monkeypatch.setattr(quota, "accumulate", _accumulate)
    return seen


async def test_cache_tokens_inside_the_input_are_not_charged_again(
    charges: list[tuple[int, Decimal]],
) -> None:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Audit two gene models.",
    )
    context = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=detached_session,
        cancel_event=asyncio.Event(),
    )
    capture = _LeadRunCapture()
    capture.lead_model = _LUNA
    usage = RunUsage()

    for call in _CALLS:
        usage.incr(_request(*call))
        await _charge_token_delta(context, state, capture, usage, lambda _: None, _LUNA)

    assert charges == [
        (30_782, Decimal("0.0078548")),
        (34_103, Decimal("0.0085762")),
        (34_302, Decimal("0.00101914")),
        (34_691, Decimal("0.00108287")),
    ]
    assert capture.charged_tokens == 133_878
    assert capture.charged_cost == Decimal("0.01853301")
