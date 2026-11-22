"""The proposed values of one set_criterion call, and the retries they earn."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from pydantic import JsonValue
from pydantic_ai import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import (
    MAX_NEAREST_ENTRIES,
    PHYLETIC_LIST_PARAMS,
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
    VocabOption,
    accession_matches,
    match_exact_option,
    nearest_entries,
)
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import (
    RADIO_OFF,
    FilterReads,
    ParameterInfo,
    ParamFetcher,
    ParamIntent,
    PhyleticListError,
    RadioPairIssue,
    ResolvedParams,
    UnknownParameterError,
    WDKFilterReads,
    check_radio_pairs,
    is_phyletic_sheet,
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
from strategist.ai.tools.standalone._vocab_resolution import bound_proposal
from strategist.ai.tools.standalone.gene_set_models import LISTING_PAGE
from strategist.domain.strategy.value_binding import pick_terms
from strategist.services.strategies.user_dataset_searches import (
    dataset_parameter,
    user_dataset_offers,
    user_dataset_types,
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

    def terms(self, name: str) -> list[str]:
        return pick_terms(self.values[name]) if name in self.values else []

    def with_values(self, values: Mapping[str, ParamValue]) -> CriterionCall:
        decoded = {name: value.to_decoded() for name, value in values.items()}
        return replace(
            self,
            params={**self.params, **decoded},
            values={**self.values, **values},
        )


def _filter_reads(search: SearchContext) -> FilterReads:
    return WDKFilterReads(search.site_id, search.record_type, search.search_name)


async def read_call(
    search: SearchContext, fetch_at: ParamFetcher, call: CriterionCall
) -> CriterionCall:
    stated = {name: v for name, v in call.params.items() if v is not None}
    try:
        values = await read_under_parents(fetch_at, stated, _filter_reads(search))
    except ValidationError as exc:
        msg = f"{exc.detail or exc.title} Nothing was recorded."
        raise ModelRetry(msg) from exc
    return replace(call, values=values)


def _bindable(infos: list[ParameterInfo]) -> list[str]:
    return sorted(i.name for i in infos if i.bindable)


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


def refuse_unknown_names(call: CriterionCall, infos: list[ParameterInfo]) -> None:
    """A proposal names a parameter of the search the call may set.

    A null proposal is dropped before the DAG's own name check, so a misspelt
    name paired with a null would otherwise set nothing and say nothing.
    """
    bindable = _bindable(infos)
    unknown = sorted(set(call.params) - set(bindable))
    if unknown:
        nearest = nearest_entries(
            [VocabOption(value=name, display="") for name in bindable],
            unknown[0],
            MAX_NEAREST_ENTRIES,
        )
        msg = (
            f"No such parameter(s) on {call.search_name}: {unknown}. Nearest: "
            f"{nearest}. The valid names are listed above; "
            f"do not request the sheet again. Valid names: {bindable}."
        )
        raise ModelRetry(msg)


def refuse_undecided(call: CriterionCall, infos: list[ParameterInfo]) -> None:
    """Every bindable required parameter needs a value or a null."""
    required = {i.name for i in infos if i.bindable and i.required}
    undecided = sorted(required - set(call.params))
    if undecided:
        msg = (
            f"Decide every required parameter of {call.search_name}: missing "
            f"{undecided}. Pass a value from the sheet, or null for the default. "
            f"The valid names are listed above; do not request the sheet again."
        )
        raise ModelRetry(msg)


def _unmatched_retry(
    search_name: str, info: ParameterInfo, options: list[VocabOption], terms: list[str]
) -> tuple[str, str] | None:
    """The first proposed term that is no entry, and the retry it earns."""
    unmatched = [term for term in terms if match_exact_option(options, term) is None]
    if not unmatched:
        return None
    shared = accession_matches(options, unmatched[0])
    if len(shared) > 1:
        return unmatched[0], (
            f"{info.name} on {search_name}: {len(shared)} entries share the "
            f"accession {unmatched[0]!r}; copy the full value of the one you mean: "
            f"{shared[:MAX_NEAREST_ENTRIES]}."
        )
    return unmatched[0], (
        f"{info.name} on {search_name} has no entry that states {unmatched}. "
        f"Read its entries with get_parameter_options and pass one of them exactly."
    )


def refuse_unmatched_value(
    search_name: str, info: ParameterInfo, options: list[VocabOption], terms: list[str]
) -> None:
    """A proposed vocabulary value is one of the entries, not a substring."""
    retry = _unmatched_retry(search_name, info, options, terms)
    if retry is not None:
        raise ModelRetry(retry[1])


def _with_terms(held: ParamValue, terms: list[str]) -> ParamValue:
    match held:
        case MultiPickValue():
            return MultiPickValue(values=terms)
        case _:
            return SinglePickValue(value=terms[0])


async def bound_vocabulary_values(
    site_id: str,
    definition: WDKSearch,
    call: CriterionCall,
    infos: list[ParameterInfo],
    derived: frozenset[str],
    state: AgentToolState,
) -> CriterionCall:
    """Binds every proposal the sheet's own vocabulary can answer, and refuses one
    no entry states.

    A proposal that is no entry is bound to the entry the catalog's pick settles.

    A dependent parameter is skipped here: the sheet showed its vocabulary under
    the search defaults, and ``reconcile_dependents`` checks it against the one
    the bound parents produce. A filter parameter takes a facet expression, not
    a vocabulary entry. A ``derived`` parameter is a species list the
    resolver reads against the tree, which names no single entry. A refusal that
    sends the request to the portal is recorded on the pass. A user-dataset
    parameter is checked against the researcher's own uploads instead.
    """
    owned = await _refuse_an_upload_the_researcher_lacks(site_id, definition, call)
    for info in infos:
        options = info.vocabulary()
        skip = (
            info.name in derived
            or info.name == owned
            or info.stated_parents
            or info.param_kind == "filter"
            or not options
        )
        terms = call.terms(info.name)
        if skip or not terms:
            continue
        bound = await bound_proposal(site_id, call.search_name, info, terms)
        call = call.with_values({info.name: _with_terms(call.values[info.name], bound)})
        retry = _unmatched_retry(call.search_name, info, options, bound)
        if retry is not None:
            value, msg = retry
            others = await _other_sites_holding(site_id, definition, info.name, value)
            if others:
                state.portal_route = portal_route_sentence(site_id)
                msg += (
                    f" {reach_sentence(definition, info.name, site_id, value)} "
                    f"{value} is on {joined(others)}. A conversation stays on its "
                    f"site: bind nothing for this criterion, ask no question about "
                    f"it, and write this in the summary word for word, link "
                    f"included: {state.portal_route}"
                )
            raise ModelRetry(msg)
    return call


async def _refuse_an_upload_the_researcher_lacks(
    site_id: str, definition: WDKSearch, call: CriterionCall
) -> str | None:
    """The dataset parameter of a user-dataset search, once its value is an upload
    the researcher owns; None for every other search.

    Its vocabulary is per account, so the cached sheet cannot check it.
    """
    parameter = dataset_parameter(definition)
    if parameter is None:
        return None
    offers = await user_dataset_offers(site_id, call.search_name)
    if not offers:
        types = ", ".join(sorted(user_dataset_types(definition)))
        msg = (
            f"{call.search_name} reads the researcher's own {types} uploads, and "
            f"this account has none installed on {site_id}, so it cannot run. Bind "
            f"nothing for this criterion, and say that the researcher uploads one "
            f"in My Data Sets on the site; nothing was recorded."
        )
        raise ModelRetry(msg)
    match call.values.get(parameter.name):
        case SinglePickValue(value=value) if value in {o.value for o in offers}:
            return parameter.name
        case _:
            uploads = ", ".join(
                f"{o.upload_name!r} ({o.value})" for o in offers[:LISTING_PAGE]
            )
            rest = len(offers) - LISTING_PAGE
            more = f" and {rest} more that list_gene_sets reads" if rest > 0 else ""
            msg = (
                f"{parameter.name} on {call.search_name} picks one of the "
                f"researcher's own uploads: {uploads}{more}. Pass the value of the upload "
                f"the request refers to; nothing was recorded."
            )
            raise ModelRetry(msg)


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


def species_lists(infos: list[ParameterInfo]) -> frozenset[str]:
    return PHYLETIC_LIST_PARAMS if is_phyletic_sheet(infos) else frozenset()


def _said(value: ParamValue) -> str | list[str]:
    match value:
        case StringValue(value=text):
            return text
        case _:
            return pick_terms(value)


def radio_overrides(
    definition: WDKSearch, call: CriterionCall, infos: list[ParameterInfo]
) -> dict[str, str]:
    """The off value for each free-text half of a pair the search ORs.

    The pairs are declared in the search properties, which the sheet drops. A
    free-text half that states the criterion is a retry.
    """
    said = {name: _said(value) for name, value in call.values.items()}
    overrides, issue = check_radio_pairs(
        radio_pairs(definition.properties), infos, said
    )
    if issue is not None:
        raise ModelRetry(_radio_retry(call, issue, infos))
    return overrides


def _published_default(infos: list[ParameterInfo], name: str) -> str | None:
    """The default value the search publishes for a param, or ``None`` for none.

    An empty list and a blank string are refused by the search that publishes
    them, so neither states a value the query would use.
    """
    published = next((i.default_value for i in infos if i.name == name), None)
    if published is None or published.strip() in ("", "[]"):
        return None
    return published


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
        f"{issue.free_value!r}: {issue.nearest}; for a wildcard use "
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
) -> ResolvedParams:
    """The binding the catalog resolves from every stated value and the off value
    of each radio half."""
    stated = {name: v for name, v in call.params.items() if v is not None}
    try:
        return await resolve_params_with_intent(
            fetch_at=fetch_at,
            filter_reads=_filter_reads(search),
            intent=ParamIntent(text=call.text),
            search_name=call.search_name,
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
