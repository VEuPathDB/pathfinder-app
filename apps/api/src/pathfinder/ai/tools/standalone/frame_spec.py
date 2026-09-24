from __future__ import annotations

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import PHYLETIC_LIST_PARAMS, to_wire
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    ParamIntent,
    ResolvedParams,
    UnknownParameterError,
    fetch_search_details,
    make_validation_callbacks,
    read_search_definition,
    resolve_params_with_intent,
    resolve_search_record_type,
    validate_parameters,
    wdk_fetch_at,
)

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._catalog_models import (
    ensure_search_registered,
    register_search,
    search_display_name,
    what_it_finds,
)
from pathfinder.ai.tools.standalone._frame_count import (
    criterion_line,
    record_and_count_criterion,
)
from pathfinder.ai.tools.standalone._frame_eda import (
    refuse_a_bound_analysis,
    refuse_a_search_the_criterion_cannot_use,
    refuse_a_waiting_criterion,
)
from pathfinder.ai.tools.standalone._frame_proposals import (
    DeclaredAssumption,
    ParamProposals,
    _CriterionCall,
    _phyletic_overrides,
    _radio_overrides,
    _refuse_bad_assumptions,
    _refuse_undecided,
    _refuse_unknown_names,
    _refuse_unmatched_values,
)
from pathfinder.ai.tools.standalone._frame_roles import (
    refuse_a_transform_on_a_saved_strategy,
)
from pathfinder.ai.tools.standalone._frame_saved import bind_saved_criterion
from pathfinder.ai.tools.standalone._frame_sheet import (
    _open_sheet,
    _reconcile_dependents,
)
from pathfinder.ai.tools.standalone._validation_helpers import validation_model_retry
from pathfinder.domain.strategy.operational_spec import (
    AssumedValue,
    Criterion,
    CriterionRole,
    OpenSlot,
    ParameterAlternatives,
)
from pathfinder.services.strategies.saved_library import SavedStrategyListing


class SetCriterionResult(CamelModel):
    """Result of binding a criterion to a WDK search and resolving its params."""

    criterion_id: str
    search_name: str
    # The search's name on the site, and its one-line summary once bound: what
    # the step runs, which is what the reply names.
    what_runs: str = ""
    # The saved strategy this criterion reuses as its input, when it names one.
    saved_strategy: SavedStrategyListing | None = None
    # Every visible parameter name mapped to null, in sheet order.
    params_template: dict[str, None] = Field(default_factory=dict)
    # True when this call opened the parameter sheet. Nothing is recorded then:
    # the sheet is pinned in the instructions and the next call decides it.
    sheet_pinned: bool = False
    # Name -> bound value, not just the names. A binding can be syntactically
    # "resolved" and semantically wrong (WDK ships `*reductase` as GenesByText's
    # example default), and reporting only names makes that invisible to the
    # model, the ledger, and the user until the step silently returns zero rows.
    resolved_params: dict[str, str] = Field(default_factory=dict)
    # Params the search defaulted. State these to the user with their values.
    defaulted_params: list[str] = Field(default_factory=list)
    open_slots: list[OpenSlot] = Field(default_factory=list)
    # The records this binding matches, or null when no count was read.
    result_count: int | None = None
    # Filled only when the binding matches no record: one entry per vocabulary
    # parameter that holds values this binding did not take.
    alternatives: list[ParameterAlternatives] = Field(default_factory=list)
    # Dependent params whose vocabulary changed once the parents were bound.
    # A non-empty list means nothing was recorded; decide these and re-call.
    # The fresh vocabulary is on the pinned sheet.
    redecide: list[str] = Field(default_factory=list)


async def _record_type(ctx: RunContext[AgentDeps], search_name: str) -> str:
    """The record type that owns the search, resolved once for the whole call.

    The strategy graph's record type answers whenever the session holds a graph,
    whatever search is named; the catalog resolves the name only without one.
    """
    graph = ctx.deps.strategy_session.get_graph(None)
    return await resolve_search_record_type(
        ctx.deps.site_id,
        search_name,
        graph.record_type if graph is not None else None,
    )


def _memoized_fetch(site_id: str, record_type: str, search_name: str) -> ParamFetcher:
    """Reads the search once per parameter context for the whole call.

    The name check, the DAG walk and the dependent re-read all want the same
    expandParams payload.
    """
    fetch_at = wdk_fetch_at(site_id, record_type, search_name)
    read: dict[tuple[tuple[str, str], ...], list[ParameterInfo]] = {}

    async def memoized(context: dict[str, str]) -> list[ParameterInfo]:
        key = tuple(sorted(context.items()))
        if key not in read:
            read[key] = await fetch_at(context)
        return read[key]

    return memoized


async def _search_definition(search: SearchContext) -> WDKSearch:
    """The published definition of the search, read through the catalog.

    The structural parameters and the search properties are both dropped from the
    sheet. The catalog's per-process cache holds site metadata and no user data.
    """
    response, _ = await fetch_search_details(search)
    return response.search_data


