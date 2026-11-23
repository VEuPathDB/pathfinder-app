"""The proposed values of one set_criterion call, and the retries they earn."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from pydantic import JsonValue
from pydantic_ai import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import (
    KeptValue,
    ParamValue,
    StringValue,
    entry_name,
    stated_form,
)
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import (
    RADIO_OFF,
    BoundValues,
    FilterReads,
    ParameterInfo,
    ParamFetcher,
    ParamIntent,
    PhyleticListError,
    Provenance,
    RadioPairIssue,
    ResolveContext,
    ResolvedParams,
    UnknownParameterError,
    WDKFilterReads,
    check_radio_pairs,
    radio_pairs,
    read_under_parents,
    resolve_params_with_intent,
)
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError

from strategist.ai.agents.state import AgentToolState
from strategist.ai.lead.site_routes import portal_route_sentence
from strategist.ai.tools.standalone._catalog_elsewhere import (
    joined,
    reach_sentence,
    tree_tops,
)
from strategist.domain.refusal import Problem, Problems, RefusalKey
from strategist.domain.strategy.genome_group_steps import criterion_as_stated
from strategist.domain.strategy.operational_spec import BoundValue
from strategist.domain.strategy.value_binding import pick_terms
from strategist.platform.refusals import (
    FaultRow,
    ProblemsRefusal,
    library_problems,
    library_rows,
)


@dataclass(frozen=True)
class CriterionCall:
    """The one call's identity, carried through the checks it drives: the
    values as stated, and as their parameters read them."""

    criterion_id: str
    search_name: str
    text: str
    params: dict[str, JsonValue]
    values: dict[str, ParamValue] = field(default_factory=dict)
    held: dict[str, BoundValue] = field(default_factory=dict)
    held_names: frozenset[str] = frozenset()

    def terms(self, name: str) -> list[str]:
        return pick_terms(self.values[name]) if name in self.values else []

    def with_values(self, values: Mapping[str, ParamValue]) -> CriterionCall:
        params = {n: v for n, v in self.params.items() if n not in values}
        for name, value in values.items():
            match stated_form(value):
                case KeptValue():
                    pass
                case form:
                    params[name] = form
        return replace(self, params=params, values={**self.values, **values})

    def with_read(self, values: BoundValues) -> CriterionCall:
        params = {
            name: given
            for name, given in self.params.items()
            if name not in values or not _kept(values[name])
        }
        return replace(self, params=params, values=dict(values))


def _kept(value: ParamValue) -> bool:
    match stated_form(value):
        case KeptValue():
            return True
        case _:
            return False


def held_binding(
    state: AgentToolState, call: CriterionCall, infos: list[ParameterInfo]
) -> dict[str, BoundValue]:
    held = next(
        (
            c
            for c in state.operational_spec_draft.criteria
            if c.id == call.criterion_id and c.search_name == call.search_name
        ),
        None,
    )
    bindable = {info.name for info in infos if info.bindable}
    if held is None:
        return {}
    return {
        name: bound
        for name, bound in criterion_as_stated(held).resolved_params.items()
        if name in bindable
    }


def with_held(call: CriterionCall, held: Mapping[str, BoundValue]) -> CriterionCall:
    unstated = {n: b.value for n, b in held.items() if n not in call.params}
    return replace(
        call.with_values(unstated), held=dict(held), held_names=frozenset(unstated)
    )


def keeping_held(
    resolved: ResolvedParams, call: CriterionCall, held: Mapping[str, BoundValue]
) -> ResolvedParams:
    kept = {n: b.value for n, b in held.items() if n not in call.params}
    return resolved.model_copy(
        update={
            "params": {**resolved.params, **kept},
            "provenance": {
                **resolved.provenance,
                **dict.fromkeys(kept, Provenance.STATED),
            },
        }
    )


def _filter_reads(search: SearchContext) -> FilterReads:
    return WDKFilterReads(search.site_id, search.record_type, search.search_name)


async def _elsewhere(
    definition: WDKSearch,
    problems: Problems,
    rows: list[FaultRow],
    state: AgentToolState,
    site_id: str,
) -> Problems:
    """The problems, the first term another site holds sent to the portal."""
    first = next((row for row in rows if row.value), None)
    if first is None:
        return problems
    others = await _other_sites_holding(site_id, definition, first.param, first.value)
    if not others:
        return problems
    state.portal_route = portal_route_sentence(site_id)
    route = (
        f"{reach_sentence(definition, first.param, site_id, first.value)} "
        f"{first.value} is on {joined(others)}. A conversation stays on its site: "
        f"bind nothing for this criterion, ask no question about it, and write this "
        f"in the summary word for word, link included: {state.portal_route}"
    )
    return Problems(
        found=tuple(
            Problem(key=p.key, sentence=f"{p.sentence} {route}")
            if p.key.parameter == first.param
            else p
            for p in problems.found
        )
    )


def nothing_recorded(problems: Problems) -> Problems:
    *head, last = problems.found
    closed = Problem(key=last.key, sentence=f"{last.sentence} Nothing was recorded.")
    return Problems(found=(*head, closed))


async def read_call(
    search: SearchContext,
    fetch_at: ParamFetcher,
    call: CriterionCall,
    *,
    definition: WDKSearch,
    state: AgentToolState,
    about: ResolveContext,
) -> tuple[CriterionCall, dict[str, BoundValue]]:
    stated = {name: v for name, v in call.params.items() if v is not None}
    try:
        values = await read_under_parents(
            fetch_at,
            stated,
            _filter_reads(search),
            about=about,
            bound={
                name: bound.value
                for name, bound in call.held.items()
                if name not in call.params or call.params[name] is not None
            },
        )
    except ValidationError as exc:
        key = RefusalKey(
            check="stated_value",
            criterion=call.criterion_id,
            search=search.search_name,
        )
        problems = await _elsewhere(
            definition,
            library_problems(exc, key),
            library_rows(exc),
            state,
            search.site_id,
        )
        raise ProblemsRefusal(nothing_recorded(problems)) from exc
    read = call.with_read(values)
    given_back = {name for name in call.params if name not in read.params}
    kept = {
        name: bound
        for name, bound in call.held.items()
        if name in call.held_names or name in given_back
    }
    return read, kept


def left_to_the_site(
    call: CriterionCall, infos: list[ParameterInfo]
) -> tuple[CriterionCall, list[str]]:
    """The call without the parameters the site sets, and one correction for
    each proposal of one, whatever its value."""
    set_by_site = {i.name for i in infos if i.site_set}
    site_set = [name for name in call.params if name in set_by_site]
    corrections = [
        f"{name} is set by the site, so the proposal was left out" for name in site_set
    ]
    params = {n: v for n, v in call.params.items() if n not in site_set}
    return replace(call, params=params), corrections


async def _other_sites_holding(
    site_id: str, definition: WDKSearch, param_name: str, value: str
) -> list[str]:
    """The other sites that hold an organism this transform cannot reach.

    Only a transform's organism tree names organisms, so nothing else asks.
    """
    if not definition.allowed_primary_input_record_class_names:
        return []
    if not tree_tops(definition, param_name):
        return []
    try:
        holders = await catalog.sites_holding_organism(value)
    except SemanticIndexUnavailableError:
        return []
    return [held for held in holders if held != site_id]


def _said(value: ParamValue) -> str | list[str]:
    match value:
        case StringValue(value=text):
            return text
        case _:
            return pick_terms(value)


def radio_overrides(
    definition: WDKSearch, call: CriterionCall, infos: list[ParameterInfo]
) -> tuple[dict[str, str], Problems]:
    """The off value for each free-text half of a pair the search ORs.

    The pairs are declared in the search properties, which the sheet drops. A
    free-text half that states the criterion is a problem.
    """
    said = {name: _said(value) for name, value in call.values.items()}
    overrides, issue = check_radio_pairs(
        radio_pairs(definition.properties), infos, said
    )
    if issue is None:
        return overrides, Problems()
    key = RefusalKey(check="radio", parameter=issue.pair.free_text)
    return overrides, Problems.one(key, _radio_retry(call, issue, infos))


def _published_default(infos: list[ParameterInfo], name: str) -> str | None:
    """The default the search publishes for a param, as it is stated, or
    ``None`` for none.

    An empty list and a blank string are refused by the search that publishes
    them, so neither states a value the query would use.
    """
    published = next((i.default for i in infos if i.name == name), None)
    if published in (None, "", []):
        return None
    return json.dumps(published)


def _radio_retry(
    call: CriterionCall, issue: RadioPairIssue, infos: list[ParameterInfo]
) -> str:
    """Names the bindings the pair allows and the entries nearest to the value."""
    pair = issue.pair
    published = _published_default(infos, pair.vocabulary)
    holds = (
        f"{pair.vocabulary} default {published} would still contribute"
        if published is not None
        else f"{pair.vocabulary} cannot be left empty"
    )
    in_vocabulary = (
        f"the criterion in {pair.vocabulary} (nearest entries for "
        f"{issue.free_value!r}: {[entry_name(e) for e in issue.nearest]}; for a "
        f"wildcard use "
        f"get_parameter_options({call.search_name}, '{pair.vocabulary}', "
        f"query=[<every phrasing of the concept>]) and list the entries a phrase "
        f"matched) and pass {RADIO_OFF} for {pair.free_text}."
    )
    halves = (
        f"{pair.free_text} and {pair.vocabulary} on {call.search_name} are ORed "
        f"halves of one criterion"
    )
    offered = any(
        option.value == RADIO_OFF
        for info in infos
        if info.name == pair.vocabulary
        for option in info.vocabulary()
    )
    if offered:
        return (
            f"{halves} ({holds}). Either pass {RADIO_OFF} for {pair.vocabulary} "
            f"to search by the {pair.free_text} value alone, or put {in_vocabulary}"
        )
    return (
        f"{halves}; the vocabulary half carries it and cannot be switched off "
        f"({holds}). Put {in_vocabulary}"
    )


async def resolve_proposals(
    search: SearchContext,
    fetch_at: ParamFetcher,
    call: CriterionCall,
    radio: Mapping[str, str],
    about: ResolveContext,
) -> ResolvedParams:
    """The binding the catalog resolves from every stated value and the off value
    of each radio half."""
    stated = {name: v for name, v in call.params.items() if v is not None}
    try:
        return await resolve_params_with_intent(
            about=about,
            fetch_at=fetch_at,
            filter_reads=_filter_reads(search),
            intent=ParamIntent(text=call.text),
            search=search,
            stated={**stated, **radio},
        )
    except UnknownParameterError as exc:
        msg = (
            f"{exc.detail} The valid names are listed above; do not request the "
            f"sheet again."
        )
        raise ModelRetry(msg) from exc
    except PhyleticListError as exc:
        msg = (
            f"{call.search_name}: {exc.detail} A genus or common name is not a "
            f"node: name a species or a clade code from the included_species / "
            f"excluded_species vocabulary on the sheet, or call "
            f"lookup_phyletic_codes(query). Nothing was recorded."
        )
        raise ModelRetry(msg) from exc
    except ValidationError as exc:
        msg = f"{exc.detail or exc.title} Nothing was recorded."
        raise ModelRetry(msg) from exc
