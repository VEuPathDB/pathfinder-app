"""The seam between the turn node and the outside world it refreshes from.

The turn node runs an agent. Reading WDK to see what the user changed since
the last build is PathFinder's business, so it arrives as a hook the graph is
built with, not as an import inside the node.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.build_outcome import BuildOutcome, NodeResult
from veupathdb.domain.strategy.session import StrategySession
from veupathdb.wdk.wdk_models import WDKStrategyDetails

from pathfinder.ai.graph import lead_node
from pathfinder.ai.graph.lead_node import make_lead_node
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.web_search import WebSearchService
from pathfinder.services.strategies.sync_state import WDKSyncState

WDK_NAMES = {
    "read_wdk_step_counts",
    "detect_build_staleness",
    "get_strategy_api",
}


def _never_factory() -> AsyncSession:
    msg = "db factory should not be called in unit tests"
    raise AssertionError(msg)


def _details(sizes: dict[int, int | None]) -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 900,
            "name": "s",
            "rootStepId": max(sizes),
            "stepTree": {"stepId": max(sizes)},
            "steps": {
                str(wdk_id): {
                    "id": wdk_id,
                    "searchName": "GenesByText",
                    "searchConfig": {"parameters": {}},
                    "estimatedSize": size,
                }
                for wdk_id, size in sizes.items()
            },
        }
    )


def _session(*, synced: bool) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    if synced:
        sync = WDKSyncState()
        sync.wdk_strategy_id = 900
        sync.wdk_step_ids = {"leaf": 11}
        sync.step_counts = {"leaf": 2862}
        session.sync_state = sync
    return session


def _context(session: StrategySession) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=session,
        db_session_factory=_never_factory,
        web_search_service=WebSearchService(),
        literature_search_service=LiteratureSearchService(),
        cancel_event=asyncio.Event(),
    )


def _state() -> PipelineState:
    outcome = BuildOutcome(
        node_results=[
            NodeResult(
                node_id="leaf",
                search_name="GenesByText",
                count=2862,
                status="ok",
            )
        ],
    )
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        domain=StrategyDomainState(last_build_outcome=outcome),
    )


def test_the_turn_node_names_no_wdk_symbol() -> None:
    assert WDK_NAMES & set(vars(lead_node)) == set()


def test_the_node_factory_takes_the_hook() -> None:
    params = inspect.signature(make_lead_node).parameters
    assert "pre_turn" in params
    assert params["pre_turn"].default is inspect.Parameter.empty


async def test_the_hook_marks_a_build_stale_against_the_live_counts(
    monkeypatch: Any,
) -> None:
    api = AsyncMock()
    api.get_strategy = AsyncMock(return_value=_details({11: 587}))
    monkeypatch.setattr(
        "pathfinder.services.strategies.live_counts.get_strategy_api",
        lambda site_id: api,
    )
    state = _state()

    refreshed = await refresh_live_strategy_state(
        state, _context(_session(synced=True))
    )

    assert refreshed.domain.stale_build is not None
    assert refreshed.domain.stale_build.changed_nodes == [("leaf", 2862, 587)]


async def test_the_hook_leaves_the_checkpointed_state_untouched(
    monkeypatch: Any,
) -> None:
    api = AsyncMock()
    api.get_strategy = AsyncMock(return_value=_details({11: 587}))
    monkeypatch.setattr(
        "pathfinder.services.strategies.live_counts.get_strategy_api",
        lambda site_id: api,
    )
    state = _state()

    refreshed = await refresh_live_strategy_state(
        state, _context(_session(synced=True))
    )

    assert refreshed is not state
    assert state.domain.stale_build is None


async def test_an_unsynced_strategy_reads_nothing_and_stays_fresh() -> None:
    state = _state()

    refreshed = await refresh_live_strategy_state(
        state, _context(_session(synced=False))
    )

    assert refreshed.domain.stale_build is None
