"""The values one set_criterion call binds: the proposal on each parameter's
scale, then each value with who set it and the label the site gives it."""

from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.parameters import ParamValue
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, ortho_taxonomy

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._frame_measure import labelled_picks
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.ai.tools.standalone._frame_sources import (
    bound_values,
    card_values_of,
    on_the_sites_scale,
    quotes_by_param,
    restated_choices,
    stated_by_their_labels,
    stated_by_their_taxa,
)
from strategist.domain.refusal import Problems
from strategist.domain.strategy.constraints import Constraint
from strategist.domain.strategy.named_taxa import (
    OrganismTree,
    organism_trees,
    phyletic_organism_tree,
)
from strategist.domain.strategy.one_sided import with_open_ends_bound
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
    RequirementLink,
)
from strategist.domain.strategy.organism_steps import UNMARKED_ORGANISM_PARAMS
from strategist.domain.strategy.value_source import taken_elsewhere
from strategist.services.strategies.sheet_params import vocabularies_under


def _with_open_ends(
    call: CriterionCall,
    infos: list[ParameterInfo],
    answers: list[RequirementLink],
    requirements: list[Constraint],
) -> tuple[CriterionCall, list[str]]:
    kinds = {info.name: info.param_kind for info in infos}
    ranges = {n: v for n, v in call.values.items() if kinds.get(n) == "number-range"}
    opened, corrections = with_open_ends_bound(ranges, answers, requirements, infos)
    moved = {n: v for n, v in opened.items() if v != ranges[n]}
    return call.with_values(moved), corrections


def proposed_call(
    call: CriterionCall,
    infos: list[ParameterInfo],
    state: AgentToolState,
    answers: list[RequirementLink],
) -> tuple[CriterionCall, list[str]]:
    """The read call with each number on its parameter's scale and each range's
    open end bound, and one correction for each change."""
    rescaled, corrections = on_the_sites_scale(call, infos, state.request_messages)
    opened, ends = _with_open_ends(rescaled, infos, answers, state.stated_requirements)
    return opened, [*corrections, *ends]


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
) -> tuple[dict[str, BoundValue], list[Measurement], Problems]:
    """Each value with who set it, and the label the site gives each pick; a
    value a message names by its labels or by its taxon is stated. ``infos``
    is the published sheet, and each dependent vocabulary is read under the
    bound parents."""
    draft = state.operational_spec_draft
    taken = taken_elsewhere(draft, call.criterion_id)
    bound = bound_values(
        values,
        infos=await vocabularies_under(fetch_at, infos, values),
        site_supplied=site_supplied,
        request_texts=state.request_messages,
        reason=reason,
        card_values=card_values_of(draft, call.criterion_id),
        linked_quotes=quotes_by_param(answers, state.stated_requirements),
        taken=taken,
    )
    labels, unlabelled = await labelled_picks(fetch_at, infos, call, bound)
    restated = stated_by_their_labels(
        bound, labels, infos, state.request_messages, taken
    )
    trees = await _taxa_trees(site_id, definition)
    named = stated_by_their_taxa(restated, trees, state.request_messages, infos, taken)
    state.operational_spec_draft = _siblings_judged_again(
        draft,
        call,
        named,
        infos=infos,
        trees=trees,
        request_texts=state.request_messages,
    )
    return named, labels, unlabelled


def _siblings_judged_again(
    draft: OperationalSpec,
    call: CriterionCall,
    bound: dict[str, BoundValue],
    *,
    infos: list[ParameterInfo],
    trees: Mapping[str, OrganismTree],
    request_texts: list[str],
) -> OperationalSpec:
    """The draft with each criterion of the same search judged again against
    the values this binding takes, so the other side of a comparison it binds
    is stated."""
    held = draft.model_copy(
        update={
            "criteria": [
                *(c for c in draft.criteria if c.id != call.criterion_id),
                Criterion(
                    id=call.criterion_id,
                    text=call.text,
                    search_name=call.search_name,
                    resolved_params=bound,
                ),
            ]
        }
    )
    return draft.model_copy(
        update={
            "criteria": [
                c.model_copy(
                    update={
                        "resolved_params": restated_choices(
                            c.resolved_params,
                            infos=infos,
                            labels=c.measurements,
                            trees=trees,
                            request_texts=request_texts,
                            taken=taken_elsewhere(held, c.id),
                        )
                    }
                )
                if c.id != call.criterion_id and c.search_name == call.search_name
                else c
                for c in draft.criteria
            ]
        }
    )


__all__ = ["proposed_call", "sourced_values"]
