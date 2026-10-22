"""The parameter sheet a criterion decides from, and the dependents it reopens."""

from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.parameters import match_exact_option, to_wire
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    ResolvedParams,
    build_sheet,
    format_param_info_typed,
    read_search_definition,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._catalog_models import (
    register_search,
    search_display_name,
    what_it_finds,
)
from pathfinder.ai.tools.standalone._frame_eda import (
    refuse_a_search_the_criterion_cannot_use,
)
from pathfinder.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    ParamProposals,
    refuse_unmatched_value,
)
from pathfinder.ai.tools.standalone._frame_qualifiers import (
    refuse_a_qualifier_the_search_drops,
)
from pathfinder.ai.tools.standalone._frame_result import (
    SetCriterionResult,
    criterion_return,
)
from pathfinder.ai.tools.standalone._frame_unserved import an_unserved_search_refused
from pathfinder.ai.tools.standalone._qualifier_words import proposal_values
from pathfinder.domain.strategy.operational_spec import Criterion


def _decided_here(info: ParameterInfo, params: ParamProposals) -> bool:
    """The proposal for this param names an entry of the vocabulary shown here."""
    if info.name not in params:
        return False
    values = proposal_values(params[info.name])
    options = info.vocabulary()
    return bool(values) and all(
        match_exact_option(options, value) is not None for value in values
    )


async def reconcile_dependents(
    fetch_at: ParamFetcher,
    infos: list[ParameterInfo],
    resolved: ResolvedParams,
    call: CriterionCall,
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
            refuse_unmatched_value(call, info, options)
    for info in stale:
        state.mark_redecided(call.criterion_id, call.search_name, info.name)
    if not stale:
        return []
    state.pin_fresh_vocabularies(
        call.criterion_id, call.search_name, build_sheet(stale, query=call.text)
    )
    return [info.name for info in stale]


def open_parameter_sheet(
    state: AgentToolState, criterion_id: str, search_name: str, definition: WDKSearch
) -> dict[str, None]:
    """Pin the parameter sheet for one criterion and answer with its template."""
    entries = build_sheet(
        format_param_info_typed(definition.parameters or []),
        query=state.operational_spec_draft.goal,
    )
    runs = f"{search_display_name(definition)}: {what_it_finds(definition)}"
    return state.pin_sheet(
        criterion_id, search_name, entries, what_runs=runs
    ).params_template()


async def open_the_sheet(
    ctx: RunContext[AgentDeps],
    stated: Criterion,
    search_name: str,
    record_type: str,
) -> ToolReturn[SetCriterionResult]:
    with an_unserved_search_refused(ctx, stated.id, search_name, record_type):
        definition = await read_search_definition(
            ctx.deps.site_id, record_type, search_name
        )
    await refuse_a_search_the_criterion_cannot_use(
        ctx, record_type, definition, stated, None
    )
    unread = await refuse_a_qualifier_the_search_drops(
        ctx, record_type, definition, stated
    )
    register_search(ctx.deps.agent_state, definition, record_type)
    return criterion_return(
        ctx,
        SetCriterionResult(
            criterion_id=stated.id,
            search_name=search_name,
            params_template=open_parameter_sheet(
                ctx.deps.agent_state, stated.id, search_name, definition
            ),
            sheet_pinned=True,
            unread_searches=unread,
        ),
        record_type,
        definition,
    )
