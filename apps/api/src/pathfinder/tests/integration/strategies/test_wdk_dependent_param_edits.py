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
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.domain.strategy import StrategyAst
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
from pathfinder.tests.integration.strategies.conftest import go_term_leaf

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]


@dataclass
class _BuiltGo:
    deps: StrategyMutationContext
    conv_id: object
    session_maker: async_sessionmaker[AsyncSession]


@pytest.fixture
async def built_go_conv(
    require_wdk_creds: str,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[_BuiltGo]:
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
                name="go",
            )
        )
        await session.commit()
    deps = StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=build_strategy_session(
            site_id="plasmodb",
            strategy_graph=PersistedStrategyGraph(
                id=str(conv_id), name="go", strategy_ast=None, wdk_strategy_id=None
            ),
        ),
        conversation_id=conv_id,
        db_session_factory=async_session_factory,
    )
    outcome = await build_strategy_from_spec(deps=deps, root=go_term_leaf("GO:0004672"))
    assert outcome.failed_steps == [], outcome.failed_steps
    assert outcome.wdk_strategy_id is not None
    created.append(outcome.wdk_strategy_id)
    try:
        yield _BuiltGo(deps=deps, conv_id=conv_id, session_maker=session_maker)
    finally:
        api = get_strategy_api("plasmodb")
        for sid in created:
            with contextlib.suppress(Exception):
                await api.delete_strategy(sid)
        veupathdb_auth_token_ctx.reset(reset)


async def _persisted_params(built: _BuiltGo) -> dict[str, ParamValue]:
    async with built.session_maker() as session:
        strategy = await session.get(ConversationStrategy, built.conv_id)
        assert strategy is not None
        ast = StrategyAst.model_validate(strategy.strategy_ast)
    return dict(ast.root.parameters)


async def test_edit_branch_organism_canonicalizes_and_preserves_go_params(
    built_go_conv: _BuiltGo,
) -> None:
    await apply_and_commit(
        deps=built_go_conv.deps,
        op=UpdateStepParamsOp(
            step_id="go",
            parameters={"organism": MultiPickValue(values=["Plasmodium falciparum"])},
        ),
    )
    params = await _persisted_params(built_go_conv)
    organism = params["organism"]
    assert isinstance(organism, MultiPickValue)
    assert organism.values != ["Plasmodium falciparum"]
    assert all("Plasmodium falciparum " in v for v in organism.values)
    assert len(organism.values) >= 10
    assert "go_typeahead" in params
    assert "go_term_evidence" in params
    assert "go_term_slim" in params


async def test_edit_dependent_param_to_invalid_value_is_rejected(
    built_go_conv: _BuiltGo,
) -> None:
    with pytest.raises(ValidationError):
        await apply_and_commit(
            deps=built_go_conv.deps,
            op=UpdateStepParamsOp(
                step_id="go",
                parameters={"go_term_slim": SinglePickValue(value="Maybe")},
            ),
        )


async def test_edit_go_term_to_different_valid_term_persists(
    built_go_conv: _BuiltGo,
) -> None:
    await apply_and_commit(
        deps=built_go_conv.deps,
        op=UpdateStepParamsOp(
            step_id="go",
            parameters={
                "go_typeahead": MultiPickValue(values=["GO:0016301"]),
                "go_term": StringValue(value="GO:0016301"),
            },
        ),
    )
    params = await _persisted_params(built_go_conv)
    typeahead = params["go_typeahead"]
    assert isinstance(typeahead, MultiPickValue)
    assert typeahead.values == ["GO:0016301"]
    assert "organism" in params
