"""Every seed of one run saves its thread and its control set, however they interleave."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.wdk import StrategyAPI, WDKIdentifier, WDKStrategyDetails

from pathfinder.persistence.models import ControlSet, User
from pathfinder.services.experiment.seed import runner
from pathfinder.services.experiment.seed.types import SeedComplete, SeedDef

_SITE = "plasmodb"
_SEEDS = 6


def _interleaving_api() -> StrategyAPI:
    """A site that mints a new strategy per call and yields between every call."""
    minted = itertools.count(9100)

    async def _create_strategy(**_kwargs: object) -> WDKIdentifier:
        await asyncio.sleep(0)
        return WDKIdentifier(id=next(minted))

    async def _get_strategy(strategy_id: int) -> WDKStrategyDetails:
        await asyncio.sleep(0)
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": strategy_id,
                "rootStepId": strategy_id,
                "name": "minted here",
                "stepTree": {"stepId": strategy_id},
                "steps": {
                    str(strategy_id): {
                        "id": strategy_id,
                        "searchName": "GenesByTaxon",
                        "searchConfig": {"parameters": {}},
                        "estimatedSize": 3,
                    }
                },
                "recordClassName": "transcript",
            }
        )

    api = Mock(spec=StrategyAPI)
    api.create_step = AsyncMock(return_value=WDKIdentifier(id=5001))
    api.create_strategy = AsyncMock(side_effect=_create_strategy)
    api.get_strategy = AsyncMock(side_effect=_get_strategy)
    return api


def _seed(n: int) -> SeedDef:
    return SeedDef.model_validate(
        {
            "name": f"seeded kinases {n}",
            "description": "a seeded strategy",
            "site_id": _SITE,
            "record_type": "transcript",
            "step_tree": {"id": "step_a", "searchName": "GenesByTaxon"},
            "control_set": {
                "name": f"kinase controls {n}",
                "positive_ids": [f"PF3D7_010{n}100"],
                "negative_ids": [],
                "provenance_notes": "curated for the test",
            },
        }
    )


@pytest.fixture
async def seed_user(
    session_maker: async_sessionmaker[AsyncSession], db_cleaner: None
) -> AsyncGenerator[User]:
    del db_cleaner
    async with session_maker() as session:
        user = User(id=uuid4())
        session.add(user)
        await session.commit()
        yield user


async def test_every_seed_saves_its_control_set(
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _interleaving_api()
    monkeypatch.setattr(runner, "get_strategy_api", lambda _site: site)
    monkeypatch.setattr(
        runner, "get_seeds_for_site", lambda _site: [_seed(n) for n in range(_SEEDS)]
    )

    events = [
        event
        async for event in runner.run_seed(
            user_id=seed_user.id, session_factory=session_maker, site_id=_SITE
        )
    ]

    done = events[-1]
    assert isinstance(done, SeedComplete)
    assert (done.strategies_created, done.control_sets_created, done.failed) == (
        _SEEDS,
        _SEEDS,
        0,
    )
    async with session_maker() as session:
        saved = await session.scalar(
            select(func.count())
            .select_from(ControlSet)
            .where(ControlSet.user_id == seed_user.id)
        )
    assert saved == _SEEDS


async def test_a_run_of_every_site_seeds_only_the_sites_served(
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unserved = _seed(9).model_copy(update={"site_id": "piroplasmadb"})
    monkeypatch.setattr(runner, "get_strategy_api", lambda _site: _interleaving_api())
    monkeypatch.setattr(runner, "get_all_seeds", lambda: [_seed(0), unserved])
    monkeypatch.setattr(runner, "served_site_ids", lambda: frozenset({_SITE}))

    events = [
        event
        async for event in runner.run_seed(
            user_id=seed_user.id, session_factory=session_maker
        )
    ]

    done = events[-1]
    assert isinstance(done, SeedComplete)
    assert (done.total, done.strategies_created, done.failed) == (1, 1, 0)
