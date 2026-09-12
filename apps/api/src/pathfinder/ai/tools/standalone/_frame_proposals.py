"""The proposed values of one set_criterion call, and the retries they earn."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, BeforeValidator, ConfigDict, field_validator
from pydantic import ValidationError as PydanticValidationError
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import (
    MAX_NEAREST_ENTRIES,
    VocabOption,
    accession_matches,
    match_exact_option,
    nearest_entries,
)
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    RADIO_OFF,
    ParameterInfo,
    PhyleticNoSelection,
    PhyleticUnresolvedProposal,
    RadioPairIssue,
    check_radio_pairs,
    derive_phyletic_overrides,
    is_phyletic_sheet,
    radio_pairs,
)


class DeclaredAssumption(CamelModel):
    """A value the model chose that the criterion text does not state."""

    param_name: str
    value: str
    reason: str


class _Proposal(BaseModel):
    """One proposed value as the model may type it: a string, a number, a list,
    a JSON-encoded list, or null."""

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
    except PydanticValidationError as exc:
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
class _CriterionCall:
    """The one call's identity, carried through the checks it drives."""

    criterion_id: str
    search_name: str
    text: str
    params: ParamProposals


def _values_of(proposal: str | list[str] | None) -> list[str]:
    if proposal is None:
        return []
    return proposal if isinstance(proposal, list) else [proposal]


def _refuse_unknown_names(call: _CriterionCall, infos: list[ParameterInfo]) -> None:
    """A proposal names a visible parameter of the search.

    A null proposal is dropped before the DAG's own name check, so a misspelt
    name paired with a null would otherwise set nothing and say nothing.
    """
    visible = sorted(i.name for i in infos if i.is_visible)
    unknown = sorted(set(call.params) - set(visible))
    if unknown:
        nearest = nearest_entries(
            [VocabOption(value=name, display="") for name in visible],
            unknown[0],
            MAX_NEAREST_ENTRIES,
        )
        msg = (
            f"No such parameter(s) on {call.search_name}: {unknown}. Nearest: "
            f"{nearest}. The valid names are listed above; "
            f"do not request the sheet again. Valid names: {visible}."
        )
        raise ModelRetry(msg)


def _refuse_undecided(call: _CriterionCall, infos: list[ParameterInfo]) -> None:
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


def _refuse_unmatched_value(
    call: _CriterionCall, info: ParameterInfo, options: list[VocabOption]
) -> None:
    """A proposed vocabulary value is one of the entries, not a substring."""
    unmatched = [
        value
        for value in _values_of(call.params.get(info.name))
        if match_exact_option(options, value) is None
    ]
    if not unmatched:
        return
    shared = accession_matches(options, unmatched[0])
    if len(shared) > 1:
        msg = (
            f"{info.name} on {call.search_name}: {len(shared)} entries share the "
            f"accession {unmatched[0]!r}; copy the full value of the one you mean: "
            f"{shared[:MAX_NEAREST_ENTRIES]}."
        )
        raise ModelRetry(msg)
    msg = (
        f"{info.name} on {call.search_name} has no entry matching {unmatched}. Copy "
        f"a value or a label from the vocabulary exactly; a substring names a "
        f"different entry. Nearest entries: "
        f"{nearest_entries(options, unmatched[0], MAX_NEAREST_ENTRIES)}."
    )
    raise ModelRetry(msg)


def _refuse_unmatched_values(
    call: _CriterionCall, infos: list[ParameterInfo], derived: frozenset[str]
) -> None:
    """Checks every proposal the sheet's own vocabulary can answer.

    A dependent parameter is skipped here: the sheet showed its vocabulary under
    the search defaults, and ``_reconcile_dependents`` checks it against the one
    the bound parents produce. A filter parameter takes a facet expression, not
    a vocabulary entry. A ``derived`` parameter holds a canonical value the
    derivation already resolved, which names no single entry.
    """
    for info in infos:
        options = info.vocabulary()
        skip = (
            info.name in derived
            or info.vocab_depends_on
            or info.param_kind == "filter"
            or not options
        )
        if info.name in call.params and not skip:
            _refuse_unmatched_value(call, info, options)


def _phyletic_overrides(
    definition: WDKSearch, call: _CriterionCall, infos: list[ParameterInfo]
) -> dict[str, str] | None:
    """The three phyletic values the two proposed species lists state.

    The clade tree lives on the structural parameters, which the sheet drops. An
    unresolved term and an empty selection are both retries.
    """
    if not is_phyletic_sheet(infos):
        return None
    derived = derive_phyletic_overrides(definition.parameters or [], call.params)
    if derived is None:
        return None
    if isinstance(derived, PhyleticUnresolvedProposal):
        raise ModelRetry(_phyletic_retry(call, derived))
    if isinstance(derived, PhyleticNoSelection):
        msg = (
            f"{call.search_name}: a phylogenetic profile needs at least one "
            f"species or clade in included_species or excluded_species. An empty "
            f"selection states no criterion and returns every gene of the chosen "
            f"organisms. Name what must have an ortholog and what must not, or "
            f"drop_criterion if the request states neither."
        )
        raise ModelRetry(msg)
    return derived.model_dump()


def _phyletic_retry(call: _CriterionCall, derived: PhyleticUnresolvedProposal) -> str:
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


def _radio_overrides(
    definition: WDKSearch, call: _CriterionCall, infos: list[ParameterInfo]
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
    call: _CriterionCall, issue: RadioPairIssue, infos: list[ParameterInfo]
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
        f"query='...') and list every entry it should cover) and pass {RADIO_OFF} "
        f"for {pair.free_text}."
    )
