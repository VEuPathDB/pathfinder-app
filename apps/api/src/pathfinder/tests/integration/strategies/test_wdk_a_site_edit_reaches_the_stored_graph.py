"""A value set on PlasmoDB itself is the value the stored graph holds next.

The step is written on the site with the client, the way the site's own
revise form writes it. The count refresh and the canvas commit both read it
back before they store a count or plan an edit.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import to_wire
from veupathdb.domain.strategy import StrategyAst
from veupathdb.wdk import WDKSearchConfig, get_strategy_api

from pathfinder.domain.strategy.operations import UpdateStepMetaOp
from pathfinder.persistence.models import (
    ConversationStrategy,
    PersistedStrategyGraph,
    User,
)
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.strategy_ops import (
    apply_operation,
    refresh_counts,
)
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.tests.integration.strategies.conftest import text_leaf

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITE = "plasmodb"
_EXPRESSION = "text_expression"


@dataclass
class _Built:
    user_id: UUID
    conv_id: UUID
    wdk_strategy_id: int
    wdk_step_id: int
    session_maker: async_sessionmaker[AsyncSession]

    async def stored(self) -> StrategyAst:
        async with self.session_maker() as session:
            strategy = await session.get(ConversationStrategy, self.conv_id)
            assert strategy is not None
            return StrategyAst.model_validate(strategy.strategy_ast)


@pytest.fixture
async def built(
    require_wdk_creds: str,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[_Built]:
    """A one-step kinase strategy PathFinder built, then revised on the site."""
    del patch_app_db_engine, db_cleaner
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    user_id, conv_id = uuid4(), uuid4()
    async with session_maker() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conv_id,
                user_id=user_id,
                site_id=_SITE,
                name="kinases",
            )
        )
        await session.commit()
    outcome = await build_strategy_from_spec(
        deps=StrategyMutationContext(
            site_id=_SITE,
            strategy_session=build_strategy_session(
                site_id=_SITE,
                strategy_graph=PersistedStrategyGraph(
                    id=str(conv_id),
                    name="kinases",
                    strategy_ast=None,
                    wdk_strategy_id=None,
                ),
            ),
            conversation_id=conv_id,
            db_session_factory=async_session_factory,
        ),
        root=text_leaf("kinase"),
        name="kinases",
    )
    assert outcome.failed_steps == [], outcome.failed_steps
    assert outcome.wdk_strategy_id is not None
    api = get_strategy_api(_SITE)
    try:
        held = await api.get_strategy(outcome.wdk_strategy_id)
        step = held.steps[str(held.root_step_id)]
        await api.update_step_search_config(
            step_id=step.id,
            search_config=WDKSearchConfig(
                parameters={
                    **step.search_config.parameters,
                    _EXPRESSION: "protease",
                }
            ),
            record_type="transcript",
            search_name=step.search_name,
        )
        yield _Built(
            user_id=user_id,
            conv_id=conv_id,
            wdk_strategy_id=outcome.wdk_strategy_id,
            wdk_step_id=step.id,
            session_maker=session_maker,
        )
    finally:
        with contextlib.suppress(Exception):
            await api.delete_strategy(outcome.wdk_strategy_id)
        veupathdb_auth_token_ctx.reset(reset)


async def _site_value(built: _Built) -> str:
    step = await get_strategy_api(_SITE).find_step(built.wdk_step_id)
    return step.search_config.parameters[_EXPRESSION]


async def test_the_refresh_stores_the_sites_value_beside_the_sites_count(
    built: _Built,
) -> None:
    async with built.session_maker() as session:
        await refresh_counts(
            ConversationRepository(session),
            built.conv_id,
            built.user_id,
            site_id=_SITE,
        )

    stored = await built.stored()
    held = await get_strategy_api(_SITE).get_strategy(built.wdk_strategy_id)
    size = held.steps[str(built.wdk_step_id)].estimated_size
    assert to_wire(stored.root.parameters[_EXPRESSION]) == "protease"
    assert (stored.step_counts or {})[stored.root.id] == size


async def test_a_canvas_rename_leaves_the_sites_value_on_the_site(
    built: _Built,
) -> None:
    async with built.session_maker() as session:
        await apply_operation(
            ConversationRepository(session),
            built.conv_id,
            built.user_id,
            site_id=_SITE,
            op=UpdateStepMetaOp(step_id="leaf", display_name="proteases"),
        )

    stored = await built.stored()
    assert await _site_value(built) == "protease"
    assert to_wire(stored.root.parameters[_EXPRESSION]) == "protease"
    assert stored.root.display_name == "proteases"
