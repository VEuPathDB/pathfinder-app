"""The parameter sheet a criterion decides from, and the dependents it reopens."""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.parameters import (
    VocabularyEntryError,
    entries_or_refusal,
    match_exact_option,
    wire_map,
)
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    ResolvedParams,
    build_sheet,
    eda_backed_search,
    format_param_info_typed,
    organism_parameter_of,
    read_search_definition,
)

from strategist.ai.agents.state import AgentToolState
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.standalone._catalog_models import (
    register_search,
    search_display_name,
    what_it_finds,
)
from strategist.ai.tools.standalone._frame_eda import (
    wait_for_the_analysis,
)
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.ai.tools.standalone._frame_result import (
    SetCriterionResult,
    criterion_return,
)
from strategist.ai.tools.standalone._frame_stages import search_stage
from strategist.ai.tools.standalone._frame_unserved import an_unserved_search_refused
from strategist.domain.strategy.operational_spec import Criterion


def _decided_here(info: ParameterInfo, call: CriterionCall) -> bool:
    """The proposal for this param names an entry of the vocabulary shown here."""
    values = call.terms(info.name)
    options = info.vocabulary()
    return bool(values) and all(
        match_exact_option(options, value) is not None for value in values
    )


async def reconcile_dependents(
    site_id: str,
    fetch_at: ParamFetcher,
    infos: list[ParameterInfo],
    resolved: ResolvedParams,
    call: CriterionCall,
    state: AgentToolState,
) -> list[str]:
    """Bindable dependent params to decide again under the parents' vocabulary.

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
        if info.stated_parents
    }
    if not on_the_sheet:
        return []
    context = wire_map(resolved.params)
    stale: list[ParameterInfo] = []
    declarations = await fetch_at(context)
    organism = await organism_parameter_of(site_id, declarations)
    for info in format_param_info_typed(declarations, organism=organism):
        if info.name not in on_the_sheet:
            continue
        options = info.vocabulary()
        changed = {option.value for option in options} != on_the_sheet[info.name]
        asked = state.was_redecided(call.criterion_id, call.search_name, info.name)
        if changed and not asked and not _decided_here(info, call):
            stale.append(info)
        elif info.param_kind != "filter":
            try:
                entries_or_refusal(info.name, options, call.terms(info.name))
            except VocabularyEntryError as exc:
                msg = f"{exc.detail} Nothing was recorded."
                raise ModelRetry(msg) from exc
    for info in stale:
        state.mark_redecided(call.criterion_id, call.search_name, info.name)
    if not stale:
        return []
    state.pin_fresh_vocabularies(
        call.criterion_id, call.search_name, build_sheet(stale, query=call.text)
    )
    return [info.name for info in stale]


def open_parameter_sheet(
    state: AgentToolState,
    criterion_id: str,
    search_name: str,
    definition: WDKSearch,
    *,
    organism: str | None,
) -> dict[str, None]:
    """Pin the parameter sheet for one criterion and answer with its template."""
    infos = format_param_info_typed(definition.parameters or [], organism=organism)
    state.record_read(search_name, infos)
    entries = build_sheet(infos, query=state.operational_spec_draft.goal)
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
    described = eda_backed_search(definition)
    if described is not None:
        return wait_for_the_analysis(
            ctx, stated, described, definition, record_type, None
        )
    await search_stage(ctx, stated, definition, record_type)
    register_search(ctx.deps.agent_state, definition, record_type)
    return criterion_return(
        ctx,
        SetCriterionResult(
            criterion_id=stated.id,
            search_name=search_name,
            params_template=open_parameter_sheet(
                ctx.deps.agent_state,
                stated.id,
                search_name,
                definition,
                organism=await organism_parameter_of(
                    ctx.deps.site_id, definition.parameters or []
                ),
            ),
            sheet_pinned=True,
        ),
        record_type,
        definition,
    )
