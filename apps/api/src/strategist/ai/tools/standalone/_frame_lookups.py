"""A typeahead pick binds only an entry a lookup of its parameter matched, and
no entry the site labels obsolete unless the request says obsolete."""

from __future__ import annotations

import re
from collections.abc import Sequence

from veupathdb.domain.parameters import (
    flatten_vocab,
    name_past_accession,
    same_named_groups,
    vocab_paths,
)
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.agents.lookup_record import LookupRecord
from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._catalog_elsewhere import joined
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.domain.refusal import Check, Problem, Problems, RefusalKey
from strategist.domain.strategy.operational_spec import BoundValue
from strategist.domain.strategy.value_binding import pick_terms
from strategist.services.strategies.obsolete_terms import OBSOLETE, says_obsolete

# WDK draws a vocabulary it means to be searched as a type-ahead box.
_TYPEAHEAD = "typeAhead"
# The vocabulary kinds a pick binds entries of.
_PICKS = frozenset({"multi-pick-vocabulary", "single-pick-vocabulary"})
# A refusal lists at most this many of the entries the lookups matched.
_LISTED = 20
_PAIR = 2


def _written_out(term: str, messages: Sequence[str]) -> bool:
    """Whether a message writes the entry as a whole token."""
    token = re.compile(rf"(?<![\w]){re.escape(term)}(?![\w])", re.IGNORECASE)
    return any(token.search(text) for text in messages)


def _lookup_call(call: CriterionCall, param: WDKParameter) -> str:
    return (
        f"get_parameter_options(search_name='{call.search_name}', "
        f"parameter_id='{param.name}', query=[every phrasing of the concept, its "
        f"synonyms and the family names that say it another way])"
    )


def _held(state: AgentToolState, call: CriterionCall) -> dict[str, BoundValue]:
    return next(
        (
            c.resolved_params
            for c in state.operational_spec_draft.criteria
            if (c.id, c.search_name) == (call.criterion_id, call.search_name)
        ),
        {},
    )


def _new_picks(
    state: AgentToolState, call: CriterionCall, name: str, held: dict[str, BoundValue]
) -> list[str]:
    """The entries the call adds that the criterion does not hold and the
    request does not write out."""
    kept = pick_terms(held[name].value) if name in held else []
    return [
        term
        for term in call.terms(name)
        if term not in kept and not _written_out(term, state.request_messages)
    ]


def _where(call: CriterionCall, param: WDKParameter) -> str:
    return f"{param.name} ({param.display_name}) on {call.search_name}"


def _lookup_problem(
    state: AgentToolState, call: CriterionCall, param: WDKParameter, new: list[str]
) -> str | None:
    where = _where(call, param)
    record = state.looked_up.get((call.search_name, param.name))
    if record is None:
        return (
            f"{where} holds {new}, and no lookup of it ran this pass. Read the "
            f"options for {call.text!r} first, then bind the entries a phrase "
            f"matched: {_lookup_call(call, param)}."
        )
    stray = [term for term in new if term not in record.matched]
    if not stray:
        return None
    listed = sorted(record.matched)[:_LISTED]
    return (
        f"{where} holds {stray}, which no lookup of it matched. Bind only "
        f"entries a lookup of {call.text!r} returned ({len(record.matched)}: "
        f"{', '.join(listed) or 'none'}), or read the options again with "
        f"other phrasings: {_lookup_call(call, param)}."
    )


def pick_problems(
    state: AgentToolState,
    definition: WDKSearch,
    call: CriterionCall,
    infos: Sequence[ParameterInfo],
) -> Problems:
    """A new typeahead multi-pick entry no lookup of its parameter matched this
    pass, for every parameter, then every new pick the lookup did not mean. An
    entry the criterion holds or the request writes out is no new pick."""
    held = _held(state, call)
    found: list[Problem] = []
    for param in definition.parameters or []:
        if param.type != "multi-pick-vocabulary" or param.display_type != _TYPEAHEAD:
            continue
        new = _new_picks(state, call, param.name, held)
        said = _lookup_problem(state, call, param, new) if new else None
        if said is not None:
            key = RefusalKey(check=Check.LOOKUP, parameter=param.name)
            found.append(Problem(key=key, sentence=said))
    return (
        Problems(found=tuple(found))
        .plus(_picks_the_lookup_did_not_mean(state, definition, call, infos, held))
        .plus(_same_named_subsets(state, definition, call))
    )


