"""The runtime counts the cost; this application decides the budget and the payer.

The arithmetic is ``assistant_core.quota``. What is pinned here is the limit
this application passes it, which spend that limit caps, and what the chat
gate does with a turn nobody may pay for.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import pytest
from assistant_core import quota
from assistant_core.persistence.models import Message
from assistant_core.platform.types import PaidBy
from fastapi import FastAPI, HTTPException
from procrastinate.testing import InMemoryConnector
from pydantic import JsonValue, SecretStr, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.provider_keys import KeyRefusal
from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ProviderNotConfiguredError
from pathfinder.services.provider_keys import record_refusals, store_key
from pathfinder.services.users import effective_monthly_limit_usd
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.http.conftest import (
    chat_body,
    chat_jobs,
    client_for,
    make_user,
)
from pathfinder.transport.http.deps import require_turn_paid

_OK = 200
_TOO_MANY = 429
_LUNA = "openai:gpt-5.6-luna"
_OPUS = "anthropic:claude-opus-5"
_KEY = "sk-ant-sentinel-0123456789WXYZ"


@pytest.fixture
def _sealed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with sealed_provider_keys(monkeypatch):
        yield


async def _spent(session: AsyncSession, limit: float, spent: str, tokens: int) -> User:
    user = await make_user(session)
    user.monthly_cost_limit_usd = limit
    await session.commit()
    await quota.accumulate(
        session,
        user_id=user.id,
        tokens=tokens,
        cost_usd=Decimal(spent),
        paid_by=PaidBy.DEPLOYMENT,
    )
    await session.commit()
    return user


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


@pytest.mark.usefixtures("_sealed")
async def test_the_quota_route_reports_the_allowance_and_the_own_key_spend_apart(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)
    user.monthly_cost_limit_usd = 4.0
    await store_key(db_session, user.id, "anthropic", SecretStr(_KEY))
    for paid_by, tokens, cost in (
        (PaidBy.DEPLOYMENT, 1200, "1.5"),
        (PaidBy.USER, 900, "3.4"),
    ):
        await quota.accumulate(
            db_session,
            user_id=user.id,
            tokens=tokens,
            cost_usd=Decimal(cost),
            paid_by=paid_by,
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
    assert (body["ownKeyUsd"], body["ownKeyTokens"]) == ("3.400000", 900)
    assert body["ownKeyProviders"] == ["anthropic"]


async def test_a_spent_allowance_refuses_a_turn_the_deployment_pays_for(
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    """The 429 is this application's, and it names what was spent."""
    del patch_app_db_engine, db_cleaner
    user = await _spent(db_session, 2.0, "2.0", 900)

    with pytest.raises(HTTPException) as caught:
        await require_turn_paid(db_session, user.id, [_LUNA])

    assert caught.value.status_code == _TOO_MANY
    detail = TypeAdapter(dict[str, JsonValue]).validate_python(caught.value.detail)
    assert detail == {
        "code": "monthly_quota_exhausted",
        "usedUsd": "2.000000",
        "limitUsd": "2.0",
        "resetsAt": quota.next_period_start().isoformat(),
        "totalTokens": 900,
    }


async def test_a_user_inside_the_allowance_passes_the_gate(
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await _spent(db_session, 2.0, "1.99", 10)

    assert await require_turn_paid(db_session, user.id, [_LUNA]) == {
        "openai": PaidBy.DEPLOYMENT
    }


@pytest.mark.usefixtures("_sealed")
async def test_a_spent_allowance_admits_a_turn_the_researchers_keys_pay_for(
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await _spent(db_session, 2.0, "2.0", 900)
    await store_key(db_session, user.id, "anthropic", SecretStr(_KEY))
    await db_session.commit()

    assert await require_turn_paid(db_session, user.id, [_OPUS]) == {
        "anthropic": PaidBy.USER
    }
    with pytest.raises(HTTPException):
        await require_turn_paid(db_session, user.id, [_OPUS, _LUNA])


async def test_a_provider_nobody_pays_for_is_refused(
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "openai_api_key", "sk-deployment")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    user = await make_user(db_session)

    with pytest.raises(ProviderNotConfiguredError) as caught:
        await require_turn_paid(db_session, user.id, [_LUNA, _OPUS])

    assert caught.value.status == 422
    assert caught.value.detail == (
        "This deployment holds no Anthropic key and you have not added one. "
        "Add yours in Settings, under Provider keys, or choose a model of "
        "another provider."
    )


@pytest.mark.usefixtures("_sealed", "signed_in_to_veupathdb")
async def test_a_refused_key_refuses_the_turn_before_it_is_stored(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)
    await store_key(db_session, user.id, "openai", SecretStr(_KEY))
    await db_session.commit()
    await record_refusals(user.id, {"openai": KeyRefusal.INVALID})
    conversation_id = uuid4()

    async with client_for(app, user.id) as client:
        response = await client.post("/api/v1/chat", json=chat_body(conversation_id))

    assert response.status_code == 409
    assert response.json()["code"] == "PROVIDER_KEY_REFUSED"
    assert _KEY not in response.text
    messages = await db_session.scalar(select(func.count()).select_from(Message))
    assert (messages, chat_jobs(in_memory_jobs)) == (0, [])
