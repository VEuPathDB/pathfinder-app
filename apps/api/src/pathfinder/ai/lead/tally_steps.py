"""The tallies of a turn, each with the steps between the result and its step."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.domain.strategy.session import StrategySession, strategy_root_id
from pathfinder.domain.tally_facts import TallyFact
from pathfinder.domain.tally_paths import tally_paths


def tallies_with_paths(
    session: StrategySession, tallies: Sequence[TallyFact]
) -> list[TallyFact]:
    graph = session.get_graph(None)
    sync = session.sync_state
    root = None if graph is None else strategy_root_id(graph, sync)
    if graph is None or sync is None or root is None:
        return list(tallies)
    elsewhere = [t.wdk_step_id for t in tallies if t.wdk_step_id is not None]
    paths = {
        p.tallied_step_id: p
        for p in tally_paths(graph.steps, sync.wdk_step_ids, root, elsewhere)
    }
    return [
        t
        if t.wdk_step_id not in paths
        else t.model_copy(update={"path": paths[t.wdk_step_id]})
        for t in tallies
    ]


__all__ = ["tallies_with_paths"]
