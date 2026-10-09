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

_HAIKU = "anthropic:claude-haiku-5-5"


def _request(input_tokens: int, output_tokens: int) -> RequestUsage:
    response = ModelResponse(
        parts=[TextPart("ok")],
        usage=RequestUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        model_name="claude-haiku-5-5",
        provider_name="anthropic",
        provider_url="https://api.anthropic.com",
    )
    response.usage.cost = response.cost().total_price
    return response.usage


@pytest.fixture
def charges(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Decimal, PaidBy]]:
    seen: list[tuple[Decimal, PaidBy]] = []

    async def _accumulate(
        session: AsyncSession,
        *,
        user_id: Any,
        tokens: int,
        cost_usd: Decimal,
        paid_by: PaidBy,
    ) -> None:
        del session, user_id, tokens
        seen.append((cost_usd, paid_by))

    monkeypatch.setattr(quota, "accumulate", _accumulate)
    return seen


async def test_each_haiku_request_is_charged_at_the_tier_its_own_prompt_reaches(
    charges: list[tuple[Decimal, PaidBy]],
) -> None:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Find kinases.",
    )
    context = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=detached_session,
        cancel_event=asyncio.Event(),
    )
    capture = _LeadRunCapture()
    capture.lead_model = _HAIKU
    usage = RunUsage()

    for input_tokens in (80_000, 80_000, 150_000):
        usage.incr(_request(input_tokens, 1_000))
        await _charge_token_delta(
            context, state, capture, usage, lambda _: None, _HAIKU
        )

    assert charges == [
        (Decimal("0.0085"), PaidBy.DEPLOYMENT),
        (Decimal("0.0085"), PaidBy.DEPLOYMENT),
        (Decimal("0.0775"), PaidBy.DEPLOYMENT),
    ]
    assert capture.charged_cost == Decimal("0.0945")
