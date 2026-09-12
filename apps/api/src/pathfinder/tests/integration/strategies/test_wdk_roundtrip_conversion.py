"""Live WDK round-trip: organism multi-pick survives build → read → decode.

Gated on WDK_TEST_EMAIL/WDK_TEST_PASSWORD (skipped when unset).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StrategyStepNode, walk
from veupathdb.wdk import get_strategy_api
from veupathdb_mcp.wdk import (
    build_snapshot_from_wdk,
    canonicalize_synced_parameters,
)

from pathfinder.persistence.models import PersistedStrategyGraph, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.spec_build import build_strategy_from_spec

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_ORGANISM = "Plasmodium falciparum 3D7"


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


async def test_organism_multipick_survives_wdk_roundtrip(
    require_wdk_creds: str,
    patch_app_db_engine: None,
    db_session: AsyncSession,
) -> None:
    del patch_app_db_engine

    user_id = uuid4()
    conv_id = uuid4()
    db_session.add(User(id=user_id))
    db_session.add(
        Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            id=conv_id,
            user_id=user_id,
            site_id="plasmodb",
            name="rt",
        )
    )
    await db_session.commit()

    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    wdk_strategy_id: int | None = None
    try:
        session = build_strategy_session(
            site_id="plasmodb",
            strategy_graph=PersistedStrategyGraph(
                id=str(conv_id), name="rt", strategy_ast=None, wdk_strategy_id=None
            ),
        )
        root = StrategyStepNode(
            id="g1",
            search_name="GenesByTaxon",
            parameters={"organism": MultiPickValue(values=[_ORGANISM])},
        )
        outcome = await build_strategy_from_spec(
            deps=StrategyMutationContext(
                site_id="plasmodb",
                strategy_session=session,
                conversation_id=conv_id,
                db_session_factory=async_session_factory,
            ),
            root=root,
            name="rt",
        )
        assert outcome.failed_steps == [], outcome.failed_steps
        wdk_strategy_id = outcome.wdk_strategy_id
        assert wdk_strategy_id is not None

        api = get_strategy_api("plasmodb")
        saved = await api.get_strategy(wdk_strategy_id)
        ast, wire_by_step_id = build_snapshot_from_wdk(saved)

        leaf_wire = next(
            params for params in wire_by_step_id.values() if "organism" in params
        )
        assert leaf_wire["organism"] != "", (
            f"WDK returned an empty organism wire value: {leaf_wire!r}"
        )

        await canonicalize_synced_parameters(ast, api, wire_by_step_id)
        leaf = next(s for s in walk(ast.root) if s.search_name == "GenesByTaxon")
        assert leaf.parameters.get("organism") == MultiPickValue(values=[_ORGANISM])
    finally:
        if wdk_strategy_id is not None:
            await get_strategy_api("plasmodb").delete_strategy(wdk_strategy_id)
        veupathdb_auth_token_ctx.reset(reset)
