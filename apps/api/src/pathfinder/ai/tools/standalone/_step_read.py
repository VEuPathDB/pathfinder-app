"""Which step of the graph a WDK step id is, and what it is read as."""

from __future__ import annotations

from veupathdb.domain.strategy import StepKind, record_class_of

from pathfinder.domain.strategy.session import StrategySession


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


def read_as(session: StrategySession, wdk_step_id: int) -> tuple[str, str | None]:
    """The record type the step answers in, and the search it runs itself."""
    graph = session.get_graph(None)
    fallback = (graph.record_type if graph is not None else None) or "transcript"
    step_id = graph_step_id(session, wdk_step_id)
    step = None if graph is None or step_id is None else graph.steps.get(step_id)
    if graph is None or step is None:
        return fallback, None
    own = None if step.kind is StepKind.COMBINE else step.search_name
    return record_class_of(step.id, graph.steps, fallback=fallback), own


__all__ = ["graph_step_id", "read_as"]
