"""The proposed values of one set_criterion call, and the retries they earn."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    ValidationError,
    field_validator,
)
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import (
    MAX_NEAREST_ENTRIES,
    VocabOption,
    accession_matches,
    match_exact_option,
    nearest_entries,
)
from veupathdb.wdk import WDKSearch, get_site, get_site_router
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import (
    RADIO_OFF,
    OverrideMap,
    ParameterInfo,
    ParamFetcher,
    ParamIntent,
    PhyleticNoSelection,
    PhyleticUnresolvedProposal,
    RadioPairIssue,
    ResolvedParams,
    UnknownParameterError,
    UnreadableValueError,
    check_radio_pairs,
    derive_phyletic_overrides,
    is_phyletic_sheet,
    radio_pairs,
    resolve_params_with_intent,
)
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._catalog_elsewhere import (
    joined,
    reach_sentence,
    tree_tops,
)
from pathfinder.ai.tools.standalone._qualifier_words import proposal_values
from pathfinder.platform.config import BASE_PATH
from pathfinder.services.strategies.parameter_rules import site_fixed
from pathfinder.services.strategies.user_dataset_searches import (
    dataset_parameter,
    user_dataset_offers,
    user_dataset_types,
)


class _Proposal(BaseModel):
    """One proposed value as the model may type it: a string, a number, a list,
    a JSON-encoded list, a filter object, or null."""

    model_config = ConfigDict(coerce_numbers_to_str=True)
    value: str | list[str] | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _json_word(cls, v: object) -> object:
        """A boolean is its JSON word, so a yes/no vocabulary answers it."""
        if isinstance(v, bool):
            return "true" if v else "false"
        return v

    @field_validator("value", mode="before")
    @classmethod
    def _json_text(cls, v: object) -> object:
        """A filter object reaches the tool server as its JSON text."""
        return json.dumps(v) if isinstance(v, dict) else v

    @field_validator("value", mode="before")
    @classmethod
    def _json_list(cls, v: object) -> object:
        if not isinstance(v, str) or not v.startswith("["):
            return v
        try:
            parsed = json.loads(v)
        except json.JSONDecodeError:
            # Bracketed text that is not a JSON list is a literal value.
            return v
        return [str(x) for x in parsed] if isinstance(parsed, list) else v


def _proposed(name: str, value: object) -> str | list[str] | None:
    try:
        return _Proposal.model_validate({"value": value}).value
    except ValidationError as exc:
        message = f"{name}: {exc.errors()[0]['msg']}"
        raise ValueError(message) from exc


def coerce_proposals(raw: object) -> object:
    """Reads each proposed value in the form the model wrote it. A non-mapping
    passes through so Pydantic reports the type error."""
    if not isinstance(raw, dict):
        return raw
    return {str(name): _proposed(str(name), value) for name, value in raw.items()}


ParamProposals = Annotated[
    dict[str, str | list[str] | None], BeforeValidator(coerce_proposals)
]


@dataclass(frozen=True)
class CriterionCall:
    """The one call's identity, carried through the checks it drives."""

    criterion_id: str
    search_name: str
    text: str
    params: ParamProposals


def _bindable(infos: list[ParameterInfo]) -> list[str]:
    return sorted(i.name for i in infos if not site_fixed(i))


def left_to_the_site(
    call: CriterionCall, infos: list[ParameterInfo]
) -> tuple[CriterionCall, list[str]]:
    """The call without the parameters only the site sets that it proposes at
    the site's value, and one correction for each.

    A proposal of another value is refused with the value the site holds.
    """
    fixed = {i.name: i for i in infos if site_fixed(i) and i.name in call.params}
    corrections: list[str] = []
    for name, info in fixed.items():
        held = info.default_value or ""
        if call.params[name] not in (None, _proposed(name, held)):
            msg = (
                f"{name} on {call.search_name} is set by the site to {held!r} and "
                f"takes no other value; leave it out of params. The names params "
                f"takes: {_bindable(infos)}."
            )
            raise ModelRetry(msg)
        corrections.append(
            f"{name} is set by the site to {held!r}, so the proposal was left out"
        )
    params = {n: v for n, v in call.params.items() if n not in fixed}
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
    """Every visible required parameter needs a value or a null."""
    required = {i.name for i in infos if i.is_visible and i.required}
    undecided = sorted(required - set(call.params))
    if undecided:
        msg = (
            f"Decide every visible required parameter of {call.search_name}: missing "
            f"{undecided}. Pass a value from the sheet, or null for the default. "
            f"The valid names are listed above; do not request the sheet again."
        )
        raise ModelRetry(msg)


