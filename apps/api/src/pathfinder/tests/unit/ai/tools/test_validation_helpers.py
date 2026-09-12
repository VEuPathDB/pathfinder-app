"""A tool that takes a graph id also answers to the VEuPathDB strategy id.

Verification reads a step's strategy by whichever id the turn put in front of
it, so a lookup by the VEuPathDB id must reach the graph that built it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import conversation
from pathfinder.ai.tools.standalone._validation_helpers import get_graph
from pathfinder.ai.tools.standalone.conversation_models import (
    ClearStrategyResult,
    RenameStrategyResult,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_WDK_STRATEGY_ID = 330558093


@pytest.fixture
def session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("graph-1", "Heat shock", "plasmodb"))
    session.sync_state = WDKSyncState(wdk_strategy_id=_WDK_STRATEGY_ID)
    return session


def _ctx(session: StrategySession) -> RunContext[AgentDeps]:
    return agent_run_context(strategy_session=session)


def test_the_veupathdb_strategy_id_finds_the_graph(session: StrategySession) -> None:
    found = get_graph(session, str(_WDK_STRATEGY_ID))
    assert found is not None
    assert found.id == "graph-1"


def test_the_graph_id_still_finds_the_graph(session: StrategySession) -> None:
    found = get_graph(session, "graph-1")
    assert found is not None
    assert found.id == "graph-1"


def test_no_id_returns_the_active_graph(session: StrategySession) -> None:
    found = get_graph(session, None)
    assert found is not None
    assert found.id == "graph-1"


def test_another_strategys_id_is_still_not_found(session: StrategySession) -> None:
    bound = get_graph(session, str(_WDK_STRATEGY_ID))
    assert bound is not None
    assert bound.id == "graph-1"
    assert get_graph(session, "330558094") is None


def test_a_strategy_id_finds_nothing_before_the_push() -> None:
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("graph-1", "Heat shock", "plasmodb"))

    assert get_graph(session, str(_WDK_STRATEGY_ID)) is None
    unpushed = get_graph(session, "graph-1")
    assert unpushed is not None
    assert unpushed.id == "graph-1"


class TestTheConversationToolsAddressTheSameWay:
    """rename_strategy and clear_strategy answer the VEuPathDB strategy id."""

    @pytest.mark.asyncio
    async def test_rename_takes_the_veupathdb_strategy_id(
        self, session: StrategySession
    ) -> None:
        answer = await conversation.rename_strategy(
            _ctx(session),
            new_name="Heat shock, refined",
            description="a refined strategy",
            graph_id=str(_WDK_STRATEGY_ID),
        )

        result = returned(answer, RenameStrategyResult)
        assert result.graph_id == "graph-1"
        assert result.old_name == "Heat shock"
        assert result.new_name == "Heat shock, refined"

    @pytest.mark.asyncio
    async def test_clear_takes_the_veupathdb_strategy_id(
        self, session: StrategySession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            conversation,
            "persist_strategy_ast_to_conversation",
            AsyncMock(),
        )

        answer = await conversation.clear_strategy(
            _ctx(session),
            graph_id=str(_WDK_STRATEGY_ID),
            confirm=True,
        )

        result = returned(answer, ClearStrategyResult)
        assert result.graph_id == "graph-1"
        cleared = session.get_graph("graph-1")
        assert cleared is not None
        assert cleared.steps == {}

    @pytest.mark.asyncio
    async def test_rename_still_refuses_another_strategys_id(
        self, session: StrategySession
    ) -> None:
        with pytest.raises(ModelRetry, match="NOT_FOUND"):
            await conversation.rename_strategy(
                _ctx(session),
                new_name="n",
                description="d",
                graph_id="330558094",
            )

    @pytest.mark.asyncio
    async def test_clear_still_refuses_another_strategys_id(
        self, session: StrategySession
    ) -> None:
        with pytest.raises(ModelRetry, match="NOT_FOUND"):
            await conversation.clear_strategy(
                _ctx(session),
                graph_id="330558094",
                confirm=True,
            )
