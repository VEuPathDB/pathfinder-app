from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    walk,
)
from veupathdb.wdk import get_strategy_api, walk_wdk_step_tree

from pathfinder.domain.strategy.operations import (
    DeleteResolution,
    DeleteStepOp,
    GraphOperation,
    UpdateCombineOperatorOp,
    UpdateStepParamsOp,
)
from pathfinder.persistence.models import PersistedStrategyGraph, User
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.strategy_ops import apply_operation
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.gene_set_refresh import (
    refresh_the_strategy_gene_set,
)
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.tests.integration.strategies.conftest import (
    ORGANISM,
    go_term_leaf,
    text_leaf,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITE = "plasmodb"
_SIGNAL = "GenesWithSignalPeptide"


@dataclass
class _Thread:
    user_id: UUID
    conv_id: UUID
    wdk_strategy_id: int
    session_maker: async_sessionmaker[AsyncSession]

    async def stored(self) -> StrategyAst:
        async with self.session_maker() as session:
            strategy = await ConversationRepository(session).get_strategy(self.conv_id)
        assert strategy.strategy_ast is not None
        return StrategyAst.model_validate(strategy.strategy_ast)

    async def apply(self, op: GraphOperation) -> None:
        async with self.session_maker() as session:
            await apply_operation(
                ConversationRepository(session),
                self.conv_id,
                self.user_id,
                site_id=_SITE,
                op=op,
            )


def _five_steps() -> StrategyStepNode:
    signal = StrategyStepNode(
        id="signal",
        search_name=_SIGNAL,
        parameters={
            "organism": MultiPickValue(values=[ORGANISM]),
            "signalp_version": SinglePickValue(value="SignalP-6.0"),
        },
    )
    inner = StrategyStepNode(
        id="inner",
        search_name="__combine__",
        primary_input=text_leaf("kinase"),
        secondary_input=go_term_leaf("GO:0016301"),
        operator=CombineOp.UNION,
    )
    return StrategyStepNode(
        id="outer",
        search_name="__combine__",
        primary_input=inner,
        secondary_input=signal,
        operator=CombineOp.UNION,
    )


@pytest.fixture
async def thread(
    require_wdk_creds: str,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[_Thread]:
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
                name="Signal peptide kinases",
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
                    name="Signal peptide kinases",
                    strategy_ast=None,
                    wdk_strategy_id=None,
                ),
            ),
            conversation_id=conv_id,
            db_session_factory=async_session_factory,
        ),
        root=_five_steps(),
    )
    assert outcome.failed_steps == [], outcome.failed_steps
    assert outcome.wdk_strategy_id is not None
    try:
        yield _Thread(user_id, conv_id, outcome.wdk_strategy_id, session_maker)
    finally:
        with contextlib.suppress(Exception):
            await get_strategy_api(_SITE).delete_strategy(outcome.wdk_strategy_id)
        veupathdb_auth_token_ctx.reset(reset)


def _ids_by_search(ast: StrategyAst) -> dict[str, str]:
    return {node.search_name: node.id for node in walk(ast.root)}


@pytest.mark.parametrize("delete_after_seconds", [0.0, 0.05, 0.1, 0.15, 0.2, 0.3])
async def test_a_delete_beside_a_refresh_leaves_the_tree_the_thread_stores(
    thread: _Thread, delete_after_seconds: float
) -> None:
    built = await thread.stored()
    ids = _ids_by_search(built)
    inner = next(
        node.id
        for node in walk(built.root)
        if node.primary_input is not None and node.id != built.root.id
    )
    await thread.apply(
        UpdateStepParamsOp(
            step_id=ids["GenesByText"],
            parameters={"text_expression": StringValue(value="protein kinase")},
        )
    )
    await thread.apply(
        UpdateCombineOperatorOp(step_id=inner, operator=CombineOp.INTERSECT)
    )

    async def _delete() -> None:
        await asyncio.sleep(delete_after_seconds)
        await thread.apply(
            DeleteStepOp(
                step_id=ids[_SIGNAL], resolution=DeleteResolution.COLLAPSE_COMBINE
            )
        )

    await asyncio.gather(
        refresh_the_strategy_gene_set(conversation_id=thread.conv_id, site_id=_SITE),
        _delete(),
    )

    stored = await thread.stored()
    site = await get_strategy_api(_SITE).get_strategy(thread.wdk_strategy_id)
    wdk_ids = stored.wdk_step_ids or {}
    stored_root = wdk_ids[stored.root.id]
    stored_steps = {wdk_ids[node.id] for node in walk(stored.root)}
    site_steps = {node.step_id for node in walk_wdk_step_tree(site.step_tree)}
    assert (site.root_step_id, site_steps) == (stored_root, stored_steps)
    assert len(site_steps) == 3
