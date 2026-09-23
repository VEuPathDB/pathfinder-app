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
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode
from veupathdb.errors import ValidationError
from veupathdb.wdk import get_strategy_api

from pathfinder.domain.strategy.operations import UpdateStepParamsOp
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


def _text_leaf(text_fields: list[str], organism: list[str]) -> StrategyStepNode:
    return StrategyStepNode(
        id="leaf",
        search_name="GenesByText",
        parameters={
            "text_expression": StringValue(value="kinase"),
            "text_fields": MultiPickValue(values=text_fields),
            "document_type": StringValue(value="gene"),
            "text_search_organism": MultiPickValue(values=organism),
        },
    )


@dataclass
class _BuiltConv:
    deps: StrategyMutationContext
    conv_id: object
    session_maker: async_sessionmaker[AsyncSession]


@pytest.fixture
async def built_text_conv(
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
                name="opval",
            )
        )
        await session.commit()
    deps = StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=build_strategy_session(
            site_id="plasmodb",
            strategy_graph=PersistedStrategyGraph(
                id=str(conv_id), name="opval", strategy_ast=None, wdk_strategy_id=None
            ),
        ),
        conversation_id=conv_id,
        db_session_factory=async_session_factory,
    )
    outcome = await build_strategy_from_spec(
        deps=deps, root=_text_leaf(["product"], [_ORG])
    )
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


async def _persisted_leaf_params(
    built: _BuiltConv,
) -> dict[str, ParamValue]:
    async with built.session_maker() as session:
        strategy = await session.get(ConversationStrategy, built.conv_id)
        assert strategy is not None
        ast = StrategyAst.model_validate(strategy.strategy_ast)
    return dict(ast.root.parameters)


async def test_operation_with_invalid_param_value_is_rejected(
    built_text_conv: _BuiltConv,
) -> None:
    bad = {
        "text_expression": StringValue(value="kinase"),
        "text_fields": MultiPickValue(values=["not_a_real_field"]),
        "document_type": StringValue(value="gene"),
        "text_search_organism": MultiPickValue(values=[_ORG]),
    }
    with pytest.raises(ValidationError, match="text_fields"):
        await apply_and_commit(
            deps=built_text_conv.deps,
            op=UpdateStepParamsOp(step_id="leaf", parameters=bad),
        )


async def test_operation_canonicalizes_branch_organism_to_leaves(
    built_text_conv: _BuiltConv,
) -> None:
    branch = {
        "text_expression": StringValue(value="kinase"),
        "text_fields": MultiPickValue(values=["product"]),
        "document_type": StringValue(value="gene"),
        "text_search_organism": MultiPickValue(values=["Plasmodium falciparum"]),
    }
    await apply_and_commit(
        deps=built_text_conv.deps,
        op=UpdateStepParamsOp(step_id="leaf", parameters=branch),
    )
    params = await _persisted_leaf_params(built_text_conv)
    organism = params["text_search_organism"]
    assert isinstance(organism, MultiPickValue)
    assert organism.values != ["Plasmodium falciparum"]
    assert all("Plasmodium falciparum " in v for v in organism.values)
    assert len(organism.values) >= 10
