"""Standalone workbench gene set tools for pydantic-ai agents.

Provides:
- ``create_workbench_gene_set`` -- create a gene set in the user's Workbench
- ``run_gene_set_enrichment`` -- run enrichment analysis on a gene set (durable)
- ``list_workbench_gene_sets`` -- list all gene sets in the user's Workbench
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from assistant_core.graph.tool_summary import summary_chunks, with_summary
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.tasks.declaration import declare_durable_tool
from assistant_core.tasks.decorator import DurableOutcome, durable_tool
from pydantic import ConfigDict, Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk
from veupathdb_mcp.wdk.enrichment import EnrichmentAnalysisType, EnrichmentResult

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.stream_events import enrichment_results_event
from pathfinder.ai.stream_part_payloads import EnrichmentResultsChunk
from pathfinder.ai.tools.standalone._stream_parts import gene_set_chunk
from pathfinder.ai.tools.standalone._workbench_models import (
    GeneSetCreatedResponse,
    GeneSetCreatedSummary,
    GeneSetListItem,
    GeneSetListResponse,
    WdkSourceSpec,
)
from pathfinder.services.gene_sets.types import GeneSet, GeneSetSource
from pathfinder.services.workbench.gene_sets import list_gene_sets, save_gene_set

logger = get_logger(__name__)


async def create_workbench_gene_set(
    ctx: RunContext[AgentDeps],
    name: str,
    gene_ids: list[str],
    record_type: str = "transcript",
    wdk_source: WdkSourceSpec | None = None,
) -> ToolReturn[GeneSetCreatedResponse]:
    """Create a gene set in the user's Workbench for further analysis.

    Use this tool after building a strategy or collecting gene IDs to send them
    to the Workbench where the user can run enrichment analysis, evaluate
    strategies, compare gene sets, and more.

    The created gene set will appear in the user's Workbench sidebar.

    Args:
        name: Human-readable name for the gene set (e.g. 'Upregulated in gametocytes').
        gene_ids: List of gene IDs to include (e.g. ['PF3D7_1222600', 'PF3D7_1031000']).
        record_type: Record type (default 'transcript').
        wdk_source: Optional WDK provenance (search name, parameters, strategy ID, step ID).
    """
    if not name or not name.strip():
        msg = "VALIDATION_ERROR: Gene set name must be a non-empty string."
        raise ModelRetry(msg)
    if not gene_ids:
        msg = "VALIDATION_ERROR: gene_ids must contain at least one gene ID."
        raise ModelRetry(msg)
    deps = ctx.deps
    src = wdk_source or WdkSourceSpec()
    source: GeneSetSource = "strategy" if src.wdk_strategy_id is not None else "paste"
    gs = GeneSet(
        id=str(uuid4()),
        name=name,
        site_id=deps.site_id,
        gene_ids=gene_ids,
        source=source,
        user_id=deps.user_id,
        wdk_strategy_id=src.wdk_strategy_id,
        wdk_step_id=src.wdk_step_id,
        search_name=src.search_name,
        record_type=record_type,
        parameters=src.parameters,
    )
    save_gene_set(gs)
    logger.info(
        "AI created workbench gene set",
        gene_set_id=gs.id,
        name=gs.name,
        gene_count=len(gs.gene_ids),
    )
    return with_summary(
        GeneSetCreatedResponse(
            gene_set_created=GeneSetCreatedSummary(
                id=gs.id,
                name=gs.name,
                gene_count=len(gs.gene_ids),
                source=gs.source,
                site_id=gs.site_id,
            ),
            message=f"Gene set '{gs.name}' with {len(gs.gene_ids)} genes has been created in the Workbench.",
        ),
        f"{gs.name}: {len(gs.gene_ids):,} genes",
        ctx=ctx,
        extra=[
            gene_set_chunk(
                gene_set_id=gs.id,
                name=gs.name,
                gene_count=len(gs.gene_ids),
                site_id=gs.site_id,
            )
        ],
    )


class _EnrichmentOutcome(CamelModel):
    """What a finished enrichment run reports about its terms."""

    model_config = ConfigDict(extra="ignore")

    gene_set_id: str = ""
    gene_set_name: str = ""
    gene_count: int = 0
    total_significant_terms: int = 0
    analysis_types_run: list[str] = Field(default_factory=list)
    enrichment_results: list[EnrichmentResult] = Field(default_factory=list)
    downloads: dict[str, str | int] | None = None


def _enrichment_chunks_from_result(
    resumed: Any,
    task_id: UUID,
    tool_call_id: str | None,
) -> list[BaseChunk]:
    outcome = DurableOutcome.model_validate(resumed)
    if not outcome.succeeded:
        return []
    enrichment = _EnrichmentOutcome.model_validate(outcome.result)
    terms = enrichment.total_significant_terms
    chunks: list[BaseChunk] = []
    if enrichment.enrichment_results:
        chunks.append(
            enrichment_results_event(
                EnrichmentResultsChunk(
                    task_id=str(task_id),
                    tool_call_id=tool_call_id or "",
                    gene_set_id=enrichment.gene_set_id,
                    gene_set_name=enrichment.gene_set_name,
                    gene_count=enrichment.gene_count,
                    results=enrichment.enrichment_results,
                    downloads=enrichment.downloads,
                )
            ),
        )
    chunks.extend(
        summary_chunks(
            tool_call_id,
            f"{terms} enriched terms across "
            f"{len(enrichment.analysis_types_run)} analyses",
            status="ok" if terms else "empty",
        ),
    )
    return chunks


GENESET_ENRICHMENT = declare_durable_tool(
    tool_name="geneset_enrichment",
    estimated_duration_seconds=120,
    chunks_from_result=_enrichment_chunks_from_result,
)


@durable_tool(GENESET_ENRICHMENT)
async def run_gene_set_enrichment(
    ctx: RunContext[AgentDeps],
    gene_set_id: str,
    enrichment_types: list[EnrichmentAnalysisType] | None = None,
) -> dict[str, Any]:
    """Run enrichment analysis on a gene set in the Workbench.

    Durable: the real analysis runs on the verification worker; the turn
    ends while GO/Pathway/Word ORA phases complete and progress streams back
    through ``task_progress``. You are called again with the summary dict
    (the gene set's id, ``geneCount``, ``enrichmentResults``, ``downloads``).

    Requires the gene set to have a WDK step ID or search parameters so the
    enrichment service can recover the full background gene universe.

    Args:
        gene_set_id: ID of the gene set to run enrichment on (from
            ``create_workbench_gene_set`` result).
        enrichment_types: Types of enrichment to run. Options: ``go_function``,
            ``go_process``, ``go_component``, ``pathway``, ``word``. Default:
            all five types.
    """
    del ctx, gene_set_id, enrichment_types
    msg = "run_gene_set_enrichment runs on the worker via @durable_tool"
    raise NotImplementedError(msg)


async def list_workbench_gene_sets(
    ctx: RunContext[AgentDeps],
) -> ToolReturn[GeneSetListResponse]:
    """List all gene sets currently in the user's Workbench.

    Returns a summary of each gene set including name, gene count,
    source, and ID. Use this to check what's available before
    running analyses.
    """
    deps = ctx.deps
    sets = await list_gene_sets(site_id=deps.site_id, user_id=deps.user_id)
    return with_summary(
        GeneSetListResponse(
            gene_sets=[
                GeneSetListItem(
                    id=gs.id,
                    name=gs.name,
                    gene_count=len(gs.gene_ids),
                    source=gs.source,
                    search_name=gs.search_name,
                    has_wdk_step=gs.wdk_step_id is not None,
                )
                for gs in sets
            ],
            total_sets=len(sets),
        ),
        f"{len(sets)} gene sets",
        ctx=ctx,
    )
