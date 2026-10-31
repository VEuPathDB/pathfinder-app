"""A typeahead pick binds only an entry a lookup of its parameter matched, and
no entry the site labels obsolete unless the request says obsolete."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState, LookupRecord
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._qualifier_words import proposal_values
from pathfinder.domain.strategy.operational_spec import BoundValue
from pathfinder.domain.strategy.value_binding import pick_terms
from pathfinder.domain.strategy.value_label import label_term
from pathfinder.domain.strategy.words import words_of

# WDK draws a vocabulary it means to be searched as a type-ahead box.
_TYPEAHEAD = "typeAhead"
# The vocabulary kinds a pick binds entries of.
_PICKS = frozenset({"multi-pick-vocabulary", "single-pick-vocabulary"})
# The first word an ontology writes in the label of a term it retired.
_OBSOLETE = "obsolete"
# A refusal lists at most this many of the entries the lookups matched.
_LISTED = 20


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
        for term in proposal_values(call.params.get(name))
        if term not in kept and not _written_out(term, state.request_messages)
    ]


def _where(call: CriterionCall, param: WDKParameter) -> str:
    return f"{param.name} ({param.display_name}) on {call.search_name}"


def refuse_a_pick_no_lookup_read(
    state: AgentToolState,
    definition: WDKSearch,
    call: CriterionCall,
    infos: Sequence[ParameterInfo],
) -> None:
    """Refuse a new typeahead multi-pick entry no lookup of its parameter matched
    this pass, then a new pick the lookup did not mean. An entry the criterion
    holds or the request writes out is no new pick."""
    held = _held(state, call)
    for param in definition.parameters or []:
        if param.type != "multi-pick-vocabulary" or param.display_type != _TYPEAHEAD:
            continue
        new = _new_picks(state, call, param.name, held)
        if not new:
            continue
        where = _where(call, param)
        record = state.looked_up.get((call.search_name, param.name))
        if record is None:
            msg = (
                f"{where} holds {new}, and no lookup of it ran this pass. Read the "
                f"options for {call.text!r} first, then bind the entries a phrase "
                f"matched: {_lookup_call(call, param)}."
            )
            raise ModelRetry(msg)
        stray = [term for term in new if term not in record.matched]
        if stray:
            listed = sorted(record.matched)[:_LISTED]
            msg = (
                f"{where} holds {stray}, which no lookup of it matched. Bind only "
                f"entries a lookup of {call.text!r} returned ({len(record.matched)}: "
                f"{', '.join(listed) or 'none'}), or read the options again with "
                f"other phrasings: {_lookup_call(call, param)}."
            )
            raise ModelRetry(msg)
    _refuse_a_pick_the_lookup_did_not_mean(state, definition, call, infos, held)


def _named(value: str, labels: dict[str, str]) -> str:
    return f"{value} ({labels[value]!r})"


def _is_obsolete(value: str, labels: dict[str, str]) -> bool:
    return words_of(label_term(value, labels[value]))[:1] == [_OBSOLETE]


def _refuse_an_obsolete_pick(
    state: AgentToolState,
    where: str,
    new: list[str],
    record: LookupRecord,
    labels: dict[str, str],
) -> None:
    """Refuse a new pick the site labels obsolete when no request message says
    obsolete, and list the current entries its lookup term matched."""
    obsolete = [v for v in new if v in labels and _is_obsolete(v, labels)]
    if not obsolete or _written_out(_OBSOLETE, state.request_messages):
        return
    terms = list(dict.fromkeys(record.matched[v] for v in obsolete))
    current = [
        v
        for term in terms
        for v in record.matched_by(term)
        if v in labels and not _is_obsolete(v, labels)
    ]
    quoted = ", ".join(repr(term) for term in terms)
    found = (
        f"The lookup of {quoted} matched these current entries: "
        f"{', '.join(_named(v, labels) for v in current[:_LISTED])}."
        if current
        else f"The lookup of {quoted} matched no current entry."
    )
    msg = (
        f"{where} holds {obsolete}, which the site labels obsolete, and no request "
        f"message says obsolete. {found} Bind current entries, or ask the "
        "researcher which one they mean."
    )
    raise ModelRetry(msg)


def _refuse_a_pick_the_lookup_did_not_mean(
    state: AgentToolState,
    definition: WDKSearch,
    call: CriterionCall,
    infos: Sequence[ParameterInfo],
    held: dict[str, BoundValue],
) -> None:
    """Refuse a new typeahead pick the site labels obsolete."""
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
        where = _where(call, param)
        _refuse_an_obsolete_pick(state, where, new, record, labels)
