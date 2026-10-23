"""Which step of the graph a WDK step id is, and what it is read as."""

from __future__ import annotations

from pydantic_ai import ModelRetry
from veupathdb.domain.strategy import StepKind, StrategyStep

from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies.record_classes import step_record_class


def graph_step_id(session: StrategySession, wdk_step_id: int) -> str | None:
    sync = session.sync_state
    return next(
        (
            s
            for s, w in ({} if sync is None else sync.wdk_step_ids).items()
            if w == wdk_step_id
        ),
        None,
    )


async def own_class(session: StrategySession, step: StrategyStep) -> str | None:
    graph = session.get_graph(None)
    if graph is None:
        return None
    return await step_record_class(session.site_id, graph.steps, step.id)


async def read_as(session: StrategySession, wdk_step_id: int) -> tuple[str, str | None]:
    """The record type the step answers in, and the search it runs itself."""
    graph = session.get_graph(None)
    step_id = graph_step_id(session, wdk_step_id)
    step = None if graph is None or step_id is None else graph.steps.get(step_id)
    if step is None:
        msg = (
            f"Step {wdk_step_id} is not a step of this strategy, so it cannot be read."
        )
        raise ModelRetry(msg)
    own = None if step.kind is StepKind.COMBINE else step.search_name
    record_type = await own_class(session, step)
    if record_type is None:
        msg = (
            f"The site lists no record type for {own or step.display_label}, so "
            f"step {wdk_step_id} cannot be read."
        )
        raise ModelRetry(msg)
    return record_type, own


__all__ = ["graph_step_id", "own_class", "read_as"]
