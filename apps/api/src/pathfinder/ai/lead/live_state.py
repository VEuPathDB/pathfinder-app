"""Authoritative read of the strategy as it exists right now.

The Ledger holds counts from the last build, and the graph editor writes a
step's new value without writing the counts that value changes. This module
reads the graph the editor persisted and asks VEuPathDB for every count, so
the Lead can answer "what does my strategy return now?" with a fact rather
than a memory.
"""

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from veupathdb.domain.parameters import wire_map

from pathfinder.ai.tools.standalone._graph_helpers import build_step_response
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies.live_counts import read_wdk_step_counts

__all__ = ["LiveStepState", "LiveStrategyState", "read_live_state"]


class LiveStepState(CamelModel):
    step_id: str
    display_name: str
    search_name: str | None = None
    estimated_size: int | None = None
    """What the site returns for this step now. ``None`` means unknown."""

    parameters: dict[str, str] = Field(default_factory=dict)
    """The values stored on the step, which outrank the name it carries."""


class LiveStrategyState(CamelModel):
    """What the strategy actually is, read fresh from the session and the site."""

    wdk_strategy_id: int | None = None
    step_count: int = 0
    root_count: int | None = None
    """What the whole strategy returns now. ``None`` means unknown."""

    steps: list[LiveStepState] = Field(default_factory=list)


async def read_live_state(
    session: StrategySession,
    site_id: str,
) -> LiveStrategyState:
    """Snapshot the live strategy for the Lead.

    Counts come from the site alone. A recorded count describes the strategy
    as it was at the last build, so a count the site does not answer for is
    reported as unknown.
    """
    graph = session.graph
    if graph is None:
        return LiveStrategyState()

    sync_state = session.sync_state
    counts = await read_wdk_step_counts(sync_state, site_id) if sync_state else {}
    steps = [
        LiveStepState(
            step_id=step.id,
            display_name=response.display_name or step.id,
            search_name=response.search_name,
            estimated_size=counts.get(step.id),
            parameters=wire_map(step.parameters or {}),
        )
        for step in graph.steps.values()
        if (response := build_step_response(graph, step, sync_state)) is not None
    ]
    # A complete strategy has exactly one root; ambiguity means no single
    # headline count to report.
    root_count = counts.get(next(iter(graph.roots))) if len(graph.roots) == 1 else None

    return LiveStrategyState(
        wdk_strategy_id=sync_state.wdk_strategy_id if sync_state else None,
        step_count=len(graph.steps),
        root_count=root_count,
        steps=steps,
    )
