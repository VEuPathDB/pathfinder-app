"""Builds the stream chunks that tools attach to their return metadata.

Only data, source, and file chunks reach the client. The adapter drops
every other chunk shape without an error.
"""

from __future__ import annotations

from pydantic_ai.ui.vercel_ai.response_types import (
    DataChunk,
    SourceUrlChunk,
)
from veupathdb.domain.strategy.graph_model import wdk_search_name
from veupathdb.domain.strategy.session import StrategyGraph, StrategySession
from veupathdb.domain.strategy.types import SyncStateProtocol

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


def _count_for_step(step_id: str, sync_state: SyncStateProtocol | None) -> int:
    """Look up the estimated size of a step. Unknown steps count as 0."""
    if sync_state is None:
        return 0
    count = sync_state.step_counts.get(step_id)
    return count if isinstance(count, int) else 0


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


def build_graph_snapshot_payload(
    session: StrategySession,
    graph: StrategyGraph,
) -> GraphSnapshot:
    """Build the graph snapshot payload for the current graph."""
    sync_state = session.sync_state
    total_genes = 0
    for root_id in graph.roots:
        total_genes += _count_for_step(root_id, sync_state)
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
        gene_count=total_genes,
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


def strategy_meta_chunk(graph: StrategyGraph) -> DataChunk:
    """Build the strategy metadata chunk for a graph."""
    sync_state = getattr(graph, "sync_state", None)
    total_size = 0
    if sync_state is not None:
        for root_id in graph.roots:
            count = sync_state.step_counts.get(root_id)
            if isinstance(count, int):
                total_size += count
    payload = StrategyMeta(
        strategy_id=graph.id,
        name=graph.name,
        is_saved=False,
        estimated_size=total_size,
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


# --- Source URLs (citations) -----------------------------------------------


def source_url_chunks_from_citations(
    citations: list[object],
) -> list[SourceUrlChunk]:
    """Emit one source chunk per citation. A citation without a URL is skipped."""
    chunks: list[SourceUrlChunk] = []
    for cit in citations:
        url = getattr(cit, "url", None)
        if not isinstance(url, str) or not url:
            continue
        cit_id = getattr(cit, "id", "")
        title = getattr(cit, "title", None)
        chunks.append(
            SourceUrlChunk(
                source_id=str(cit_id) or url,
                url=url,
                title=title if isinstance(title, str) else None,
            )
        )
    return chunks
