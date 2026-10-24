"""Who pays for each provider a run of models names, and the monthly budget it would spend past."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from assistant_core import quota
from assistant_core.platform.types import ModelProvider, PaidBy
from assistant_core.quota import QuotaStatus
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.provider_keys import key_statuses, require_payers
from pathfinder.services.users import effective_monthly_limit_usd


@dataclass(frozen=True, kw_only=True)
class TurnPayment:
    payers: dict[ModelProvider, PaidBy]
    budget: QuotaStatus | None


async def turn_payment(
    session: AsyncSession, user_id: UUID, model_ids: Iterable[str]
) -> TurnPayment:
    payers = require_payers(model_ids, await key_statuses(session, user_id))
    if PaidBy.DEPLOYMENT not in payers.values():
        return TurnPayment(payers=payers, budget=None)
    status_now = await quota.get_current(
        session,
        user_id,
        limit_usd=await effective_monthly_limit_usd(session, user_id),
    )
    used = status_now.used_usd >= status_now.limit_usd
    return TurnPayment(payers=payers, budget=status_now if used else None)
