"""Authoritative read of the strategy as it exists right now.

The Ledger holds counts from the last build, and the graph editor writes a
step's new value without writing the counts that value changes. This module
reads the graph the editor persisted and asks VEuPathDB for every count, so
the Lead can answer "what does my strategy return now?" with a fact rather
than a memory.
"""

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from strategist.ai.tools.standalone.graph_helpers import serialize_step
from strategist.ai.tools.standalone.strategy_graph import ShownStep, shown_step
from strategist.domain.strategy.build_outcome import citable_count
from strategist.domain.strategy.session import StrategySession, strategy_root_id
from strategist.services.strategies.live_counts import read_wdk_step_counts

__all__ = ["LiveStrategyState", "read_live_state"]


class LiveStrategyState(CamelModel):
    """What the strategy actually is, read fresh from the session and the site."""

    wdk_strategy_id: int | None = None
    step_count: int = 0
    record_type: str | None = None
    root_count: int | None = None
    """What the whole strategy returns now. ``None`` means unknown."""

    root_step_id: str | None = None
    """The step whose count is the strategy's count."""

    steps: list[ShownStep] = Field(default_factory=list)


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
    refused = sync_state.wdk_push_errors if sync_state else {}
    root_id = strategy_root_id(graph, sync_state)
    steps = [
        shown_step(
            serialize_step(graph, step, sync_state).model_copy(
                update={
                    "estimated_size": citable_count(
                        step.id, counts=counts, refused=refused
                    )
                }
            )
        )
        for step in graph.steps.values()
    ]
    root_count = (
        citable_count(root_id, counts=counts, refused=refused)
        if root_id is not None
        else None
    )

    return LiveStrategyState(
        wdk_strategy_id=sync_state.wdk_strategy_id if sync_state else None,
        step_count=len(graph.steps),
        record_type=graph.record_type,
        root_count=root_count,
        root_step_id=root_id,
        steps=steps,
    )
