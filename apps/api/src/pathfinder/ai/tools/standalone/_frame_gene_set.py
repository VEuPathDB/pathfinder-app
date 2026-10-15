"""Binding a criterion to a gene set the user saved, on this site or another."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.parameters import InputDatasetValue
from veupathdb.wdk import (
    WDKDatasetConfigIdList,
    WDKDatasetIdListContent,
    get_site,
    get_strategy_api,
)

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._frame_eda import refuse_a_waiting_criterion
from pathfinder.ai.tools.standalone._frame_result import (
    GeneSetBinding,
    SetCriterionResult,
)
from pathfinder.ai.tools.standalone._frame_roles import (
    refuse_a_transform_on_a_saved_input,
)
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.services.evidence.gene_sets import list_stored_gene_sets
from pathfinder.services.gene_sets.homes import ID_LIST_SEARCHES, site_kind
from pathfinder.services.gene_sets.types import GeneSet


async def set_gene_set_criterion(
    ctx: RunContext[AgentDeps], stated: Criterion, *, reference: str
) -> ToolReturn[SetCriterionResult]:
    """Record a criterion whose input is the genes a saved set holds on this site."""
    refuse_a_waiting_criterion(ctx.deps.agent_state, stated.id)
    refuse_a_transform_on_a_saved_input(stated.id, stated.role, "saved gene set")
    binding, search_name = await _bind(ctx, stated, reference)
    return with_summary(
        SetCriterionResult(
            criterion_id=stated.id, search_name=search_name, gene_set=binding
        ),
        f"{stated.id} starts from {binding.name}, "
        f"{binding.genes_here:,} genes on this site",
        ctx=ctx,
    )


async def _bind(
    ctx: RunContext[AgentDeps], stated: Criterion, reference: str
) -> tuple[GeneSetBinding, str]:
    deps = ctx.deps
    listed = await list_stored_gene_sets(site_id=deps.site_id, user_id=deps.user_id)
    named = reference.strip().casefold()
    match = next(
        (gs for gs in listed if named in (gs.id.casefold(), gs.name.casefold())), None
    )
    if match is None:
        raise ModelRetry(_unresolved_message(reference, listed))
    kind = site_kind(deps.site_id)
    genes = match.genes_on(deps.site_id, kind)
    search = ID_LIST_SEARCHES[kind]
    dataset_id = await get_strategy_api(deps.site_id).create_dataset(
        WDKDatasetConfigIdList(
            source_type="idList",
            source_content=WDKDatasetIdListContent(ids=genes),
        )
    )
    deps.agent_state.frame_set_criterion(
        stated.model_copy(
            update={
                "search_name": search.search_name,
                "search_display_name": f"Gene set: {match.name}",
                "param_display_names": {search.param_name: "Genes"},
                "resolved_params": {
                    search.param_name: BoundValue(
                        value=InputDatasetValue(dataset_id=str(dataset_id)),
                        source="chosen",
                        basis=f"the saved gene set {match.name}",
                        label=_label(match, len(genes), deps.site_id),
                    )
                },
            }
        )
    )
    binding = GeneSetBinding(
        id=match.id,
        name=match.name,
        saved_on=match.site_id,
        gene_count=len(match.gene_ids),
        genes_here=len(genes),
    )
    return binding, search.search_name


def _label(gene_set: GeneSet, genes_here: int, site_id: str) -> str:
    if gene_set.site_id == site_id:
        return f"the {genes_here} genes of {gene_set.name}"
    saved_on = get_site(gene_set.site_id).name
    return (
        f"{genes_here} of the {len(gene_set.gene_ids)} genes of {gene_set.name}, "
        f"saved on {saved_on}"
    )


def _unresolved_message(reference: str, listed: list[GeneSet]) -> str:
    if not listed:
        return (
            f"{reference!r} names no gene set: the user has no saved gene set "
            "with genes on this site. Ask the user which genes to start from."
        )
    names = ", ".join(f"{gs.name!r}" for gs in listed)
    return (
        f"{reference!r} names none of the user's gene sets with genes on this "
        f"site: {names}. Call set_criterion again with one of those names, or "
        "ask the user which one they mean."
    )