def _unmatched_retry(
    call: CriterionCall, info: ParameterInfo, options: list[VocabOption]
) -> tuple[str, str] | None:
    """The first proposed value that is no entry, and the retry it earns."""
    unmatched = [
        value
        for value in proposal_values(call.params.get(info.name))
        if match_exact_option(options, value) is None
    ]
    if not unmatched:
        return None
    shared = accession_matches(options, unmatched[0])
    if len(shared) > 1:
        return unmatched[0], (
            f"{info.name} on {call.search_name}: {len(shared)} entries share the "
            f"accession {unmatched[0]!r}; copy the full value of the one you mean: "
            f"{shared[:MAX_NEAREST_ENTRIES]}."
        )
    return unmatched[0], (
        f"{info.name} on {call.search_name} has no entry matching {unmatched}. Copy "
        f"a value or a label from the vocabulary exactly; a substring names a "
        f"different entry. Nearest entries: "
        f"{nearest_entries(options, unmatched[0], MAX_NEAREST_ENTRIES)}."
    )


def refuse_unmatched_value(
    call: CriterionCall, info: ParameterInfo, options: list[VocabOption]
) -> None:
    """A proposed vocabulary value is one of the entries, not a substring."""
    retry = _unmatched_retry(call, info, options)
    if retry is not None:
        raise ModelRetry(retry[1])


