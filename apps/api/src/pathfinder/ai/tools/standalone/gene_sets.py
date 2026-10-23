"""The agent tools that save a gene set and list the saved ones."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.logging import get_logger
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.strategy import StepKind
from veupathdb.errors import ValidationError

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.stream_part_payloads import ListedGeneSet, ListedGeneSets
from pathfinder.ai.tools.standalone._saved_here import saved_here
from pathfinder.ai.tools.standalone.gene_set_models import (
    GeneSetCreatedResponse,
    GeneSetCreatedSummary,
    GeneSetListItem,
    GeneSetListResponse,
    WdkProvenance,
)
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.ai.tools.standalone.stream_parts import (
    gene_set_chunk,
    gene_set_list_chunk,
)
from pathfinder.domain.gene_homes import gene_record_class
from pathfinder.domain.strategy.session import StrategySession, strategy_root_id
from pathfinder.services.evidence.gene_sets import (
    list_stored_gene_sets,
    store_gene_set,
)
from pathfinder.services.gene_sets.homes import (
    StepGenes,
    gene_homes,
    read_step_genes,
    site_kind,
    sites_that_list,
)
from pathfinder.services.gene_sets.step_genes import (
    IncompleteAnswerError,
    TooManyGenesError,
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
    "A pasted list of gene ids carries no strategy step. Leave step_id out to save "
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
) -> tuple[StepGenes, WdkProvenance]:
    """The genes a step of this conversation's strategy holds, and its ids."""
    src = _wdk_provenance(deps.strategy_session, step_id)
    if src.wdk_step_id is None:
        raise ModelRetry(_NO_STEP_TO_SAVE_FROM)
    genes = await read_step_genes(deps.site_id, src.wdk_step_id)
    if not genes.gene_ids:
        raise ModelRetry(_STEP_HOLDS_NO_GENES)
    return genes, await _with_the_parameters_a_user_sees(
        deps.site_id, src, genes.record_class
    )


async def _genes_of_list(
    deps: AgentDeps, step_id: str | None, gene_ids: list[str], record_type: str
) -> StepGenes:
    if step_id is not None:
        raise ModelRetry(_A_LIST_AND_A_STEP)
    if not gene_ids:
        msg = "VALIDATION_ERROR: gene_ids must contain at least one gene ID."
        raise ModelRetry(msg)
    return StepGenes(
        gene_ids=gene_ids,
        homes=await gene_homes(deps.site_id, gene_ids, record_type=record_type),
        record_class=record_type,
    )


async def _genes_to_save(
    deps: AgentDeps,
    step_id: str | None,
    gene_ids: list[str] | None,
    record_type: str,
) -> tuple[StepGenes, WdkProvenance]:
    try:
        if gene_ids is None:
            return await _genes_of_step(deps, step_id)
        genes = await _genes_of_list(deps, step_id, gene_ids, record_type)
    except (IncompleteAnswerError, TooManyGenesError) as exc:
        raise ModelRetry(str(exc.detail)) from exc
    return genes, WdkProvenance()


async def save_gene_set(
    ctx: RunContext[AgentDeps],
    name: str,
    step_id: str | None = None,
    gene_ids: list[str] | None = None,
) -> ToolReturn[GeneSetCreatedResponse]:
    """Save a gene set the user can export and publish.

    This is the save the user asks for when they say "save these genes as a
    gene set": the set appears in the conversation, and it returns the id the export
    tools take. ``remember`` stores a note and creates nothing. Controls are
    saved with ``build_control_set``, never as a gene set. A save is never a
    read: ``read_step_ids`` answers which genes a step holds.

    Args:
        name: Human-readable name for the gene set (e.g. 'Upregulated in gametocytes').
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
    genes, src = await _genes_to_save(
        deps, step_id, gene_ids, gene_record_class(site_kind(deps.site_id))
    )
    gs = GeneSet(
        id=str(uuid4()),
        name=name,
        site_id=deps.site_id,
        gene_ids=genes.gene_ids,
        source=src.source,
        user_id=deps.user_id,
        wdk_strategy_id=src.wdk_strategy_id,
        wdk_step_id=src.wdk_step_id,
        search_name=src.search_name,
        record_type=genes.record_class,
        parameters=src.parameters,
        conversation_id=deps.conversation_id,
        homes=genes.homes,
    )
    await store_gene_set(gs)
    created = CreatedGeneSet(
        id=gs.id,
        name=gs.name,
        gene_count=len(gs.gene_ids),
        record_type=gs.record_type,
    )
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
                f"saved in PathFinder. A conversation on "
                f"{_or(sites_that_list(gs.site_id, gs.homes))} can start from it; "
                "it reaches the VEuPathDB workspace only when it is published."
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


def _or(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"


async def list_gene_sets(
    ctx: RunContext[AgentDeps],
) -> ToolReturn[GeneSetListResponse]:
    """List the gene sets the user saved that hold genes of this site.

    The sets this conversation saved come first, each marked ``savedHere``.
    Every row names its gene count, source and id, the site it was saved on,
    and how many of its genes this site holds: a set saved on OrthoMCL or the
    portal lists here with this site's genes alone. ``outOfDate`` names why a
    set no longer holds its strategy's result.
    """
    deps = ctx.deps
    stored = await list_stored_gene_sets(site_id=deps.site_id, user_id=deps.user_id)
    kind = site_kind(deps.site_id)
    rows = [
        GeneSetListItem(
            id=gs.id,
            name=gs.name,
            gene_count=len(gs.gene_ids),
            source=gs.source,
            search_name=gs.search_name,
            has_wdk_step=gs.wdk_step_id is not None,
            saved_here=saved_here(gs.conversation_id, deps.conversation_id),
            saved_on=gs.site_id,
            genes_on_this_site=len(gs.genes_on(deps.site_id, kind)),
            record_noun=counted_noun(gs.record_type or gene_record_class(kind)),
            out_of_date=gs.out_of_date,
        )
        for gs in stored
    ]
    ordered = sorted(rows, key=lambda row: not row.saved_here)
    here = sum(row.saved_here for row in rows)
    listed = ListedGeneSets(
        site_id=deps.site_id,
        gene_sets=[
            ListedGeneSet(
                id=row.id,
                name=row.name,
                gene_count=row.gene_count,
                genes_here=row.genes_on_this_site,
                saved_on=row.saved_on,
                saved_here=row.saved_here,
                record_noun=row.record_noun,
                out_of_date=row.out_of_date,
            )
            for row in ordered
        ],
    )
    return with_summary(
        GeneSetListResponse(gene_sets=ordered, total_sets=len(rows)),
        f"{count_noun(len(rows), 'gene set')}, {here} saved in this conversation",
        ctx=ctx,
        extra=[gene_set_list_chunk(listed)],
    )
