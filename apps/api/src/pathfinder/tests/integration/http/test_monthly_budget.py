"""The runtime counts the cost; this application decides the budget.

The arithmetic is ``assistant_core.quota``. What is pinned here is the limit
this application passes it and what the two callers do with the answer.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from assistant_core import quota
from fastapi import FastAPI, HTTPException
from pydantic import JsonValue, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.platform.config import get_settings
from pathfinder.services.users import effective_monthly_limit_usd
from pathfinder.tests.integration.http.conftest import client_for, make_user
from pathfinder.transport.http.deps import require_quota_available

_OK = 200
_TOO_MANY = 429


async def test_a_user_with_no_override_is_held_to_the_configured_default(
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)

    limit = await effective_monthly_limit_usd(db_session, user.id)

    assert limit == Decimal(
        str(get_settings().pathfinder_user_monthly_cost_limit_usd),
    )


async def test_the_account_override_is_the_budget(
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)
    user.monthly_cost_limit_usd = 4.0
    await db_session.commit()

    assert await effective_monthly_limit_usd(db_session, user.id) == Decimal(4)


async def test_the_quota_route_reports_the_spend_against_that_budget(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)
    user.monthly_cost_limit_usd = 4.0
    await db_session.commit()
    await quota.accumulate(
        db_session,
        user_id=user.id,
        tokens=1200,
        cost_usd=Decimal("1.5"),
    )
    await db_session.commit()

    async with client_for(app, user.id) as client:
        response = await client.get("/api/v1/me/quota")

    assert response.status_code == _OK
    body = response.json()
    assert body["usedUsd"] == "1.500000"
    assert body["limitUsd"] == "4.0"
    assert body["totalTokens"] == 1200
    assert body["percent"] == 0.375


async def test_a_user_who_spent_the_budget_is_refused_with_the_numbers(
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    """The 429 is this application's, and it names what was spent."""
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)
    user.monthly_cost_limit_usd = 2.0
    await db_session.commit()
    await quota.accumulate(
        db_session,
        user_id=user.id,
        tokens=900,
        cost_usd=Decimal("2.0"),
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as caught:
        await require_quota_available(db_session, user.id)

    assert caught.value.status_code == _TOO_MANY
    detail = TypeAdapter(dict[str, JsonValue]).validate_python(caught.value.detail)
    assert detail == {
        "code": "monthly_quota_exhausted",
        "usedUsd": "2.000000",
        "limitUsd": "2.0",
        "resetsAt": quota.next_period_start().isoformat(),
        "totalTokens": 900,
    }


async def test_a_user_inside_the_budget_passes_the_gate(
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)
    user.monthly_cost_limit_usd = 2.0
    await db_session.commit()
    await quota.accumulate(
        db_session,
        user_id=user.id,
        tokens=10,
        cost_usd=Decimal("1.99"),
    )
    await db_session.commit()

    assert await require_quota_available(db_session, user.id) == user.id