async def refuse_unmatched_values(
    site_id: str,
    definition: WDKSearch,
    call: CriterionCall,
    infos: list[ParameterInfo],
    derived: frozenset[str],
    state: AgentToolState,
) -> None:
    """Checks every proposal the sheet's own vocabulary can answer.

    A dependent parameter is skipped here: the sheet showed its vocabulary under
    the search defaults, and ``reconcile_dependents`` checks it against the one
    the bound parents produce. A filter parameter takes a facet expression, not
    a vocabulary entry. A ``derived`` parameter holds a canonical value the
    derivation already resolved, which names no single entry. A refusal that
    sends the request to the portal is recorded on the pass. A user-dataset
    parameter is checked against the researcher's own uploads instead.
    """
    owned = await _refuse_an_upload_the_researcher_lacks(site_id, definition, call)
    for info in infos:
        options = info.vocabulary()
        skip = (
            info.name in derived
            or info.name == owned
            or info.vocab_depends_on
            or info.param_kind == "filter"
            or not options
        )
        retry = None if skip else _unmatched_retry(call, info, options)
        if retry is not None:
            value, msg = retry
            others = await _other_sites_holding(site_id, definition, info.name, value)
            if others:
                state.portal_route = portal_only_sentence(site_id)
                msg += (
                    f" {reach_sentence(definition, info.name, site_id, value)} "
                    f"{value} is on {joined(others)}. A conversation stays on its "
                    f"site: bind nothing for this criterion, ask no question about "
                    f"it, and write this in the summary word for word, link "
                    f"included: {state.portal_route}"
                )
            raise ModelRetry(msg)


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
    match call.params.get(parameter.name):
        case str() as value if value in {offer.value for offer in offers}:
            return parameter.name
        case _:
            uploads = ", ".join(f"{o.upload_name!r} ({o.value})" for o in offers)
            msg = (
                f"{parameter.name} on {call.search_name} picks one of the "
                f"researcher's own uploads: {uploads}. Pass the value of the upload "
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


def portal_only_sentence(site_id: str) -> str:
    """What the researcher does when only the portal holds both organisms."""
    portal = next(site for site in get_site_router().list_sites() if site.is_portal)
    link = f"{BASE_PATH}/{portal.id}/conversation"
    return (
        f"This needs the {portal.name} Portal, where one strategy holds both "
        f"organisms. [Open a new conversation there]({link}); "
        f"this conversation stays on {get_site(site_id).name}."
    )


def phyletic_overrides(
    definition: WDKSearch, call: CriterionCall, infos: list[ParameterInfo]
) -> dict[str, str] | None:
    """The three phyletic values the two proposed species lists state.

    The clade tree lives on the structural parameters, which the sheet drops. An
    unresolved term and an empty selection are both retries.
    """
    if not is_phyletic_sheet(infos):
        return None
    match derive_phyletic_overrides(definition.parameters or [], call.params):
        case None:
            return None
        case PhyleticUnresolvedProposal() as unresolved:
            raise ModelRetry(_phyletic_retry(call, unresolved))
        case PhyleticNoSelection():
            msg = (
                f"{call.search_name}: a phylogenetic profile needs at least one "
                f"species or clade in included_species or excluded_species. An "
                f"empty selection states no criterion and returns every gene of "
                f"the chosen organisms. Name what must have an ortholog and what "
                f"must not, or drop_criterion if the request states neither."
            )
            raise ModelRetry(msg)
        case derived:
            return derived.model_dump()


def _phyletic_retry(call: CriterionCall, derived: PhyleticUnresolvedProposal) -> str:
    """Names each list's unresolved terms and the entries nearest to them."""
    unresolved = derived.unresolved
    reasons: list[str] = []
    if unresolved.included_unknown:
        reasons.append(f"included_species names no entry {unresolved.included_unknown}")
    if unresolved.excluded_unknown:
        reasons.append(f"excluded_species names no entry {unresolved.excluded_unknown}")
    if unresolved.conflicts:
        reasons.append(f"{unresolved.conflicts} is in both lists")
    nearest = f" Nearest entries: {derived.nearest}." if derived.nearest else ""
    return (
        f"{call.search_name}: {'; '.join(reasons)}. Copy a code or a label from the "
        f"included_species / excluded_species vocabulary on the sheet, and name each "
        f"species or clade in ONE of the two lists. A genus or common name is not a "
        f"node - name a species or a clade code from the sheet, or call "
        f"lookup_phyletic_codes(query).{nearest}"
    )


def radio_overrides(
    definition: WDKSearch, call: CriterionCall, infos: list[ParameterInfo]
) -> dict[str, str]:
    """The off value for each free-text half of a pair the search ORs.

    The pairs are declared in the search properties, which the sheet drops. A
    free-text half that states the criterion is a retry.
    """
    overrides, issue = check_radio_pairs(
        radio_pairs(definition.properties), infos, call.params
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
    """Names the half that carries the criterion and the entries nearest to it."""
    pair = issue.pair
    published = _published_default(infos, pair.vocabulary)
    holds = (
        f"{pair.vocabulary} default {published} would still contribute"
        if published is not None
        else f"{pair.vocabulary} cannot be left empty"
    )
    return (
        f"{pair.free_text} and {pair.vocabulary} on {call.search_name} are ORed "
        f"halves of one criterion; the vocabulary half carries it and cannot be "
        f"switched off ({holds}). Put the criterion in {pair.vocabulary} (nearest "
        f"entries for {issue.free_value!r}: {issue.nearest}; for a wildcard use "
        f"get_parameter_options({call.search_name}, '{pair.vocabulary}', "
        f"query=[<every phrasing of the concept>]) and list the entries a phrase "
        f"matched) and pass {RADIO_OFF} "
        f"for {pair.free_text}."
    )


async def resolve_proposals(
    fetch_at: ParamFetcher, text: str, overrides: OverrideMap
) -> ResolvedParams:
    try:
        return await resolve_params_with_intent(
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
    except UnreadableValueError as exc:
        raise ModelRetry(str(exc)) from exc
