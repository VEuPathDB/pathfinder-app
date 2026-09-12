"""Builds the stream chunks that tools attach to their return metadata.

Only data, source, and file chunks reach the client. The adapter drops
every other chunk shape without an error.
"""

from __future__ import annotations

from pydantic_ai.ui.vercel_ai.response_types import (
    DataChunk,
)
from veupathdb.domain.strategy import subtree_ids, wdk_search_name

from pathfinder.ai.stream_part_payloads import (
    GeneSet,
    GraphCleared,
    GraphEdge,
    GraphEdgeOperator,
    GraphNode,
    GraphSnapshot,
    StrategyLink,
    StrategyMeta,
)
from pathfinder.domain.strategy.build_outcome import citable_count
from pathfinder.domain.strategy.session import (
    StrategyGraph,
    StrategySession,
    strategy_root_id,
)
from pathfinder.domain.strategy.types import SyncStateProtocol

# --- Operator coercion -----------------------------------------------------


# Maps upper-cased input values to the canonical WDK operator set.
_OPERATOR_MAP: dict[str, GraphEdgeOperator] = {
    "INTERSECT": "INTERSECT",
    "UNION": "UNION",
    "MINUS": "MINUS",
    "RMINUS": "RMINUS",
    "LONLY": "LONLY",
    "RONLY": "RONLY",
    "COLOCATE": "COLOCATE",
}


def _coerce_operator(op: str | None) -> GraphEdgeOperator | None:
    """Return a stream-part operator, or None when the name is unknown."""
    if op is None:
        return None
    return _OPERATOR_MAP.get(op.upper())


# --- Graph snapshot --------------------------------------------------------


def _count_for_step(step_id: str, sync_state: SyncStateProtocol | None) -> int | None:
    """The count a step may be cited with, or nothing when it has none."""
    if sync_state is None:
        return None
    return citable_count(
        step_id,
        counts=sync_state.step_counts,
        refused=sync_state.wdk_push_errors,
    )


def _snapshot_edges(graph: StrategyGraph) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    for step in graph.steps.values():
        primary = step.primary_input_id
        if primary is not None:
            edges.append(
                GraphEdge(
                    source=primary,
                    target=step.id,
                    operator=_coerce_operator(
                        step.operator.value if step.operator else None
                    ),
                )
            )
        secondary = step.secondary_input_id
        if secondary is not None:
            edges.append(
                GraphEdge(
                    source=secondary,
                    target=step.id,
                    operator=_coerce_operator(
                        step.operator.value if step.operator else None
                    ),
                )
            )
    return edges


def _strategy_root_count(
    graph: StrategyGraph, sync_state: SyncStateProtocol | None
) -> int | None:
    """The genes the strategy returns, or nothing when its root has no
    citable count."""
    root_id = strategy_root_id(graph, sync_state)
    if root_id is None:
        return None
    return _count_for_step(root_id, sync_state)


def _detached_step_count(
    graph: StrategyGraph, sync_state: SyncStateProtocol | None
) -> int:
    """The steps the strategy's tree leaves out.

    A split graph names its fragments even when no root carries a count, so
    the structural root stands in when no push names one.
    """
    root_id = strategy_root_id(graph, sync_state) or graph.primary_root_id()
    if root_id is None:
        return 0
    return len(graph.steps) - len(subtree_ids(root_id, graph.steps))


def build_graph_snapshot_payload(
    session: StrategySession,
    graph: StrategyGraph,
) -> GraphSnapshot:
    """Build the graph snapshot payload for the current graph."""
    sync_state = session.sync_state
    nodes = [
        GraphNode(
            id=step.id,
            search_name=wdk_search_name(step),
            estimated_size=_count_for_step(step.id, sync_state),
        )
        for step in graph.steps.values()
    ]
    edges = _snapshot_edges(graph)
    return GraphSnapshot(
        strategy_id=graph.id,
        gene_count=_strategy_root_count(graph, sync_state),
        detached_step_count=_detached_step_count(graph, sync_state),
        nodes=nodes,
        edges=edges,
    )


def graph_snapshot_chunk(session: StrategySession, graph: StrategyGraph) -> DataChunk:
    """Build the graph snapshot chunk for a graph."""
    payload = build_graph_snapshot_payload(session, graph)
    return DataChunk(
        type="data-graph-snapshot",
        data=payload.model_dump(by_alias=True, mode="json"),
    )


def graph_cleared_chunk(*, reason: str | None = None) -> DataChunk:
    """Build the graph cleared chunk."""
    payload = GraphCleared(reason=reason)
    return DataChunk(
        type="data-graph-cleared",
        data=payload.model_dump(by_alias=True, mode="json"),
    )


# --- Strategy metadata -----------------------------------------------------


def strategy_meta_chunk(session: StrategySession, graph: StrategyGraph) -> DataChunk:
    """Build the strategy metadata chunk for a graph."""
    payload = StrategyMeta(
        strategy_id=graph.id,
        name=graph.name,
        is_saved=False,
        estimated_size=_strategy_root_count(graph, session.sync_state),
        record_class_name=graph.record_type or "transcript",
    )
    return DataChunk(
        type="data-strategy-meta",
        data=payload.model_dump(by_alias=True, mode="json"),
    )


def strategy_link_chunk(
    *,
    strategy_id: str,
    url: str,
    title: str | None = None,
) -> DataChunk:
    """Build the strategy link chunk. The URL must be an HTTP URL."""
    payload = StrategyLink(strategy_id=strategy_id, url=url, title=title)
    return DataChunk(
        type="data-strategy-link",
        data=payload.model_dump(by_alias=True, mode="json"),
    )


# --- Gene set --------------------------------------------------------------


def gene_set_chunk(
    *,
    gene_set_id: str,
    name: str,
    gene_count: int,
    site_id: str,
) -> DataChunk:
    """Build the gene set chunk for a workbench gene set."""
    payload = GeneSet(
        gene_set_id=gene_set_id,
        name=name,
        gene_count=gene_count,
        site_id=site_id,
    )
    return DataChunk(
        type="data-gene-set",
        data=payload.model_dump(by_alias=True, mode="json"),
    )
