from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters.values import MultiPickValue, StringValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.strategy_ast import StrategyAst
from veupathdb.domain.strategy.tree import walk
from veupathdb.wdk.factory import get_strategy_api

from pathfinder.domain.strategy.operations import (
    DeleteEdgeOp,
    DeleteEdgeResolution,
    DeleteResolution,
    DeleteStepOp,
)
from pathfinder.persistence.models import (
    ConversationStrategy,
    PersistedStrategyGraph,
    User,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.spec_build import build_strategy_from_spec

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_ORG = "Plasmodium falciparum 3D7"


def _text_leaf(step_id: str, expression: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByText",
        parameters={
            "text_expression": StringValue(value=expression),
            "text_fields": MultiPickValue(values=["product"]),
            "document_type": StringValue(value="gene"),
            "text_search_organism": MultiPickValue(values=[_ORG]),
        },
    )


def _combine(
    step_id: str, primary: StrategyStepNode, secondary: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="__combine__",
        operator=CombineOp.INTERSECT,
        primary_input=primary,
        secondary_input=secondary,
    )


@dataclass
class _BuiltConv:
    deps: StrategyMutationContext
    conv_id: object
    session_maker: async_sessionmaker[AsyncSession]


@pytest.fixture
async def built_nested_conv(
    require_wdk_creds: str,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[_BuiltConv]:
    del patch_app_db_engine, db_cleaner
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    created: list[int] = []
    user_id, conv_id = uuid4(), uuid4()
    async with session_maker() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conv_id,
                user_id=user_id,
                site_id="plasmodb",
                name="col",
            )
        )
        await session.commit()
    deps = StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=build_strategy_session(
            site_id="plasmodb",
            strategy_graph=PersistedStrategyGraph(
                id=str(conv_id), name="col", strategy_ast=None, wdk_strategy_id=None
            ),
        ),
        conversation_id=conv_id,
        db_session_factory=async_session_factory,
    )
    root = _combine(
        "narrowed",
        _combine(
            "text_or_go",
            _text_leaf("text_kinases", "kinase"),
            _text_leaf("go_kinase_genes", "protease"),
        ),
        _text_leaf("pf_taxon", "transporter"),
    )
    outcome = await build_strategy_from_spec(deps=deps, root=root, name="col")
    assert outcome.failed_steps == [], outcome.failed_steps
    assert outcome.wdk_strategy_id is not None
    created.append(outcome.wdk_strategy_id)
    try:
        yield _BuiltConv(deps=deps, conv_id=conv_id, session_maker=session_maker)
    finally:
        api = get_strategy_api("plasmodb")
        for sid in created:
            with contextlib.suppress(Exception):
                await api.delete_strategy(sid)
        veupathdb_auth_token_ctx.reset(reset)


async def _persisted_step_ids(built: _BuiltConv) -> list[str]:
    async with built.session_maker() as session:
        strategy = await session.get(ConversationStrategy, built.conv_id)
        assert strategy is not None
        ast = StrategyAst.model_validate(strategy.strategy_ast)
    return sorted(s.id for s in walk(ast.root))


async def test_collapse_delete_drops_step_and_combine_no_orphans(
    built_nested_conv: _BuiltConv,
) -> None:
    assert await _persisted_step_ids(built_nested_conv) == [
        "go_kinase_genes",
        "narrowed",
        "pf_taxon",
        "text_kinases",
        "text_or_go",
    ]

    await apply_and_commit(
        deps=built_nested_conv.deps,
        op=DeleteStepOp(
            step_id="pf_taxon", resolution=DeleteResolution.COLLAPSE_COMBINE
        ),
    )

    graph = built_nested_conv.deps.strategy_session.get_graph(None)
    assert graph is not None
    assert sorted(graph.steps.keys()) == [
        "go_kinase_genes",
        "text_kinases",
        "text_or_go",
    ]
    assert await _persisted_step_ids(built_nested_conv) == [
        "go_kinase_genes",
        "text_kinases",
        "text_or_go",
    ]


async def test_delete_edge_detaches_against_live_wdk(
    built_nested_conv: _BuiltConv,
) -> None:
    """Deleting an edge on the canvas used to 422 before reaching WDK.

    The operation kind existed only on the frontend, so the discriminated
    union rejected it and the optimistic apply rolled back. This drives the
    real commit pipeline: detach the root combine's secondary input and
    confirm the freed subtree survives while the strategy still pushes.
    """
    assert await _persisted_step_ids(built_nested_conv) == [
        "go_kinase_genes",
        "narrowed",
        "pf_taxon",
        "text_kinases",
        "text_or_go",
    ]

    await apply_and_commit(
        deps=built_nested_conv.deps,
        op=DeleteEdgeOp(
            source_id="pf_taxon",
            target_id="narrowed",
            slot="secondary",
            resolution=DeleteEdgeResolution.DETACH,
        ),
    )

    graph = built_nested_conv.deps.strategy_session.get_graph(None)
    assert graph is not None
    # Detach is not delete: pf_taxon stays, now as its own root.
    assert sorted(graph.steps.keys()) == [
        "go_kinase_genes",
        "narrowed",
        "pf_taxon",
        "text_kinases",
        "text_or_go",
    ]
    assert graph.steps["narrowed"].secondary_input_id is None
    assert graph.steps["narrowed"].operator is None
    assert graph.roots == {"narrowed", "pf_taxon"}


async def test_delete_edge_collapse_against_live_wdk(
    built_nested_conv: _BuiltConv,
) -> None:
    """Collapse resolves to the same shape the delete dialog produces."""
    await apply_and_commit(
        deps=built_nested_conv.deps,
        op=DeleteEdgeOp(
            source_id="narrowed",
            target_id="narrowed",
            slot="secondary",
            resolution=DeleteEdgeResolution.COLLAPSE,
        ),
    )

    graph = built_nested_conv.deps.strategy_session.get_graph(None)
    assert graph is not None
    assert sorted(graph.steps.keys()) == [
        "go_kinase_genes",
        "text_kinases",
        "text_or_go",
    ]
    assert await _persisted_step_ids(built_nested_conv) == [
        "go_kinase_genes",
        "text_kinases",
        "text_or_go",
    ]
