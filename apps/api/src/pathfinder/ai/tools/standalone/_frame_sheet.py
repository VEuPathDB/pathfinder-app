"""The parameter sheet a criterion decides from, and the dependents it reopens."""

from __future__ import annotations

from veupathdb.domain.parameters import match_exact_option, to_wire
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    ResolvedParams,
    build_sheet,
    format_param_info_typed,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_proposals import (
    ParamProposals,
    _CriterionCall,
    _refuse_unmatched_value,
    _values_of,
)


def _decided_here(info: ParameterInfo, params: ParamProposals) -> bool:
    """The proposal for this param names an entry of the vocabulary shown here."""
    if info.name not in params:
        return False
    values = _values_of(params[info.name])
    options = info.vocabulary()
    return bool(values) and all(
        match_exact_option(options, value) is not None for value in values
    )


async def _reconcile_dependents(
    fetch_at: ParamFetcher,
    infos: list[ParameterInfo],
    resolved: ResolvedParams,
    call: _CriterionCall,
    state: AgentToolState,
) -> list[str]:
    """Visible dependent params to decide again under the parents' vocabulary.

    The sheet was read under the search defaults, so a proposal made from it does
    not decide the vocabulary the bound parents produce. A param already handed
    back for this criterion is decided by whatever the re-call says, so it is
    validated against the fresh vocabulary instead of asked again. Every call
    recomputes the list, so a param this one does not name is no longer asked.
    """
    state.clear_redecide(call.criterion_id)
    on_the_sheet = {
        info.name: {option.value for option in info.vocabulary()}
        for info in infos
        if info.is_visible and info.vocab_depends_on
    }
    if not on_the_sheet:
        return []
    context = {name: to_wire(value) for name, value in resolved.params.items()}
    stale: list[ParameterInfo] = []
    for info in await fetch_at(context):
        if info.name not in on_the_sheet:
            continue
        options = info.vocabulary()
        changed = {option.value for option in options} != on_the_sheet[info.name]
        asked = state.was_redecided(call.criterion_id, call.search_name, info.name)
        if changed and not asked and not _decided_here(info, call.params):
            stale.append(info)
        elif options and info.param_kind != "filter":
            _refuse_unmatched_value(call, info, options)
    for info in stale:
        state.mark_redecided(call.criterion_id, call.search_name, info.name)
    if not stale:
        return []
    state.pin_fresh_vocabularies(
        call.criterion_id, call.search_name, build_sheet(stale, query=call.text)
    )
    return [info.name for info in stale]


def _open_sheet(
    state: AgentToolState, criterion_id: str, search_name: str, definition: WDKSearch
) -> dict[str, None]:
    """Pin the parameter sheet for one criterion and answer with its template."""
    entries = build_sheet(
        format_param_info_typed(definition.parameters or []),
        query=state.operational_spec_draft.goal,
    )
    return state.pin_sheet(criterion_id, search_name, entries).params_template()
