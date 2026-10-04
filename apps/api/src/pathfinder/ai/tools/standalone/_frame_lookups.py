"""A typeahead pick binds only an entry a lookup of its parameter matched, only
the entry the lookup was asked for, and only an entry the request's words name."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState, LookupRecord
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._qualifier_words import proposal_values, stem
from pathfinder.domain.strategy.constraints import content_words
from pathfinder.domain.strategy.operational_spec import BoundValue
from pathfinder.domain.strategy.value_label import label_term
from pathfinder.domain.strategy.words import words_of
from pathfinder.services.strategies.value_labels import pick_terms

# WDK draws a vocabulary it means to be searched as a type-ahead box.
_TYPEAHEAD = "typeAhead"
# The vocabulary kinds a pick binds entries of.
_PICKS = frozenset({"multi-pick-vocabulary", "single-pick-vocabulary"})
# The first word an ontology writes in the label of a term it retired.
_OBSOLETE = "obsolete"
# A refusal lists at most this many of the entries the lookups matched.
_LISTED = 20
# A word that more than one label in fifty holds, and more than two labels,
# names no family of its own.
_COMMON_WORD_SHARE = 0.02
_FEWEST_LABELS_FOR_A_COMMON_WORD = 2
# A vocabulary with fewer labels than this tells no word common.
_FEWEST_LABELS_TO_TELL_COMMON = 10


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


def _refuse_a_pick_beside_the_exact_term(
    state: AgentToolState,
    where: str,
    new: list[str],
    record: LookupRecord,
    labels: dict[str, str],
) -> None:
    """Refuse a new pick a lookup term matched when another entry's label is
    that term, unless the request writes the picked label out."""
    for term in dict.fromkeys(record.matched.values()):
        wanted = content_words(term)
        exact = [
            v
            for v in record.matched
            if v in labels and content_words(label_term(v, labels[v])) == wanted
        ]
        if not exact:
            continue
        by_term = record.matched_by(term)
        others = [
            v
            for v in new
            if v in by_term
            and v in labels
            and v not in exact
            and not _written_out(label_term(v, labels[v]), state.request_messages)
        ]
        if others:
            msg = (
                f"{where} holds {others}, which the lookup of {term!r} matched "
                f"beside {_named(exact[0], labels)}, the entry whose label is that "
                "term. Bind the exact entry alone; the others state a narrower or "
                "related question, unless the request names them."
            )
            raise ModelRetry(msg)


def _stems(text: str) -> frozenset[str]:
    return frozenset(stem(word) for word in content_words(text))


def _label_words(labels: dict[str, str]) -> dict[str, frozenset[str]]:
    return {v: _stems(label_term(v, display)) for v, display in labels.items()}


def _common_words(words: dict[str, frozenset[str]]) -> frozenset[str]:
    """The words more than the common share of the labels hold. A small
    vocabulary has none."""
    if len(words) < _FEWEST_LABELS_TO_TELL_COMMON:
        return frozenset()
    counts = Counter(word for held in words.values() for word in held)
    most = max(_COMMON_WORD_SHARE * len(words), _FEWEST_LABELS_FOR_A_COMMON_WORD)
    return frozenset(word for word, count in counts.items() if count > most)


def _other_parent_values(
    definition: WDKSearch,
    param: WDKParameter,
    call: CriterionCall,
    by_name: dict[str, ParameterInfo],
) -> str:
    """The values of the parameter this one depends on that the call does not
    send, as the vocabularies the same entries can be read under."""
    parents = [
        p
        for p in definition.parameters or []
        if param.name in p.dependent_params and p.name in by_name
    ]
    if not parents:
        return ""
    parent = parents[0]
    sent = set(proposal_values(call.params.get(parent.name)))
    others = [
        o.display for o in by_name[parent.name].vocabulary() if o.value not in sent
    ][:_LISTED]
    if not others:
        return ""
    return f" under another {parent.display_name} ({', '.join(others)})"


def _refuse_a_pick_off_the_request_words(
    state: AgentToolState,
    where: str,
    call: CriterionCall,
    new: list[str],
    *,
    record: LookupRecord,
    labels: dict[str, str],
    elsewhere: str,
) -> None:
    """Refuse a new pick whose label shares no uncommon content word with the
    request messages, unless the request writes the picked label out. A request
    whose looked-up concept words are all common counts them as uncommon. The
    refusal names the matched entries whose labels do carry those words."""
    words = _label_words(labels)
    asked = frozenset().union(*map(_stems, state.request_messages))
    common = _common_words(words)
    concept = asked & frozenset().union(*map(_stems, set(record.matched.values())))
    uncommon = asked - common
    if concept and concept <= common:
        uncommon |= concept
    strays = [
        v
        for v in new
        if v in words
        and not words[v] & uncommon
        and not _written_out(label_term(v, labels[v]), state.request_messages)
    ]
    if not strays:
        return
    fitting = [v for v in record.matched if v in words and words[v] & uncommon]
    shown = ", ".join(repr(labels[v]) for v in strays)
    share = "whose labels share" if len(strays) > 1 else "whose label shares"
    found = (
        "The lookup matched entries whose labels carry the request's words: "
        f"{', '.join(_named(v, labels) for v in fitting[:_LISTED])}."
        if fitting
        else f"No entry this lookup matched carries the request's words; read the "
        f"options{elsewhere}."
    )
    msg = (
        f"{where} holds {strays} ({shown}), {share} no uncommon word with the "
        f"request's {call.text!r}. {found} Bind an entry whose label carries the "
        "concept's words, or ask the researcher which family they mean."
    )
    raise ModelRetry(msg)


def _refuse_a_pick_the_lookup_did_not_mean(
    state: AgentToolState,
    definition: WDKSearch,
    call: CriterionCall,
    infos: Sequence[ParameterInfo],
    held: dict[str, BoundValue],
) -> None:
    """Refuse a new typeahead pick the site labels obsolete, a pick beside the
    entry whose label is the looked-up term, and a pick off the request's words."""
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
        _refuse_a_pick_beside_the_exact_term(state, where, new, record, labels)
        _refuse_a_pick_off_the_request_words(
            state,
            where,
            call,
            new,
            record=record,
            labels=labels,
            elsewhere=_other_parent_values(definition, param, call, by_name),
        )
