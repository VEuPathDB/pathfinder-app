"""The spend of a model run beside the Lead, and the usage row that records it.

The thread title and the notes compaction run on the key that pays for their
provider, so each run is charged on that payer's row.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from assistant_core import quota
from assistant_core.cost import cost_for_run
from assistant_core.platform.db import DBSessionFactory
from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import PaidBy
from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, WrapRunHandler
from pydantic_ai.run import AgentRunResult
from sqlalchemy.exc import SQLAlchemyError

from pathfinder.platform.model_keys import turn_paid_by

logger = get_logger(__name__)

__all__ = ["ModelSpend", "SpendMeter", "charge_spend"]


@dataclass(frozen=True)
class ModelSpend:
    """What one run spent, and who paid for it."""

    tokens: int
    cost_usd: Decimal
    paid_by: PaidBy


@dataclass
class SpendMeter:
    """The runs one caller metered, in the order they ended."""

    spent: list[ModelSpend] = field(default_factory=list)

    def on(self, model_id: str) -> AbstractCapability[Any]:
        """The capability that meters each run of an agent on ``model_id``."""
        return _MeteredRuns(model_id=model_id, spent=self.spent)

    @property
    def tokens(self) -> int:
        return sum(spend.tokens for spend in self.spent)

    @property
    def cost_usd(self) -> Decimal:
        return sum((spend.cost_usd for spend in self.spent), Decimal(0))


@dataclass
class _MeteredRuns(AbstractCapability[Any]):
    """Records the usage of every run, a run that fails included."""

    model_id: str
    spent: list[ModelSpend]

    async def wrap_run(
        self,
        ctx: RunContext[Any],
        *,
        handler: WrapRunHandler,
    ) -> AgentRunResult[Any]:
        try:
            return await handler()
        finally:
            self.spent.append(
                ModelSpend(
                    tokens=ctx.usage.total_tokens,
                    cost_usd=cost_for_run(
                        usage=ctx.usage,
                        model_name=ctx.model.model_name,
                        provider_name=ctx.model.system,
                        provider_url=ctx.model.base_url,
                    ),
                    paid_by=turn_paid_by(self.model_id),
                )
            )


async def charge_spend(
    session_factory: DBSessionFactory,
    *,
    user_id: UUID,
    spent: Sequence[ModelSpend],
) -> None:
    """Add each run to the row of its payer. A database refusal is logged."""
    if not spent:
        return
    try:
        async with session_factory() as session:
            for spend in spent:
                await quota.accumulate(
                    session,
                    user_id=user_id,
                    tokens=spend.tokens,
                    cost_usd=spend.cost_usd,
                    paid_by=spend.paid_by,
                )
            await session.commit()
    except SQLAlchemyError:
        logger.warning(
            "failed to charge a model run beside the turn", user_id=str(user_id)
        )
