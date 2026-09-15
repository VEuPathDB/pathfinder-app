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
from assistant_core.tasks.decorator import DurableOutcome
from pydantic import ConfigDict, Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk
from veupathdb.domain.strategy import StepKind
from veupathdb_mcp.wdk.enrichment import EnrichmentAnalysisType, EnrichmentResult

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.stream_events import enrichment_results_event
from pathfinder.ai.stream_part_payloads import EnrichmentResultsChunk
from pathfinder.ai.tools.standalone.stream_parts import gene_set_chunk
from pathfinder.ai.tools.standalone.workbench_models import (
    GeneSetCreatedResponse,
    GeneSetCreatedSummary,
    GeneSetListItem,
    GeneSetListResponse,
    WdkProvenance,
)
from pathfinder.domain.strategy.session import StrategySession, strategy_root_id
from pathfinder.platform.durable_worker import durable_agent_tool
from pathfinder.services.gene_sets.step_genes import step_gene_ids
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.workbench.gene_sets import list_gene_sets, save_gene_set

logger = get_logger(__name__)

_NO_WDK_STEP = (
    "It holds gene IDs only: this conversation has no pushed strategy step "
    "behind them, so enrichment cannot recover a background gene universe."
)

_NO_STEP_TO_SAVE_FROM = (
    "This conversation has no pushed strategy step to save from. Pass "
    "gene_ids to save a list of genes instead."
)

_A_LIST_AND_A_STEP = (
    "A pasted gene list carries no strategy step. Leave step_id out to save "
    "these ids as a list, or leave gene_ids out to save the genes of that step."
)

_STEP_HOLDS_NO_GENES = (
    "That step returns no genes on VEuPathDB, so there is nothing to save. "
    "Widen the strategy, or pass gene_ids to save a list of genes."
)


def _no_such_step(step_id: str, known: list[str]) -> str:
    """Why a save that names a step the strategy has not pushed is refused."""
    held = ", ".join(sorted(known)) or "none"
    return (
        f"VALIDATION_ERROR: step_id={step_id!r} names no step this strategy "
        f"has on VEuPathDB. The steps it has: {held}. Pass one of them, or "
        f"pass none to save from the strategy's root step."
    )


def _wdk_provenance(session: StrategySession, step_id: str | None) -> WdkProvenance:
    """What a save records about the strategy step behind its genes.

    The ids come from the last push, keyed by the graph's own step id. A step
    the push does not name is refused; a thread with no pushed strategy
    records no ids.
    """
    graph = session.graph
    sync_state = session.sync_state
    if graph is None or sync_state is None:
        return WdkProvenance()
    if step_id is not None and step_id not in sync_state.wdk_step_ids:
        raise ModelRetry(_no_such_step(step_id, list(sync_state.wdk_step_ids)))
    local_id = step_id or strategy_root_id(graph, sync_state)
    step = graph.get_step(local_id) if local_id is not None else None
    wdk_step_id = sync_state.wdk_step_ids.get(local_id or "")
    if wdk_step_id is None or step is None:
        return WdkProvenance()
    # Only a search step can be re-run from its name and parameters alone. A
    # combine runs no search of its own, and a transform needs its input step.
    runs_search = step.kind is StepKind.SEARCH
    return WdkProvenance(
        wdk_strategy_id=sync_state.wdk_strategy_id,
        wdk_step_id=wdk_step_id,
        search_name=step.search_name if runs_search else None,
        parameters=dict(step.parameters) if runs_search else None,
    )


async def _genes_of_step(
    deps: AgentDeps,
    step_id: str | None,
) -> tuple[list[str], WdkProvenance]:
    """The genes a step of this conversation's strategy holds, and its ids."""
    src = _wdk_provenance(deps.strategy_session, step_id)
    if src.wdk_step_id is None:
        raise ModelRetry(_NO_STEP_TO_SAVE_FROM)
    ids = await step_gene_ids(deps.site_id, src.wdk_step_id)
    if not ids:
        raise ModelRetry(_STEP_HOLDS_NO_GENES)
    return ids, src


async def create_workbench_gene_set(
    ctx: RunContext[AgentDeps],
    name: str,
    record_type: str = "transcript",
    step_id: str | None = None,
    gene_ids: list[str] | None = None,
) -> ToolReturn[GeneSetCreatedResponse]:
    """Create a gene set in the user's Workbench for further analysis.

    This is the save the user asks for when they say "save these genes as a
    gene set": it puts the set in the Workbench sidebar, where enrichment,
    export, EDA and the control tools read it, and it returns the id those
    tools take. ``remember`` stores a note and creates nothing.

    Args:
        name: Human-readable name for the gene set (e.g. 'Upregulated in gametocytes').
        record_type: Record type (default 'transcript').
        step_id: The step of THIS conversation's strategy whose genes to save,
            by its graph id (e.g. 'step_3'). Leave it out for the strategy's
            root step. The genes of a step are read from that step on
            VEuPathDB, and its WDK ids come from the strategy; never type one.
        gene_ids: A list of gene IDs the user pasted or this turn computed,
            which no step holds (e.g. ['PF3D7_1222600', 'PF3D7_1031000']). It
            saves that list alone, so leave it out whenever the genes are a
            step's.
    """
    if not name or not name.strip():
        msg = "VALIDATION_ERROR: Gene set name must be a non-empty string."
        raise ModelRetry(msg)
    deps = ctx.deps
    if gene_ids is None:
        ids, src = await _genes_of_step(deps, step_id)
    else:
        if step_id is not None:
            raise ModelRetry(_A_LIST_AND_A_STEP)
        if not gene_ids:
            msg = "VALIDATION_ERROR: gene_ids must contain at least one gene ID."
            raise ModelRetry(msg)
        ids, src = gene_ids, WdkProvenance()
    gs = GeneSet(
        id=str(uuid4()),
        name=name,
        site_id=deps.site_id,
        gene_ids=ids,
        source=src.source,
        user_id=deps.user_id,
        wdk_strategy_id=src.wdk_strategy_id,
        wdk_step_id=src.wdk_step_id,
        search_name=src.search_name,
        record_type=record_type,
        parameters=src.parameters,
    )
    save_gene_set(gs)
    deps.agent_state.created_gene_sets.append(
        CreatedGeneSet(id=gs.id, name=gs.name, gene_count=len(gs.gene_ids))
    )
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
            message=(
                f"Gene set '{gs.name}' with {len(gs.gene_ids)} genes has been "
                f"created in the Workbench."
                + ("" if gs.wdk_step_id is not None else f" {_NO_WDK_STEP}")
            ),
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


@durable_agent_tool(GENESET_ENRICHMENT)
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
    msg = "run_gene_set_enrichment runs on the worker via @durable_agent_tool"
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