def _same_named(
    state: AgentToolState, call: CriterionCall, param: WDKParameter
) -> dict[str, tuple[str, ...]]:
    """The groups of entries that share a name, from the lookup of the
    parameter when one ran, else from its whole vocabulary."""
    record = state.looked_up.get((call.search_name, param.name))
    if record is not None:
        return record.same_named
    options = flatten_vocab(param.vocabulary)
    labels = {option.value: name_past_accession(option) for option in options}
    return {
        labels[group[0]]: tuple(group)
        for group in same_named_groups(options, vocab_paths(param.vocabulary))
    }


def _same_named_subsets(
    state: AgentToolState, definition: WDKSearch, call: CriterionCall
) -> Problems:
    found: list[Problem] = []
    for param in definition.parameters or []:
        if param.type != "multi-pick-vocabulary":
            continue
        picks = call.terms(param.name)
        for name, group in _same_named(state, call, param).items():
            held = [v for v in group if v in picks]
            named = any(_written_out(v, state.request_messages) for v in held)
            if not held or len(held) == len(group) or named:
                continue
            found.append(
                Problem(
                    key=RefusalKey(check=Check.SAME_NAMED_SUBSET, parameter=param.name),
                    sentence=(
                        f"{joined(group)} share the name {name!r}. Bind "
                        f"{'both' if len(group) == _PAIR else 'all of them'}, or "
                        "ask which one on the card."
                    ),
                )
            )
    return Problems(found=tuple(found))


def _named(value: str, labels: dict[str, str]) -> str:
    return f"{value} ({labels[value]!r})"


def _an_obsolete_pick(
    state: AgentToolState,
    where: str,
    new: list[str],
    record: LookupRecord,
    labels: dict[str, str],
) -> str | None:
    """A new pick the site labels obsolete when no request message says
    obsolete, with the current entries its lookup term matched."""
    obsolete = [v for v in new if v in labels and says_obsolete(v, labels[v])]
    if not obsolete or _written_out(OBSOLETE, state.request_messages):
        return None
    terms = list(dict.fromkeys(record.matched[v] for v in obsolete))
    current = [
        v
        for term in terms
        for v in record.matched_by(term)
        if v in labels and not says_obsolete(v, labels[v])
    ]
    quoted = ", ".join(repr(term) for term in terms)
    found = (
        f"The lookup of {quoted} matched these current entries: "
        f"{', '.join(_named(v, labels) for v in current[:_LISTED])}."
        if current
        else f"The lookup of {quoted} matched no current entry."
    )
    return (
        f"{where} holds {obsolete}, which the site labels obsolete, and no request "
        f"message says obsolete. {found} Bind current entries, or ask the "
        "researcher which one they mean."
    )


def _picks_the_lookup_did_not_mean(
    state: AgentToolState,
    definition: WDKSearch,
    call: CriterionCall,
    infos: Sequence[ParameterInfo],
    held: dict[str, BoundValue],
) -> Problems:
    """Every new typeahead pick the site labels obsolete."""
    found: list[Problem] = []
    by_name = {info.name: info for info in infos}
    for param in definition.parameters or []:
        record = state.looked_up.get((call.search_name, param.name))
        if (
            param.type not in _PICKS
            or param.display_type != _TYPEAHEAD
            or record is None
            or param.name not in by_name
        ):
            continue
        new = _new_picks(state, call, param.name, held)
        if not new:
            continue
        labels = {o.value: o.display for o in by_name[param.name].vocabulary()}
        said = _an_obsolete_pick(state, _where(call, param), new, record, labels)
        if said is not None:
            key = RefusalKey(check=Check.OBSOLETE_PICK, parameter=param.name)
            found.append(Problem(key=key, sentence=said))
    return Problems(found=tuple(found))
