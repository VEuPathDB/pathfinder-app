"""Typed payloads for the graph, strategy, gene-set and enrichment data-parts.
``strategy_stream_parts`` registers them by kind."""

from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from veupathdb_mcp.wdk.enrichment import EnrichmentResult

# Matches WDK BooleanOperator (canonical 7) and the frontend `CombineOperator`
# union in `packages/shared-ts/src/types.ts`. Narrowing to a subset would silently
# drop valid WDK operators in graph snapshots.
GraphEdgeOperator = Literal[
    "INTERSECT", "UNION", "MINUS", "RMINUS", "LONLY", "RONLY", "COLOCATE"
]


class GraphNode(CamelModel):
    id: str
    search_name: str
    estimated_size: int | None = Field(ge=0)


class GraphEdge(CamelModel):
    source: str
    target: str
    operator: GraphEdgeOperator | None = None


class GraphSnapshot(CamelModel):
    strategy_id: str
    gene_count: int | None = Field(ge=0)
    """What the strategy's root returns. Nothing when no root is citable."""

    detached_step_count: int = Field(ge=0)
    """The steps the strategy's tree does not hold."""

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
    estimated_size: int | None = Field(ge=0)
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
    tool_call_id: str = ""
    gene_set_id: str
    gene_set_name: str
    gene_count: int
    results: list[EnrichmentResult]
    downloads: dict[str, str | int] | None = None


class ControlSetSummary(CamelModel):
    """One control set of a control test: its size, its hits, its rate and the
    ids behind the counts. ``missed_ids`` is empty for a negative set, whose
    hits are the unexpected ones."""

    controls_count: int = Field(ge=0)
    intersection_count: int = Field(ge=0)
    recall: float | None = None
    false_positive_rate: float | None = None
    hit_ids: list[str] = Field(default_factory=list)
    missed_ids: list[str] = Field(default_factory=list)


class TestedParameter(CamelModel):
    """One criterion the tested step ran, under the name WDK shows for it."""

    label: str
    value: str


class ControlTestResults(CamelModel):
    """The numbers one control test measured against a built WDK step.

    ``task_id`` names the worker task the row on the thread reports, and is
    empty for a test that ran inside the turn; ``tool_call_id`` names the call
    the summary line describes. ``target_label`` is what WDK calls the tested
    step or search, never a url segment.
    """

    task_id: str
    tool_call_id: str
    target_step_id: int | None = None
    target_label: str = ""
    target_estimated_size: int = Field(default=0, ge=0)
    target_parameters: list[TestedParameter] = Field(default_factory=list)
    positive: ControlSetSummary | None = None
    negative: ControlSetSummary | None = None
