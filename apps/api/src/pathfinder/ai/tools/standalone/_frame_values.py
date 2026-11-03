"""The values one set_criterion call binds: the proposal on each parameter's
scale, then each value with who set it and the label the site gives it."""

from __future__ import annotations

from dataclasses import replace

from veupathdb.domain.parameters import ParamValue, param_value_from_raw
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, ortho_taxonomy

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_measure import labelled_picks
from pathfinder.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    left_to_the_site,
)
from pathfinder.ai.tools.standalone._frame_sources import (
    bound_values,
    card_values_of,
    on_the_sites_scale,
    quotes_by_param,
    stated_by_their_labels,
    stated_by_their_taxa,
)
from pathfinder.domain.strategy.constraints import Constraint
from pathfinder.domain.strategy.named_taxa import (
    OrganismTree,
    organism_trees,
    phyletic_organism_tree,
)
from pathfinder.domain.strategy.one_sided import with_open_ends_bound
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Measurement,
    RequirementLink,
)
from pathfinder.domain.strategy.organism_steps import UNMARKED_ORGANISM_PARAMS
from pathfinder.services.strategies.sheet_params import vocabularies_under


def _proposed_ranges(
    call: CriterionCall, infos: list[ParameterInfo]
) -> dict[str, ParamValue]:
    ranges: dict[str, ParamValue] = {}
    for info in infos:
        match call.params.get(info.name):
            case str(text) if info.param_kind == "number-range":
                try:
                    ranges[info.name] = param_value_from_raw(text, info.param_kind)
                except ValueError:
                    continue
            case _:
                continue
    return ranges


def _with_open_ends(
    call: CriterionCall,
    infos: list[ParameterInfo],
    answers: list[RequirementLink],
    requirements: list[Constraint],
) -> tuple[CriterionCall, list[str]]:
    ranges = _proposed_ranges(call, infos)
    opened, corrections = with_open_ends_bound(ranges, answers, requirements, infos)
    moved = {n: v.to_wire() for n, v in opened.items() if v != ranges[n]}
    return replace(call, params={**call.params, **moved}), corrections


def proposed_call(
    call: CriterionCall,
    infos: list[ParameterInfo],
    state: AgentToolState,
    answers: list[RequirementLink],
) -> tuple[CriterionCall, list[str]]:
    """The call without what only the site sets, each number on its
    parameter's scale, each range's open end bound, and one correction for each
    change."""
    kept, fixed = left_to_the_site(call, infos)
    rescaled, corrections = on_the_sites_scale(kept, infos, state.request_messages)
    opened, ends = _with_open_ends(rescaled, infos, answers, state.stated_requirements)
    return opened, [*fixed, *corrections, *ends]


async def _taxa_trees(site_id: str, definition: WDKSearch) -> dict[str, OrganismTree]:
    trees = organism_trees(definition)
    param = UNMARKED_ORGANISM_PARAMS.get(definition.url_segment)
    taxonomy = None if param is None else await ortho_taxonomy(site_id)
    if param is not None and taxonomy is not None:
        trees[param] = phyletic_organism_tree(taxonomy)
    return trees


async def sourced_values(
    state: AgentToolState,
    call: CriterionCall,
    values: dict[str, ParamValue],
    *,
    site_id: str,
    definition: WDKSearch,
    infos: list[ParameterInfo],
    fetch_at: ParamFetcher,
    site_supplied: set[str],
    reason: str,
    answers: list[RequirementLink],
) -> tuple[dict[str, BoundValue], list[Measurement]]:
    """Each value with who set it, and the label the site gives each pick; a
    value a message names by its labels or by its taxon is stated. ``infos``
    is the published sheet, and each dependent vocabulary is read under the
    bound parents."""
    bound = bound_values(
        values,
        infos=await vocabularies_under(fetch_at, infos, values),
        site_supplied=site_supplied,
        request_texts=state.request_messages,
        reason=reason,
        card_values=card_values_of(state.operational_spec_draft, call.criterion_id),
        linked_quotes=quotes_by_param(answers, state.stated_requirements),
    )
    labels = await labelled_picks(fetch_at, infos, call, bound)
    restated = stated_by_their_labels(bound, labels, infos, state.request_messages)
    named = stated_by_their_taxa(
        restated, await _taxa_trees(site_id, definition), state.request_messages
    )
    return named, labels


__all__ = ["proposed_call", "sourced_values"]
