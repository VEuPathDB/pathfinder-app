"""A caller that mints a strategy and then adopts it states the claim.

The gold-strategy builder and the seed runner both create the VEuPathDB
strategy before the thread exists, so the adoption cannot read the claim off
the site.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.wdk import StrategyAPI, WDKIdentifier, WDKStrategyDetails

from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.saved_strategy import SavedStrategyRepository
from pathfinder.services.eval import build_gold_strategy
from pathfinder.services.experiment.seed import runner
from pathfinder.services.experiment.seed.types import SeedDef

_SITE = "plasmodb"
_GOLD_STRATEGY = 9001
_SEED_STRATEGY = 9002
_STEP = 5001


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


def _minting_api(strategy_id: int) -> StrategyAPI:
    """A site that accepts one step, one strategy, and reads it back."""
    api = Mock(spec=StrategyAPI)
    api.create_step = AsyncMock(return_value=WDKIdentifier(id=_STEP))
    api.create_strategy = AsyncMock(return_value=WDKIdentifier(id=strategy_id))
    api.get_step_answer = AsyncMock(return_value=Mock(records=[]))
    api.get_strategy = AsyncMock(
        return_value=WDKStrategyDetails.model_validate(
            {
                "strategyId": strategy_id,
                "rootStepId": _STEP,
                "name": "minted here",
                "stepTree": {"stepId": _STEP},
                "steps": {
                    str(_STEP): {
                        "id": _STEP,
                        "searchName": "GenesByTaxon",
                        "searchConfig": {"parameters": {}},
                        "estimatedSize": 3,
                    }
                },
                "recordClassName": "transcript",
            }
        )
    )
    return api


def _step_tree() -> dict[str, object]:
    return {
        "id": "step_a",
        "searchName": "GenesByTaxon",
        "recordType": "transcript",
        "parameters": {},
    }


def _seed() -> SeedDef:
    return SeedDef.model_validate(
        {
            "name": "seeded kinases",
            "description": "a seeded strategy",
            "site_id": _SITE,
            "record_type": "transcript",
            "step_tree": _step_tree(),
            "control_set": {
                "name": "kinase controls",
                "positive_ids": ["PF3D7_0100100"],
                "negative_ids": [],
                "provenance_notes": "curated for the test",
            },
        }
    )


async def _provenance(
    session_maker: async_sessionmaker[AsyncSession], conv_id: UUID
) -> bool:
    async with session_maker() as verify:
        row = await ConversationRepository(verify).get_strategy(conv_id)
    return row.wdk_strategy_created_here


async def test_a_gold_strategy_thread_claims_the_strategy_it_minted(
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    patch_app_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine
    monkeypatch.setattr(
        "pathfinder.services.eval.get_strategy_api",
        lambda _site: _minting_api(_GOLD_STRATEGY),
    )

    result = await build_gold_strategy(
        gold_id="gold-1",
        site_id=_SITE,
        record_type="transcript",
        step_tree=_step_tree(),
        user_id=seed_user.id,
    )

    assert result.wdk_strategy_id == _GOLD_STRATEGY
    assert result.conversation_id is not None
    assert await _provenance(session_maker, result.conversation_id) is True


async def test_a_seeded_thread_claims_the_strategy_it_minted(
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner, "get_strategy_api", lambda _site: _minting_api(_SEED_STRATEGY)
    )
    monkeypatch.setattr(runner, "get_seeds_for_site", lambda _site: [_seed()])

    async for _event in runner.run_seed(
        user_id=seed_user.id, session_factory=session_maker, site_id=_SITE
    ):
        pass

    async with session_maker() as verify:
        found = await SavedStrategyRepository(verify).get_by_wdk_strategy_id(
            seed_user.id, _SEED_STRATEGY
        )
    assert found is not None
    assert found[1].wdk_strategy_created_here is True
