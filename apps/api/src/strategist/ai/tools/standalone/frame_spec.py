from __future__ import annotations

from pydantic import JsonValue
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.domain import SearchContext
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKParameter
from veupathdb_mcp.catalog import (
    ParamFetcher,
    ResolveContext,
    ResolvedParams,
    format_param_info_typed,
    make_validation_callbacks,
    organism_parameter_of,
    shortlist_slot,
    validate_parameters,
    wdk_fetch_at,
)

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.standalone._catalog_models import (
    ensure_search_registered,
    search_display_name,
)
from strategist.ai.tools.standalone._expression_handles import (
    with_stored_expressions,
)
from strategist.ai.tools.standalone._frame_answers import (
    AnsweredRequirement,
    linked_requirements,
    refuse_a_param_the_sheet_lacks,
)
from strategist.ai.tools.standalone._frame_computed import set_computed_criterion
from strategist.ai.tools.standalone._frame_datasets import (
    saved_id_lists,
    with_typed_ids,
)
from strategist.ai.tools.standalone._frame_eda import (
    refuse_a_bound_analysis,
    refuse_a_search_the_criterion_cannot_use,
)
from strategist.ai.tools.standalone._frame_gene_set import set_gene_set_criterion
from strategist.ai.tools.standalone._frame_lookups import refuse_a_pick_no_lookup_read
from strategist.ai.tools.standalone._frame_measure import (
    display_names,
    record_bound_criterion,
)
from strategist.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    held_binding,
    keeping_held,
    left_to_the_site,
    radio_overrides,
    read_call,
    refuse_an_upload_the_researcher_lacks,
    refuse_undecided,
    refuse_unknown_names,
    resolve_proposals,
    with_held,
)
from strategist.ai.tools.standalone._frame_rationale import (
    SearchChoice,
    rationale_for,
)
from strategist.ai.tools.standalone._frame_reading import offered_reading
from strategist.ai.tools.standalone._frame_result import (
    SetCriterionResult,
    criterion_return,
)
from strategist.ai.tools.standalone._frame_saved import set_saved_criterion
from strategist.ai.tools.standalone._frame_sheet import (
    open_the_sheet,
    reconcile_dependents,
)
from strategist.ai.tools.standalone._frame_sources import (
    chosen_reason,
    open_slots,
    pasted_params,
)
from strategist.ai.tools.standalone._frame_stated import refuse_what_the_words_decide
from strategist.ai.tools.standalone._frame_unserved import (
    an_unserved_search_refused,
    listed_record_type,
)
from strategist.ai.tools.standalone._frame_values import proposed_call, sourced_values
from strategist.ai.tools.standalone._frame_weight import held_weight
from strategist.ai.tools.standalone._validation_helpers import validation_model_retry
from strategist.domain.strategy.expression_handles import stated_value
from strategist.domain.strategy.operational_spec import (
    Criterion,
    CriterionRole,
)
from strategist.services.strategies.sheet_params import catalog_search_definition


def _memoized_fetch(site_id: str, record_type: str, search_name: str) -> ParamFetcher:
    """Reads the search once per parameter context for the whole call.

    The name check, the DAG walk and the dependent re-read all want the same
    expandParams payload.
    """
    fetch_at = wdk_fetch_at(site_id, record_type, search_name)
    read: dict[tuple[tuple[str, str], ...], list[WDKParameter]] = {}

    async def memoized(context: dict[str, str]) -> list[WDKParameter]:
        key = tuple(sorted(context.items()))
        if key not in read:
            read[key] = await fetch_at(context)
        return read[key]

    return memoized


