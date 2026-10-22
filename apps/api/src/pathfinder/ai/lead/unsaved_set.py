from __future__ import annotations

from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.gene_homes import holds_genes
from pathfinder.domain.strategy.session import StrategyGraph, strategy_root_id
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.domain.turn_facts import UnsavedSetFact
from pathfinder.platform.config import get_settings
from pathfinder.services.gene_sets.homes import site_kind


def result_not_saved(
    site_id: str,
    graph: StrategyGraph | None,
    sync_state: SyncStateProtocol | None,
) -> UnsavedSetFact | None:
    if graph is None or sync_state is None or not graph.record_type:
        return None
    root = strategy_root_id(graph, sync_state)
    count = None if root is None else sync_state.step_counts.get(root)
    cap = get_settings().step_genes_cap
    if (
        count is None
        or count <= cap
        or not holds_genes(site_kind(site_id), graph.record_type)
    ):
        return None
    return UnsavedSetFact(
        count=count, cap=cap, record_noun=counted_noun(graph.record_type)
    )
