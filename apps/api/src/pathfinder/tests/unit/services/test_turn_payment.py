from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.types import PaidBy
from assistant_core.quota import QuotaStatus
from fastapi import HTTPException
from pydantic import JsonValue, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.turn_payment import TurnPayment
from pathfinder.transport.http import deps

_RESETS = datetime(2026, 11, 1, tzinfo=UTC)
_SPENT = QuotaStatus(
    used_usd=Decimal("2.000000"),
    limit_usd=Decimal("2.0"),
    total_tokens=900,
    percent=1.0,
    resets_at=_RESETS,
)


def _paying(budget: QuotaStatus | None) -> object:
    async def payment(
        session: AsyncSession, user_id: UUID, model_ids: Iterable[str]
    ) -> TurnPayment:
        del session, user_id, model_ids
        return TurnPayment(payers={"openai": PaidBy.DEPLOYMENT}, budget=budget)

    return payment


async def test_a_used_budget_answers_the_same_429_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps, "turn_payment", _paying(_SPENT))

    with pytest.raises(HTTPException) as caught:
        await deps.require_turn_paid(AsyncSession(), uuid4(), ["openai:x"])

    assert caught.value.status_code == 429
    assert TypeAdapter(dict[str, JsonValue]).validate_python(caught.value.detail) == {
        "code": "monthly_quota_exhausted",
        "usedUsd": "2.000000",
        "limitUsd": "2.0",
        "resetsAt": _RESETS.isoformat(),
        "totalTokens": 900,
    }


async def test_a_turn_inside_its_budget_answers_its_payers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps, "turn_payment", _paying(None))

    payers = await deps.require_turn_paid(AsyncSession(), uuid4(), ["openai:x"])

    assert payers == {"openai": PaidBy.DEPLOYMENT}
