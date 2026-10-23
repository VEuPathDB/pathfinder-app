from __future__ import annotations

from veupathdb.domain.strategy import (
    StepKind,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState


def classed_strategy(
    site_id: str, wdk_step_ids: dict[str, int], record_type: str = "transcript"
) -> StrategySession:
    session = StrategySession(site_id=site_id)
    graph = StrategyGraph(graph_id="g1", name="genes", site_id=site_id)
    graph.record_type = record_type
    for step_id in wdk_step_ids:
        graph.steps[step_id] = StrategyStep(
            id=step_id,
            kind=StepKind.SEARCH,
            search_name="GenesByTaxon",
            record_class=record_type,
        )
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids=dict(wdk_step_ids))
    return session


def classed_steps(
    root: StrategyStepNode, record_type: str = "transcript"
) -> dict[str, StrategyStep]:
    steps = flatten_tree(root)
    for step in steps.values():
        if step.search_name:
            step.record_class = record_type
    return steps
