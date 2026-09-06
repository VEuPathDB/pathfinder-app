"""Usage is attributed per application; the monthly cap stays per user."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.context import application_id_ctx
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select

from pathfinder.persistence.models import MonthlyUsage, User
from pathfinder.services import quota

HOME = "pathfinder"
OTHER = "companion"


@pytest.fixture
def under_home() -> Iterator[None]:
    token = application_id_ctx.set(HOME)
    yield
    application_id_ctx.reset(token)


async def _seed_user(user_id: UUID) -> None:
    async with async_session_factory() as session:
        session.add(User(id=user_id, monthly_cost_limit_usd=10.0))
        await session.commit()


async def _accumulate(application_id: str, user_id: UUID, cost: str) -> None:
    token = application_id_ctx.set(application_id)
    try:
        async with async_session_factory() as session:
            await quota.accumulate(
                session,
                user_id=user_id,
                tokens=100,
                cost_usd=Decimal(cost),
            )
            await session.commit()
    finally:
        application_id_ctx.reset(token)


@pytest.mark.asyncio
async def test_each_application_gets_its_own_usage_row(
    db_cleaner: None,
    patch_app_db_engine: None,
    under_home: None,
) -> None:
    del db_cleaner, patch_app_db_engine, under_home
    user_id = uuid4()
    await _seed_user(user_id)

    await _accumulate(HOME, user_id, "1.50")
    await _accumulate(OTHER, user_id, "2.25")

    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(MonthlyUsage).where(MonthlyUsage.user_id == user_id),
                )
            )
            .scalars()
            .all()
        )

    by_application = {row.application_id: row.total_cost_usd for row in rows}
    assert by_application == {HOME: Decimal("1.50"), OTHER: Decimal("2.25")}


@pytest.mark.asyncio
async def test_the_cap_sums_every_application_of_one_user(
    db_cleaner: None,
    patch_app_db_engine: None,
    under_home: None,
) -> None:
    del db_cleaner, patch_app_db_engine, under_home
    user_id = uuid4()
    await _seed_user(user_id)

    await _accumulate(HOME, user_id, "1.50")
    await _accumulate(OTHER, user_id, "2.25")

    async with async_session_factory() as session:
        status = await quota.get_current(session, user_id)

    assert status.used_usd == Decimal("3.75")
    assert status.total_tokens == 200
    assert status.limit_usd == Decimal("10.0")


@pytest.mark.asyncio
async def test_a_second_charge_from_one_application_adds_to_its_own_row(
    db_cleaner: None,
    patch_app_db_engine: None,
    under_home: None,
) -> None:
    del db_cleaner, patch_app_db_engine, under_home
    user_id = uuid4()
    await _seed_user(user_id)

    await _accumulate(OTHER, user_id, "1.00")
    await _accumulate(OTHER, user_id, "0.50")

    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(MonthlyUsage).where(MonthlyUsage.user_id == user_id),
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0].total_cost_usd == Decimal("1.50")
