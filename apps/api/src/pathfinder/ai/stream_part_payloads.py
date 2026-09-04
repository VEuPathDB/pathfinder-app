"""Typed payloads for the graph, strategy, gene-set and enrichment data-parts.
``strategy_stream_parts`` registers them by kind."""

from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from pathfinder.services.enrichment.types import EnrichmentResult

# Matches WDK BooleanOperator (canonical 7) and the frontend `CombineOperator`
# union in `packages/shared-ts/src/types.ts`. Narrowing to a subset would silently
# drop valid WDK operators in graph snapshots.
GraphEdgeOperator = Literal[
    "INTERSECT", "UNION", "MINUS", "RMINUS", "LONLY", "RONLY", "COLOCATE"
]


class GraphNode(CamelModel):
    id: str
    search_name: str
    estimated_size: int = Field(ge=0)


class GraphEdge(CamelModel):
    source: str
    target: str
    operator: GraphEdgeOperator | None = None


class GraphSnapshot(CamelModel):
    strategy_id: str
    gene_count: int = Field(ge=0)
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphCleared(CamelModel):
    """Sentinel indicating the strategy graph was cleared."""

    reason: str | None = None


class StrategyMeta(CamelModel):
    """Top-level strategy metadata (one per strategy creation/load)."""

    strategy_id: str
    name: str
    is_saved: bool
    estimated_size: int = Field(ge=0)
    record_class_name: str


class StrategyLink(CamelModel):
    """A link to the strategy in the public WDK UI."""

    strategy_id: str
    url: str = Field(pattern=r"^https?://")
    title: str | None = None


class GeneSet(CamelModel):
    gene_set_id: str
    name: str
    gene_count: int = Field(ge=0)
    site_id: str


class EnrichmentResultsChunk(CamelModel):
    task_id: str
    gene_set_id: str
    gene_set_name: str
    gene_count: int
    results: list[EnrichmentResult]
    downloads: dict[str, str | int] | None = None
