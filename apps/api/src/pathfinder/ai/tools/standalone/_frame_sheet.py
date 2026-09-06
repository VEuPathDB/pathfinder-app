"""The parameter sheet a criterion decides from, and the dependents it reopens."""

from __future__ import annotations

from veupathdb.domain.parameters.value_codec import to_wire
from veupathdb.domain.parameters.wdk_vocab import match_exact_option
from veupathdb.wdk.wdk_models import WDKSearch
from veupathdb_mcp.catalog.param_dag import ParamFetcher, ResolvedParams
from veupathdb_mcp.catalog.param_formatting import (
    ParameterInfo,
    format_param_info_typed,
)
from veupathdb_mcp.catalog.param_sheet import SheetEntry, build_sheet

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_proposals import (
    ParamProposals,
    _CriterionCall,
    _refuse_unmatched_value,
    _values_of,
)

_RE_SHEET_NOTE = (
    "vocabulary shown in the first sheet; use get_parameter_options(search_name, "
    "parameter_id, query=...) for an entry you no longer see"
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
) -> list[SheetEntry]:
    """Visible dependent params to hand back with the vocabulary the parents produce.

    The sheet was read under the search defaults, so a proposal made from it does
    not decide the vocabulary the bound parents produce. A param already handed
    back for this criterion is decided by whatever the re-call says, so it is
    validated against the fresh vocabulary instead of asked again.
    """
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
    return build_sheet(stale, query=call.text)


def _sheet_for(
    state: AgentToolState, criterion_id: str, search_name: str, definition: WDKSearch
) -> list[SheetEntry]:
    """The parameter sheet for one criterion, without repeating a vocabulary.

    The second sheet for the same criterion and search carries every parameter
    but no vocabulary, which the model already holds.
    """
    entries = build_sheet(
        format_param_info_typed(definition.parameters or []),
        query=state.operational_spec_draft.goal,
    )
    if not state.was_sheet_shown(criterion_id, search_name):
        state.mark_sheet_shown(criterion_id, search_name)
        return entries
    return [
        entry.model_copy(update={"vocabulary": [], "vocabulary_note": _RE_SHEET_NOTE})
        for entry in entries
    ]
