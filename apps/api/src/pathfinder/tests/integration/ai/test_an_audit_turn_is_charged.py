from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from assistant_core.persistence.models import MonthlyUsage
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import PaidBy
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.ai.audit.turn import charge_usage
from pathfinder.domain.provider_keys import ProviderKeyring
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_keys import attach_keyring
from pathfinder.tests.integration.http.conftest import make_user

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_OPENAI_KEY = ProviderKeyring(
    active={"openai": SecretStr("sk-proj-sentinel-0123456789WXYZ")}
)
_COST = Decimal("0.0125")


@pytest.fixture
def cloud_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_tier", "balanced", raising=False)


async def _user(session_maker: async_sessionmaker[AsyncSession]) -> UUID:
    async with session_maker() as session:
        return (await make_user(session)).id


async def _rows(user_id: UUID) -> dict[PaidBy, tuple[int, Decimal]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(MonthlyUsage).where(MonthlyUsage.user_id == user_id)
        )
        return {
            row.paid_by: (row.total_tokens, row.total_cost_usd)
            for row in result.scalars()
        }


@pytest.mark.usefixtures("cloud_provider")
async def test_an_audit_turn_is_one_row_on_the_auditors_payer(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    owner = await _user(session_maker)

    with attach_keyring(_OPENAI_KEY):
        await charge_usage(owner, 120, _COST)

    assert await _rows(owner) == {PaidBy.USER: (120, _COST)}


@pytest.mark.usefixtures("cloud_provider")
async def test_an_audit_turn_that_spent_nothing_writes_no_row(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    owner = await _user(session_maker)

    with attach_keyring(_OPENAI_KEY):
        await charge_usage(owner, 0, Decimal(0))

    assert await _rows(owner) == {}


async def test_a_mock_audit_turn_is_charged_by_the_mock_model(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    owner = await _user(session_maker)

    with attach_keyring(_OPENAI_KEY):
        await charge_usage(owner, 120, _COST)

    assert await _rows(owner) == {PaidBy.DEPLOYMENT: (120, _COST)}
