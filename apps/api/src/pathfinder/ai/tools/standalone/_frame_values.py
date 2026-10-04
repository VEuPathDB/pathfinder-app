"""The values one set_criterion call binds: the proposal on each parameter's
scale, then each value with who set it and the label the site gives it."""

from __future__ import annotations

from veupathdb.domain.parameters import ParamValue
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher

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
    stated_by_their_labels,
    stated_by_their_taxa,
)
from pathfinder.domain.strategy.named_taxa import organism_trees
from pathfinder.domain.strategy.operational_spec import BoundValue, Measurement
from pathfinder.services.strategies.sheet_params import vocabularies_under


def proposed_call(
    call: CriterionCall, infos: list[ParameterInfo], request_texts: list[str]
) -> tuple[CriterionCall, list[str]]:
    """The call without what only the site sets, each number on its
    parameter's scale, and one correction for each change."""
    kept, fixed = left_to_the_site(call, infos)
    rescaled, corrections = on_the_sites_scale(kept, infos, request_texts)
    return rescaled, [*fixed, *corrections]


async def sourced_values(
    state: AgentToolState,
    call: CriterionCall,
    values: dict[str, ParamValue],
    *,
    definition: WDKSearch,
    infos: list[ParameterInfo],
    fetch_at: ParamFetcher,
    site_supplied: set[str],
    reason: str,
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
        requirement_phrases=[c.requested_value for c in state.stated_requirements],
    )
    labels = await labelled_picks(fetch_at, infos, call, bound)
    restated = stated_by_their_labels(bound, labels, infos, state.request_messages)
    named = stated_by_their_taxa(
        restated, organism_trees(definition), state.request_messages
    )
    return named, labels


__all__ = ["proposed_call", "sourced_values"]
