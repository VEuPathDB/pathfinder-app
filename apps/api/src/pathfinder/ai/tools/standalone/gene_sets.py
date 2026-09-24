"""The agent tools that save a gene set and list the saved ones."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.logging import get_logger
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.strategy import StepKind
from veupathdb.errors import ValidationError

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.gene_set_models import (
    GeneSetCreatedResponse,
    GeneSetCreatedSummary,
    GeneSetListItem,
    GeneSetListResponse,
    WdkProvenance,
)
from pathfinder.ai.tools.standalone.stream_parts import gene_set_chunk
from pathfinder.domain.strategy.session import StrategySession, strategy_root_id
from pathfinder.services.evidence.gene_sets import (
    list_stored_gene_sets,
    store_gene_set,
)
from pathfinder.services.gene_sets.step_genes import (
    step_gene_ids,
    visible_parameter_names,
)
from pathfinder.services.gene_sets.types import GeneSet

logger = get_logger(__name__)

_NO_WDK_STEP = (
    "It holds gene IDs only: this conversation has no pushed strategy step behind them."
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


async def _with_the_parameters_a_user_sees(
    site_id: str, src: WdkProvenance, record_type: str
) -> WdkProvenance:
    """The provenance with only the parameters WDK shows for its search."""
    if src.search_name is None or src.parameters is None:
        return src
    try:
        visible = await visible_parameter_names(
            site_id, record_type=record_type, search_name=src.search_name
        )
    except ValidationError:
        # A definition the catalog cannot read decides nothing, and the genes
        # are already in hand: the set is saved with what the step carried.
        return src
    kept = {name: value for name, value in src.parameters.items() if name in visible}
    return src.model_copy(update={"parameters": kept})


async def _genes_of_step(
    deps: AgentDeps,
    step_id: str | None,
    record_type: str,
) -> tuple[list[str], WdkProvenance]:
    """The genes a step of this conversation's strategy holds, and its ids."""
    src = _wdk_provenance(deps.strategy_session, step_id)
    if src.wdk_step_id is None:
        raise ModelRetry(_NO_STEP_TO_SAVE_FROM)
    ids = await step_gene_ids(deps.site_id, src.wdk_step_id)
    if not ids:
        raise ModelRetry(_STEP_HOLDS_NO_GENES)
    return ids, await _with_the_parameters_a_user_sees(deps.site_id, src, record_type)


async def save_gene_set(
    ctx: RunContext[AgentDeps],
    name: str,
    record_type: str = "transcript",
    step_id: str | None = None,
    gene_ids: list[str] | None = None,
) -> ToolReturn[GeneSetCreatedResponse]:
    """Save a gene set the user can export, publish and test controls against.

    This is the save the user asks for when they say "save these genes as a
    gene set": the set appears in the thread, and it returns the id the export
    and control tools take. ``remember`` stores a note and creates nothing.

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
        ids, src = await _genes_of_step(deps, step_id, record_type)
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
    store_gene_set(gs)
    created = CreatedGeneSet(id=gs.id, name=gs.name, gene_count=len(gs.gene_ids))
    # The note the turn writes later reads one record; the turn's reply is
    # held against the other.
    deps.agent_state.created_gene_sets.append(created)
    deps.turn_markers.record_gene_set(created)
    logger.info(
        "AI saved a gene set",
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
                f"saved." + ("" if gs.wdk_step_id is not None else f" {_NO_WDK_STEP}")
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


async def list_gene_sets(
    ctx: RunContext[AgentDeps],
) -> ToolReturn[GeneSetListResponse]:
    """List the gene sets the user saved on this site.

    Returns a summary of each gene set including name, gene count,
    source, and ID.
    """
    deps = ctx.deps
    sets = await list_stored_gene_sets(site_id=deps.site_id, user_id=deps.user_id)
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