async def _canonical_binding(
    search: SearchContext, resolved: ResolvedParams, about: ResolveContext
) -> tuple[ResolvedParams, list[str]]:
    """The binding WDK renders, and the values WDK supplied rather than accepted.
    A tree parameter scores its leaves alone, so these are the values a count
    and a build both send."""
    try:
        validated = await validate_parameters(
            search,
            stated=dict(resolved.params),
            callbacks=make_validation_callbacks(search.site_id),
            about=about,
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
    params: dict[str, JsonValue] | None = None,
    saved_strategy: str = "",
    gene_set: str = "",
    computed_groups: str = "",
    why: SearchChoice | None = None,
    reading: str = "",
    answers: list[AnsweredRequirement] | None = None,
    weight: int | None = None,
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

    Pass ``gene_set`` INSTEAD of ``search_name`` when the criterion's input is
    a gene set the user saved: give the name (or the id) from
    ``list_gene_sets``. A set saved on another site, such as OrthoMCL or the
    portal, starts from the genes it holds on this site. The set's genes run
    through the site's gene id search; there are no parameters to decide.

    Pass ``computed_groups`` INSTEAD of ``search_name`` when the criterion is
    the groups of a computed comparison: give the ``groups:`` handle
    ``build_phyletic_expression`` returned. The groups are uploaded to the
    researcher's account as an id list, so it binds only on a turn that asks
    for a strategy or answers the card that offered the save.

    Call this ONCE with no ``params`` to open the PARAMETER SHEET: every
    visible parameter of the search with its type, help, default, dependency,
    and its vocabulary -- whole, or the 200 entries most relevant to the
    request. The sheet is pinned under "Open parameter sheets" in your
    instructions and stays there until the criterion binds; nothing is recorded
    by that call. The result's ``params_template`` is the exact ``params``
    object to send back: copy it and replace each null with a value or leave
    null; do not rename keys. Then call it AGAIN with that ``params`` object.

    Each value takes the shape its sheet entry's schema gives; a filter takes a
    list of {field, value, includeUnknown}. An input-dataset parameter also
    takes a list of the ids the request states, which the tool saves as an ID list.
    ``null`` means the request does not determine it: the search default applies
    and is reported in ``defaulted_params``, or the parameter becomes an open
    slot when there is no default. On a re-bind of a criterion to the same
    search, a name left out of ``params`` keeps the value the criterion holds. Do not pass null for a numeric parameter when
    ``text`` states its value; pass the stated number. Never invent a value; a
    name that is not on the sheet comes back as a retry listing the real ones,
    and a missing vocabulary entry means the search cannot realize the
    criterion, or the value is beyond a shortlisted vocabulary (use
    ``get_parameter_options(query=...)``).

    A number the request writes on the other scale than the parameter's
    display name names (a fold for a log2 parameter, a log2 value for a fold
    one) binds converted to the parameter's scale, and ``corrections`` says so.

    The tool records who set each value: the request when its words state it,
    the site when it is the sheet's default, and you otherwise, with the reason
    in ``why``. A value you chose becomes a constraint the user reads and can
    override.

    ``measurements`` names, one clause each, the label the vocabulary gives
    each pick and, once the binding counts, the count of another reading of
    each value the site or you set: a number at its loosest bound, a quoted
    word in its wildcard form, a phrase in the site search, a quoted phrase as
    any of its words, a species group in at least one member. A pick the
    vocabulary gives no label comes back as a retry naming the labels it holds.

    ``why`` goes on the call with ``params``: why this search and not the others
    the catalog answered.

    ``reading`` goes on the call with ``params`` when the researcher answered,
    in their own words, a question that offered readings on this criterion: the
    label of the offered reading closest to their answer, with that reading's
    values in ``params``. With no such question it is refused.

    ``answers`` goes on the call that binds: each requirement of "Requirements
    the researcher stated" this criterion answers, by its number, and the
    parameter that carries its value when one does. A percentile, fold-change
    or significance requirement is checked only against the parameter named
    there, or against the cut of the analysis the criterion runs. An empty list says it answers none; leaving it out keeps what the
    criterion already answers.

    ``weight`` makes the criterion one search of a ranking plan, a UNION whose
    genes score the weights of the criteria they meet: 1 unless the researcher
    says this evidence matters more. Leaving it out keeps the criterion's weight.

    ``result_count`` is how many records the binding you just made matches,
    and is null for a search that runs on another step or a count that did
    not arrive in time. A binding the site refuses to count is not recorded
    and comes back as a retry naming the site's status.

    ``alternatives`` is present only when ``result_count`` is 0: one entry per
    vocabulary parameter of this search, with the values the binding took and
    the values it did not. A vocabulary larger than its listing bound reports
    its size alone; read that one with ``get_parameter_options``. Any value you
    take from it that the request does not state is recorded as your choice.

    ``redecide`` names the dependent parameters whose vocabulary changed once
    the parents were bound; the pin carries that fresh vocabulary and nothing is
    recorded then. Re-call with the same ``params`` and either a
    value from the fresh vocabulary or the same null for each listed parameter,
    and it closes. Re-call the same way once the user answers an open slot."""
    state = ctx.deps.agent_state
    refuse_a_bound_analysis(state, criterion_id)
    stated = Criterion(
        id=criterion_id,
        text=text,
        role=role,
        answers=linked_requirements(state, criterion_id, answers),
        weight=held_weight(state, criterion_id, weight),
    )
    if gene_set or computed_groups or saved_strategy:
        refuse_a_param_the_sheet_lacks(stated.answers, [])
    if gene_set:
        return await set_gene_set_criterion(ctx, stated, reference=gene_set)
    if computed_groups:
        return await set_computed_criterion(ctx, stated, handle=computed_groups)
    if saved_strategy:
        return await set_saved_criterion(ctx, stated, reference=saved_strategy)
    record_type = await listed_record_type(ctx, criterion_id, search_name)
    if params is None:
        return await open_the_sheet(ctx, stated, search_name, record_type)
    return await _bind_the_search(
        ctx, stated, search_name, record_type, params=params, why=why, reading=reading
    )


async def _bind_the_search(
    ctx: RunContext[AgentDeps],
    stated: Criterion,
    search_name: str,
    record_type: str,
    *,
    params: dict[str, JsonValue],
    why: SearchChoice | None,
    reading: str,
) -> ToolReturn[SetCriterionResult]:
    state = ctx.deps.agent_state
    criterion_id, text, role = stated.id, stated.text, stated.role
    search = SearchContext(ctx.deps.site_id, record_type, search_name)
    fetch_at = _memoized_fetch(ctx.deps.site_id, record_type, search_name)
    with an_unserved_search_refused(ctx, criterion_id, search_name, record_type):
        definition = await catalog_search_definition(
            ctx.deps.site_id, record_type, search_name
        )
        declarations = await fetch_at({})
        infos = format_param_info_typed(
            declarations,
            organism=await organism_parameter_of(ctx.deps.site_id, declarations),
        )
    state.record_read(search_name, infos)
    refuse_a_param_the_sheet_lacks(stated.answers, infos)
    await refuse_a_search_the_criterion_cannot_use(
        ctx, record_type, definition, stated, params
    )
    call, fixed = left_to_the_site(
        with_stored_expressions(
            state,
            CriterionCall(
                criterion_id=criterion_id,
                search_name=search_name,
                text=text,
                params=params,
            ),
        ),
        infos,
    )
    held = held_binding(state, call, infos)
    call = with_held(call, held)
    refuse_unknown_names(call, infos)
    refuse_undecided(call, infos)
    call, typed = await saved_id_lists(ctx.deps.site_id, state, call, infos)
    about = ctx.deps.resolving()
    read, kept = await read_call(
        search, fetch_at, call, definition=definition, state=state, about=about
    )
    call, corrected = proposed_call(read, infos, state, stated.answers)
    await ensure_search_registered(state, ctx.deps.site_id, record_type, search_name)
    radio = radio_overrides(definition, call, infos)
    await refuse_an_upload_the_researcher_lacks(ctx.deps.site_id, definition, call)
    refuse_what_the_words_decide(definition, call, infos, state)
    refuse_a_pick_no_lookup_read(state, definition, call, infos)
    resolved = keeping_held(
        await resolve_proposals(search, fetch_at, call, radio, about), call, kept
    )
    if resolved.unread:
        msg = (
            f"The criterion states a quantity and {resolved.unread} was left null. "
            f"Pass the stated value, or say in the criterion text why the default "
            f"is right."
        )
        raise ModelRetry(msg)
    redecide = await reconcile_dependents(
        ctx.deps.site_id, fetch_at, infos, resolved, call, state
    )
    if redecide:
        return criterion_return(
            ctx,
            SetCriterionResult(
                criterion_id=criterion_id,
                search_name=search_name,
                redecide=redecide,
            ),
            record_type,
            definition,
        )
    # A half switched off holds a value the request never stated, so it is
    # disclosed like a default.
    site_supplied = set(resolved.defaulted()) | radio.keys()
    chosen = rationale_for(ctx, call, record_type, infos, resolved.params, why)
    canonical = resolved
    # Only a binding with no open slot is validated: an unresolved required
    # param reads as missing, while a bad value returns a did-you-mean retry.
    if not resolved.open_slots:
        canonical, substituted = await _canonical_binding(search, resolved, about)
        # WDK renders the spec it would run, so it reports which values are its
        # own. That report is about the search being built and outranks the
        # local reading of the request.
        site_supplied |= set(substituted)
    bound, labels = await sourced_values(
        state,
        call,
        resolved.params,
        site_id=ctx.deps.site_id,
        definition=definition,
        infos=infos,
        fetch_at=fetch_at,
        site_supplied=site_supplied,
        reason=chosen_reason(why, chosen),
        answers=stated.answers,
    )
    bound = with_typed_ids({**bound, **kept}, typed, state.request_messages)
    accepted = offered_reading(state, criterion_id, reading, bound)
    open_params = open_slots(
        criterion_id, resolved.open_slots, infos, pasted_params(definition)
    )
    count, alternatives, measured = await record_bound_criterion(
        ctx,
        Criterion(
            id=criterion_id,
            text=text,
            answers=stated.answers,
            search_name=search_name,
            search_display_name=search_display_name(definition),
            record_class=record_type,
            role=role,
            organism_param=next((i.name for i in infos if i.organism_param), None),
            resolved_params=bound,
            param_display_names=display_names(bound, open_params, infos),
            measurements=labels,
            open_params=open_params,
            rationale=chosen.rationale,
            accepted_reading=accepted,
            weight=stated.weight,
        ),
        record_type=record_type,
        definition=definition,
        canonical=canonical,
        fetch_at=fetch_at,
        infos=infos,
    )
    return criterion_return(
        ctx,
        SetCriterionResult(
            criterion_id=criterion_id,
            search_name=search_name,
            resolved_params={
                name: stated_value(name, value)
                for name, value in resolved.params.items()
                if name in bound and not state.sets_the_site(search_name, name)
            },
            defaulted_params=sorted(
                n for n, b in bound.items() if b.source == "default"
            ),
            open_slots=[shortlist_slot(slot, text) for slot in open_params],
            result_count=count,
            alternatives=alternatives,
            rationale=chosen.rationale,
            corrections=[*fixed, *corrected],
            measurements=measured,
        ),
        record_type,
        definition,
    )
