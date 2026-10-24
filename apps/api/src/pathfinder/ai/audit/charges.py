from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.quota import accumulate
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

from pathfinder.ai.capabilities.metering import RunPricing
from pathfinder.platform.model_keys import turn_paid_by


async def charge(
    user_id: UUID, tokens: int, cost_usd: Decimal, *, model_id: str
) -> None:
    if tokens == 0 and cost_usd == 0:
        return
    async with async_session_factory() as session:
        await accumulate(
            session,
            user_id=user_id,
            tokens=tokens,
            cost_usd=cost_usd,
            paid_by=turn_paid_by(model_id),
        )
        await session.commit()


async def charge_run(
    user_id: UUID, usage: RunUsage, model: Model, *, model_id: str
) -> None:
    cost = RunPricing.of(model).cost(usage)
    await charge(user_id, usage.total_tokens, cost, model_id=model_id)