async def _canonical_binding(
    search: SearchContext, resolved: ResolvedParams
) -> tuple[ResolvedParams, list[str]]:
    """The binding WDK renders, and the values WDK supplied rather than accepted.
    A tree parameter scores its leaves alone, so these are the values a count
    and a build both send."""
    try:
        validated = await validate_parameters(
            search,
            parameters=dict(resolved.params),
            callbacks=make_validation_callbacks(search.site_id),
        )
    except ValidationError as exc:
        raise validation_model_retry(
            exc, recordType=search.record_type, searchName=search.search_name
        ) from exc
    canonical = resolved.model_copy(update={"params": validated.params})
    return canonical, validated.substituted


async def set_criterion(
    ctx: RunContext[AgentDeps],
    *,
    criterion_id: str,
    text: str,
    search_name: str = "",
    role: CriterionRole = "filter",
    params: ParamProposals | None = None,
    assumed: list[DeclaredAssumption] | None = None,
    saved_strategy: str = "",
) -> ToolReturn[SetCriterionResult]:
    """Bind a criterion to a WDK search, in two calls.

    ``criterion_id`` names a criterion the strategy already holds a step for, or
    a NEW criterion you are adding. A new one takes a name that says what it
    asks, like ``c_secreted``. To re-bind a criterion that HAS a step, pass
    that step's own id.

    Pass ``saved_strategy`` INSTEAD of ``search_name`` when the criterion's
    input is a strategy the user already saved: give the name (or the id) from
    ``list_saved_strategies``, and the saved strategy becomes that criterion's
    input, collapsed under the combine that uses it. There are no parameters to
    decide then, and a reference the listing does not hold comes back as a retry
    naming the ones it does; ask the user which one rather than dropping it.

    Call this ONCE with no ``params`` to open the PARAMETER SHEET: every
    visible parameter of the search with its type, help, default, dependency,
    and its vocabulary -- whole, or the 200 entries most relevant to the
    request. The sheet is pinned under "Open parameter sheets" in your
    instructions and stays there until the criterion binds; nothing is recorded
    by that call. The result's ``params_template`` is the exact ``params``
    object to send back: copy it and replace each null with a value or leave
    null; do not rename keys. Then call it AGAIN with that ``params`` object.

    A value must be copied from the sheet's vocabulary when the parameter has
    one (a tree parent term selects its children); a number or free text is the
    literal the request states; a filter parameter takes "<facet>=<v1>,<v2>".
    ``null`` means the request does not determine it: the search default applies
    and is reported in ``defaulted_params``, or the parameter becomes an open
    slot when there is no default. Do not pass null for a numeric parameter when
    ``text`` states its value; pass the stated number. Never invent a value; a
    name that is not on the sheet comes back as a retry listing the real ones,
    and a missing vocabulary entry means the search cannot realize the
    criterion, or the value is beyond a shortlisted vocabulary (use
    ``get_parameter_options(query=...)``).

    ``assumed`` records every value you chose that the criterion text does not
    state and that is not the sheet's default, one entry per parameter with the
    value and the reason. Each becomes a constraint the user reads and can
    override. A half of a reference and comparison pair is never assumed.

    ``result_count`` is how many records the binding you just made matches,
    and is null for a search that runs on another step.

    ``alternatives`` is present only when ``result_count`` is 0: one entry per
    vocabulary parameter of this search, with the values the binding took and
    the values it did not. A vocabulary larger than its listing bound reports
    its size alone; read that one with ``get_parameter_options``. Any value you
    take from it that the criterion text does not state is an ``assumed`` entry
    like every other.

    ``redecide`` names the dependent parameters whose vocabulary changed once
    the parents were bound; the pin carries that fresh vocabulary and nothing is
    recorded then. Re-call with the same ``params`` and either a
    value from the fresh vocabulary or the same null for each listed parameter,
    and it closes. Re-call the same way once the user answers an open slot."""
    state = ctx.deps.agent_state
    refuse_a_bound_analysis(state, criterion_id)
    stated = Criterion(id=criterion_id, text=text, role=role)
    if saved_strategy:
        refuse_a_waiting_criterion(state, criterion_id)
        refuse_a_transform_on_a_saved_strategy(criterion_id, role)
        match = await bind_saved_criterion(
            ctx,
            criterion_id=criterion_id,
            text=text,
            role=role,
            reference=saved_strategy,
        )
        return with_summary(
            SetCriterionResult(
                criterion_id=criterion_id, search_name="", saved_strategy=match
            ),
            f"{criterion_id} starts from {match.name}",
            ctx=ctx,
        )
    if not search_name:
        msg = (
            "set_criterion needs a search_name, or a saved_strategy when the "
            "criterion starts from a strategy the user saved "
            "(list_saved_strategies names them)."
        )
        raise ModelRetry(msg)
    record_type = await _record_type(ctx, search_name)
    if params is None:
        definition = await read_search_definition(
            ctx.deps.site_id, record_type, search_name
        )
        await refuse_a_search_the_criterion_cannot_use(
            ctx, record_type, definition, stated, None
        )
        register_search(state, definition, record_type)
        return _criterion_return(
            ctx,
            SetCriterionResult(
                criterion_id=criterion_id,
                search_name=search_name,
                params_template=_open_sheet(
                    state, criterion_id, search_name, definition
                ),
                sheet_pinned=True,
            ),
            record_type,
            definition,
        )
    search = SearchContext(ctx.deps.site_id, record_type, search_name)
    definition = await _search_definition(search)
    await refuse_a_search_the_criterion_cannot_use(
        ctx, record_type, definition, stated, params
    )
    await ensure_search_registered(state, ctx.deps.site_id, record_type, search_name)
    fetch_at = _memoized_fetch(ctx.deps.site_id, record_type, search_name)
    infos = await fetch_at({})
    call = _CriterionCall(
        criterion_id=criterion_id, search_name=search_name, text=text, params=params
    )
    _refuse_unknown_names(call, infos)
    _refuse_undecided(call, infos)
    _refuse_bad_assumptions(call, assumed or [], infos)
    phyletic = _phyletic_overrides(definition, call, infos)
    radio = _radio_overrides(definition, call, infos)
    _refuse_unmatched_values(
        call, infos, PHYLETIC_LIST_PARAMS if phyletic is not None else frozenset()
    )
    # A null proposal states no value, so it leaves the param to resolution.
    overrides = {name: value for name, value in params.items() if value is not None}
    # The derived pattern replaces the two lists it was derived from.
    if phyletic is not None:
        overrides.update(phyletic)
    overrides.update(radio)
    try:
        resolved = await resolve_params_with_intent(
            fetch_at=fetch_at,
            intent=ParamIntent(text=text),
            overrides=overrides,
        )
    except UnknownParameterError as exc:
        msg = (
            f"{exc.detail} The valid names are listed above; do not request the "
            f"sheet again."
        )
        raise ModelRetry(msg) from exc
    if resolved.unread:
        msg = (
            f"The criterion states a quantity and {resolved.unread} was left null. "
            f"Pass the stated value, or say in the criterion text why the default "
            f"is right."
        )
        raise ModelRetry(msg)
    redecide = await _reconcile_dependents(fetch_at, infos, resolved, call, state)
    if redecide:
        return _criterion_return(
            ctx,
            SetCriterionResult(
                criterion_id=criterion_id, search_name=search_name, redecide=redecide
            ),
            record_type,
            definition,
        )
    # A half switched off holds a value the request never stated, so it is
    # disclosed like a default.
    defaulted = sorted(set(resolved.defaulted()) | radio.keys())
    canonical = resolved
    # Only a binding with no open slot is validated: an unresolved required
    # param reads as missing, while a bad value returns a did-you-mean retry.
    if not resolved.open_slots:
        canonical, substituted = await _canonical_binding(search, resolved)
        # WDK renders the spec it would run, so it reports which values are its
        # own. That report is about the search being built and outranks the
        # local reading of the request.
        defaulted = sorted(set(defaulted) | set(substituted))
    open_params = [
        OpenSlot(
            criterion_id=criterion_id,
            param_name=slot.param_name,
            question=slot.question,
            options=slot.options,
        )
        for slot in resolved.open_slots
    ]
    count, alternatives = await record_and_count_criterion(
        ctx,
        Criterion(
            id=criterion_id,
            text=text,
            search_name=search_name,
            search_display_name=search_display_name(definition),
            role=role,
            resolved_params=resolved.params,
            defaulted_params=defaulted,
            open_params=open_params,
            assumptions=[
                AssumedValue(param_name=e.param_name, value=e.value, reason=e.reason)
                for e in assumed or []
            ],
        ),
        record_type=record_type,
        definition=definition,
        resolved=canonical,
        infos=infos,
    )
    return _criterion_return(
        ctx,
        SetCriterionResult(
            criterion_id=criterion_id,
            search_name=search_name,
            resolved_params={
                name: to_wire(value) for name, value in resolved.params.items()
            },
            defaulted_params=defaulted,
            open_slots=open_params,
            result_count=count,
            alternatives=alternatives,
        ),
        record_type,
        definition,
    )


def _criterion_return(
    ctx: RunContext[AgentDeps],
    result: SetCriterionResult,
    record_type: str,
    definition: WDKSearch,
) -> ToolReturn[SetCriterionResult]:
    """The bound criterion, or the parameters the call still leaves open.

    The sheet's own heading carries the summary, so the sheet-opening return
    stays short enough to survive history elision.
    """
    name = search_display_name(definition)
    runs = name if result.sheet_pinned else f"{name}: {what_it_finds(definition)}"
    result = result.model_copy(update={"what_runs": runs})
    if result.sheet_pinned:
        return with_summary(
            result,
            f"{result.criterion_id}: sheet pinned, "
            f"{count_noun(len(result.params_template), 'parameter')} to decide",
            ctx=ctx,
            status="warn",
        )
    pending = len(result.redecide) + len(result.open_slots)
    if pending:
        return with_summary(
            result,
            f"{result.criterion_id}: {count_noun(pending, 'parameter')} still open",
            ctx=ctx,
            status="warn",
        )
    line, status = criterion_line(
        result.criterion_id,
        result.search_name,
        record_type,
        result.result_count,
        result.alternatives,
    )
    return with_summary(result, line, ctx=ctx, status=status)
