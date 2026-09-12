from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import (
    MultiPickValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode
from veupathdb.wdk import (
    get_results_api,
    get_strategy_api,
)
from veupathdb_mcp.wdk import (
    build_snapshot_from_wdk,
    canonicalize_synced_parameters,
)

from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.persistence.models import PersistedStrategyGraph, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.spec_build import build_strategy_from_spec


@dataclass
class RoundTrip:
    outcome: BuildOutcome
    decoded: StrategyAst
    wdk_strategy_id: int


BuildAndRead = Callable[[StrategyStepNode], Awaitable[RoundTrip]]
BuildRaw = Callable[[StrategyStepNode], Awaitable[BuildOutcome]]

ORGANISM = "Plasmodium falciparum 3D7"


def text_leaf(expression: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="leaf",
        search_name="GenesByText",
        parameters={
            "text_expression": StringValue(value=expression),
            "text_fields": MultiPickValue(values=["product"]),
            "document_type": StringValue(value="gene"),
            "text_search_organism": MultiPickValue(values=[ORGANISM]),
        },
    )


def go_term_leaf(go_id: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="go",
        search_name="GenesByGoTerm",
        parameters={
            "organism": MultiPickValue(values=[ORGANISM]),
            "go_term_evidence": MultiPickValue(values=["Curated", "Computed"]),
            "go_term_slim": SinglePickValue(value="No"),
            "go_typeahead": MultiPickValue(values=[go_id]),
            "go_term": StringValue(value=go_id),
        },
    )


async def step_gene_ids(rt: RoundTrip) -> tuple[int, set[str]]:
    assert rt.decoded.wdk_step_ids
    step = next(iter(rt.decoded.wdk_step_ids.values()))
    answer = await get_results_api("plasmodb").get_step_preview(step, limit=50000)
    return step, {r.display_name for r in answer.records}


@pytest.fixture
def wdk_session(
    require_wdk_creds: str,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> Generator[None]:
    """Act on WDK as the registered account (no build machinery)."""
    del patch_app_db_engine, db_cleaner
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@pytest.fixture
async def wdk_builder(
    require_wdk_creds: str,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[BuildAndRead]:
    del patch_app_db_engine, db_cleaner
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    created: list[int] = []

    async def build_and_read(root: StrategyStepNode) -> RoundTrip:
        async with session_maker() as session:
            user_id, conv_id = uuid4(), uuid4()
            session.add(User(id=user_id))
            session.add(
                Conversation(
                    assistant_id=PATHFINDER_ASSISTANT_ID,
                    id=conv_id,
                    user_id=user_id,
                    site_id="plasmodb",
                    name="rt",
                )
            )
            await session.commit()
        strategy_session = build_strategy_session(
            site_id="plasmodb",
            strategy_graph=PersistedStrategyGraph(
                id=str(conv_id), name="rt", strategy_ast=None, wdk_strategy_id=None
            ),
        )
        outcome = await build_strategy_from_spec(
            deps=StrategyMutationContext(
                site_id="plasmodb",
                strategy_session=strategy_session,
                conversation_id=conv_id,
                db_session_factory=async_session_factory,
            ),
            root=root,
            name="rt",
        )
        assert outcome.failed_steps == [], outcome.failed_steps
        assert outcome.wdk_strategy_id is not None
        created.append(outcome.wdk_strategy_id)
        api = get_strategy_api("plasmodb")
        saved = await api.get_strategy(outcome.wdk_strategy_id)
        ast, wire = build_snapshot_from_wdk(saved)
        await canonicalize_synced_parameters(ast, api, wire)
        return RoundTrip(
            outcome=outcome, decoded=ast, wdk_strategy_id=outcome.wdk_strategy_id
        )

    try:
        yield build_and_read
    finally:
        api = get_strategy_api("plasmodb")
        for sid in created:
            with contextlib.suppress(Exception):
                await api.delete_strategy(sid)
        veupathdb_auth_token_ctx.reset(reset)


@pytest.fixture
async def wdk_build_raw(
    require_wdk_creds: str,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[BuildRaw]:
    del patch_app_db_engine, db_cleaner
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    created: list[int] = []

    async def build_raw(root: StrategyStepNode) -> BuildOutcome:
        async with session_maker() as session:
            user_id, conv_id = uuid4(), uuid4()
            session.add(User(id=user_id))
            session.add(
                Conversation(
                    assistant_id=PATHFINDER_ASSISTANT_ID,
                    id=conv_id,
                    user_id=user_id,
                    site_id="plasmodb",
                    name="rt-raw",
                )
            )
            await session.commit()
        strategy_session = build_strategy_session(
            site_id="plasmodb",
            strategy_graph=PersistedStrategyGraph(
                id=str(conv_id), name="rt-raw", strategy_ast=None, wdk_strategy_id=None
            ),
        )
        outcome = await build_strategy_from_spec(
            deps=StrategyMutationContext(
                site_id="plasmodb",
                strategy_session=strategy_session,
                conversation_id=conv_id,
                db_session_factory=async_session_factory,
            ),
            root=root,
            name="rt-raw",
        )
        if outcome.wdk_strategy_id is not None:
            created.append(outcome.wdk_strategy_id)
        return outcome

    try:
        yield build_raw
    finally:
        api = get_strategy_api("plasmodb")
        for sid in created:
            with contextlib.suppress(Exception):
                await api.delete_strategy(sid)
        veupathdb_auth_token_ctx.reset(reset)
