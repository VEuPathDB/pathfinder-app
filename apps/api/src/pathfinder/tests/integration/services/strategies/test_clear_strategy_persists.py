"""Clearing the strategy has to reach the database.

``clear_strategy`` emptied the in-memory graph and returned. Nothing wrote the
conversation row, so the next read rebuilt the strategy the user had just
asked the agent to throw away - and the WDK strategy id stayed attached to it.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation
from pydantic_ai.exceptions import ModelRetry
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters.values import MultiPickValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.graph_model import flatten_tree
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.conversation import clear_strategy
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.persistence.models import (
    ConversationStrategy,
    PersistedStrategyGraph,
    User,
)
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.sync_state import WDKSyncState


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


def _leaf(step_id: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByTaxon",
        parameters={"organism": MultiPickValue(values=["Pf3D7"])},
    )


async def _seed(db_session: AsyncSession, user: User) -> Any:
    conv_id = uuid4()
    ast = StrategyAst(record_type="transcript", root=_leaf("step_a"))
    db_session.add(
        Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            id=conv_id,
            user_id=user.id,
            site_id="plasmodb",
            name="c",
        )
    )
    await db_session.flush()
    db_session.add(
        ConversationStrategy(
            conversation_id=conv_id,
            strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
            wdk_strategy_id=555,
            step_count=1,
        )
    )
    await db_session.commit()
    return conv_id


def _ctx(
    conv_id: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> Any:
    session = build_strategy_session(
        site_id="plasmodb",
        strategy_graph=PersistedStrategyGraph(
            id=str(conv_id), name="c", strategy_ast=None, wdk_strategy_id=555
        ),
    )
    graph = StrategyGraph(graph_id=str(conv_id), name="c", site_id="plasmodb")
    graph.record_type = "transcript"
    node = _leaf("step_a")
    graph.steps.update(flatten_tree(node))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={"step_a": 100}, wdk_strategy_id=555)
    ctx = MagicMock()
    ctx.tool_call_id = "call_1"
    ctx.deps = AgentDeps(
        site_id="plasmodb",
        strategy_session=session,
        conversation_id=conv_id,
        db_session_factory=db_session_factory,
    )
    return ctx


async def test_clearing_wipes_the_persisted_strategy(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
) -> None:
    conv_id = await _seed(db_session, seed_user)
    ctx = _ctx(conv_id, session_maker)

    await clear_strategy(ctx, confirm=True)

    async with session_maker() as fresh:
        strategy = await ConversationRepository(fresh).get_strategy(conv_id)
        assert not strategy.strategy_ast
        assert strategy.step_count == 0
        assert strategy.wdk_strategy_id is None


async def test_refusing_without_confirmation_leaves_the_row_alone(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
) -> None:
    conv_id = await _seed(db_session, seed_user)
    ctx = _ctx(conv_id, session_maker)

    with pytest.raises(ModelRetry):
        await clear_strategy(ctx, confirm=False)

    async with session_maker() as fresh:
        refetched = await ConversationRepository(fresh).get_strategy(conv_id)
        assert refetched.strategy_ast
        assert refetched.wdk_strategy_id == 555
