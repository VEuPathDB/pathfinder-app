"""The Lead's rename reaches the stored thread, its stored strategy and WDK."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStrategyDetails

from pathfinder.ai.tools.standalone.strategy_rename import rename_strategy
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies import live_counts, naming
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import StubAPI

_OLD = "Kinase hunt"
_NEW = "UAT signal peptide screen"
_WDK_STRATEGY_ID = 555
_WDK_ROOT_ID = 100
_ROOT_COUNT = 116


class _Site(StubAPI):
    """A site that records each rename and answers the root's count."""

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": strategy_id,
                "name": _NEW,
                "rootStepId": _WDK_ROOT_ID,
                "stepTree": {"stepId": _WDK_ROOT_ID},
                "steps": {
                    str(_WDK_ROOT_ID): {
                        "id": _WDK_ROOT_ID,
                        "searchName": "GenesWithSignalPeptide",
                        "searchConfig": {"parameters": {}},
                        "estimatedSize": _ROOT_COUNT,
                    }
                },
            }
        )


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> _Site:
    api = _Site()
    for module in (naming, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)
    return api


def _leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_a",
        search_name="GenesWithSignalPeptide",
        parameters={"organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])},
    )


async def _seed(db_session: AsyncSession) -> UUID:
    user = User(id=uuid4())
    conv_id = uuid4()
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            id=conv_id,
            user_id=user.id,
            site_id="plasmodb",
            name=_OLD,
        )
    )
    await db_session.flush()
    ast = StrategyAst(record_type="transcript", name=_OLD, root=_leaf())
    db_session.add(
        ConversationStrategy(
            conversation_id=conv_id,
            strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
            wdk_strategy_id=_WDK_STRATEGY_ID,
            step_count=1,
        )
    )
    await db_session.commit()
    return conv_id


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name=_OLD, site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(_leaf()))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_a": _WDK_ROOT_ID}, wdk_strategy_id=_WDK_STRATEGY_ID
    )
    return session


async def test_the_rename_is_read_back_from_the_store_and_reaches_wdk(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    site: _Site,
) -> None:
    conv_id = await _seed(db_session)
    ctx = lead_run_context(
        conversation_id=conv_id,
        strategy_session=_session(),
        db_session_factory=session_maker,
        tool_call_id="call_rename",
    )

    returned = await rename_strategy(ctx, name=_NEW)

    async with session_maker() as fresh:
        found = await ConversationRepository(fresh).get_with_strategy(conv_id)
    assert found is not None
    conversation, strategy = found
    assert (conversation.name, strategy.strategy_ast["name"]) == (_NEW, _NEW)
    assert [
        (call.kwargs["strategy_id"], call.kwargs["name"])
        for call in site.named("update_strategy")
    ] == [(_WDK_STRATEGY_ID, _NEW)]
    assert returned.return_value == (
        f"Renamed the strategy to {_NEW}. It returns {_ROOT_COUNT} genes."
    )
