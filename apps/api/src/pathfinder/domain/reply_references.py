"""The references a reply writes in place of a fact, the text each renders from
the turn's facts, and the faults of a reply that writes a fact itself."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from pathfinder.domain.comparison_facts import ComparedVariant
from pathfinder.domain.count_words import counted
from pathfinder.domain.dispute_references import unnamed_disputes
from pathfinder.domain.list_items import without_item_numbers
from pathfinder.domain.reference_grammar import (
    A_REFERENCE,
    COUNTED_REFERENCES,
    malformed_brackets,
    reference_and_its_noun,
    reference_kind,
)
from pathfinder.domain.reference_placement import misplacements
from pathfinder.domain.reply_notes import ReplyNotes, misused_references
from pathfinder.domain.reply_suggestions import (
    A_TOKEN,
    EDGE_MARKS,
    an_identifier,
    last_change,
    link_references,
    number_references,
    product_of,
    record_references,
    value_word_references,
)
from pathfinder.domain.statistic_facts import (
    statistic_group_references,
    statistic_keyed_references,
    statistic_value,
    statistic_word_references,
)
from pathfinder.domain.strategy.operational_spec import ValueSource
from pathfinder.domain.tally_facts import tally_count
from pathfinder.domain.turn_facts import ParameterFact, TurnFacts

_A_LINK = re.compile(
    r"(?:https?:[\\/]*|www\.|(?<![:\w/\\])[\\/]{2}(?=[\w-]+\.))[^\s<>()\[\]\"'`]+",
    re.IGNORECASE,
)
_THE_DIGITS = re.compile(r"\d[\d,]*(?:\.\d+)?")
_NUM = r"\d[\d,]*(?:\.\d+)?(?:[eE][+-]?\d+)?"
# A count or a value: a number, a range or ratio of numbers, with a percent or a
# unit glued to it ("37C", "5x", "2-fold"), or a log scale ("log2").
_A_NUMBER = re.compile(rf"[+-]?{_NUM}(?:[-/]{_NUM})*(?:%|-?[A-Za-z]{{1,4}})?|log\d+")
# The count a comparison reference names after its variant.
_COMPARED = ("unique", "result", "shared")
_GROUP_SHOWN = 6
_A_CITE = re.compile(r"[ \t]*\[cite:(?P<body>[^\[\]\n]+)\]")
# The link a record reference renders: the record's id, then its page.
_A_RECORD_LINK = re.compile(r"\[(?P<record_id>[^\[\]\s]+)\]\([^()\s]+\)")

_SOURCE_WORDS: dict[ValueSource, str] = {
    "stated": "you stated",
    "card": "your answer on a card",
    "default": "the site's default",
    "chosen": "chosen",
    "held": "held by the strategy",
}

type FaultKind = Literal[
    "number",
    "identifier",
    "link",
    "unheld_reference",
    "keyed_reference",
    "malformed_reference",
    "number_word",
    "noun_after_count",
    "product_text",
    "standalone_count",
    "sentence_in_place",
    "cited_number",
    "unnamed_dispute",
]


class ProseFault(CamelModel):
    """A token of a reply that states a fact outside a reference, or a reference
    that names nothing the facts hold, and the references that render it."""

    model_config = ConfigDict(frozen=True)

    token: str
    kind: FaultKind
    references: tuple[str, ...] = ()
    # The record whose product holds the token.
    record_id: str = ""


def _parameter(facts: TurnFacts, body: str) -> ParameterFact | None:
    step_id, _, name = body.partition(".")
    step = facts.step(step_id)
    if step is None:
        return None
    return next((p for p in step.parameters if p.name == name), None)


def _variant(facts: TurnFacts, label: str) -> ComparedVariant | None:
    return next(
        (
            v
            for c in reversed(facts.comparisons)
            for v in c.variants
            if v.label == label
        ),
        None,
    )


def _shared(facts: TurnFacts, pair: str) -> int | None:
    a, _, b = pair.partition(",")
    return next(
        (
            o.shared
            for c in reversed(facts.comparisons)
            for o in c.overlaps
            if {o.a, o.b} == {a, b}
        ),
        None,
    )


def _compared(facts: TurnFacts, body: str) -> int | None:
    """The count a comparison reference names: a variant's genes, its unique
    genes, its result in place, or the genes two variants share."""
    label, _, which = body.rpartition(":")
    if which not in _COMPARED:
        label, which = body, ""
    if which == "shared":
        return _shared(facts, label)
    variant = _variant(facts, label)
    if variant is None:
        return None
    match which:
        case "unique":
            return variant.unique_count
        case "result":
            return variant.result_count
        case _:
            return variant.gene_count


def _count(facts: TurnFacts, side: str) -> int | None:
    """The count one side of a difference names."""
    kind, _, body = side.partition(":")
    match kind, body:
        case "root", "":
            return facts.root_count
        case "root_before", "":
            return facts.root_count_before
        case "before", _:
            step = facts.step(body)
            return None if step is None else step.count_before
        case "compare", _:
            return _compared(facts, body)
        case "last_change", _:
            return last_change(facts, body)
        case _:
            step = facts.step(side)
            return None if step is None else step.count


def _difference(facts: TurnFacts, body: str) -> int | None:
    a, comma, b = (side.strip() for side in body.partition(","))
    if not comma or "," in b or a == b:
        return None
    first, second = _count(facts, a), _count(facts, b)
    return None if first is None or second is None else abs(first - second)


def _record(facts: TurnFacts, record_id: str) -> str | None:
    """The record's id linked to its page, with its product."""
    held = next((s for s in facts.citable_records() if s.record_id == record_id), None)
    if held is None:
        return None
    product = f" ({held.product})" if held.product else ""
    return f"[{record_id}]({held.url}){product}"


def linked_records(rendered: str) -> list[str]:
    """The ids of the records a rendered reply links, once each, in order."""
    found = (m.group("record_id") for m in _A_RECORD_LINK.finditer(rendered))
    return list(dict.fromkeys(found))


def _with_noun(count: int | None, facts: TurnFacts) -> str | None:
    return None if count is None else counted(count, facts.record_noun)


def _step_count(facts: TurnFacts, body: str) -> str | None:
    step = facts.step(body)
    if step is None or step.count is None:
        return None
    return counted(step.count, step.record_noun)


def _step_count_before(facts: TurnFacts, body: str) -> str | None:
    step = facts.step(body)
    if step is None or step.count_before is None:
        return None
    return counted(step.count_before, step.record_noun)


def _value(facts: TurnFacts, body: str) -> str | None:
    param = _parameter(facts, body)
    return None if param is None else param.shown()


def _source(facts: TurnFacts, body: str) -> str | None:
    param = _parameter(facts, body)
    return None if param is None else _SOURCE_WORDS[param.source]


_RENDERERS: dict[str, Callable[[TurnFacts, str], str | None]] = {
    "root": lambda facts, _: _with_noun(facts.root_count, facts),
    "root_before": lambda facts, _: _with_noun(facts.root_count_before, facts),
    "url": lambda facts, _: facts.strategy_url(),
    "count": _step_count,
    "before": _step_count_before,
    "diff": lambda facts, body: _with_noun(_difference(facts, body), facts),
    "compare": lambda facts, body: _with_noun(_compared(facts, body), facts),
    "last_change": lambda facts, body: _with_noun(last_change(facts, body), facts),
    "value": _value,
    "source": _source,
    "record": _record,
    "stat": lambda facts, body: statistic_value(facts.cited_statistics(), body),
    "cite": lambda facts, body: statistic_value(facts.cited_statistics(), body),
    "tally": lambda facts, body: tally_count(facts.tallies, body),
}


def _rendered(match: re.Match[str], facts: TurnFacts) -> str | None:
    """What one reference renders, or None when the facts hold nothing it names."""
    return _RENDERERS[reference_kind(match)](facts, match.group("body") or "")


def _unheld_words(match: re.Match[str]) -> str:
    match reference_kind(match):
        case "record":
            return match.group("body") or ""
        case "url":
            return "a link not shown"
        case "value" | "source" | "stat":
            return "a value not shown"
        case "cite":
            return ""
        case _:
            return "a count not shown"


def _rendered_with_notes(
    prose: str, facts: TurnFacts, label: str
) -> tuple[str, ReplyNotes]:
    notes = ReplyNotes(facts.cited_statistics(), label)

    def replaced(match: re.Match[str]) -> str:
        body = match.group("body") or ""
        if reference_kind(match) == "cite":
            return (notes.marker(body) or "") + (match.group("noun") or "")
        rendered = _rendered(match, facts)
        noun = match.group("noun") or ""
        shown = _unheld_words(match) if rendered is None else rendered
        kept = shown if reference_kind(match) in COUNTED_REFERENCES else shown + noun
        return match.group("gap") + kept

    return reference_and_its_noun(facts.counted_nouns()).sub(replaced, prose), notes


def render_reply(prose: str, facts: TurnFacts, label: str = "") -> str:
    """The reply with each reference replaced by the fact it names. A count
    reference carries the record noun, so the noun written after it is absorbed.
    A ``cite`` reference is a note marker after the word before it.
    A reference that names nothing the facts hold is shown as its plain words."""
    text, _ = _rendered_with_notes(prose, facts, label)
    return text


def nested_text(prose: str, facts: TurnFacts) -> str:
    def cited(match: re.Match[str]) -> str:
        value = statistic_value(facts.cited_statistics(), match.group("body"))
        return "" if value is None else f" ({value})"

    return render_reply(_A_CITE.sub(cited, prose), facts)


def shown_reply(prose: str, facts: TurnFacts, label: str) -> str:
    text, notes = _rendered_with_notes(prose, facts, label)
    return text + notes.block()


def _words(text: str) -> set[str]:
    """The whole tokens of the text, case folded."""
    return {found.strip(EDGE_MARKS).casefold() for found in A_TOKEN.findall(text)}


def _token_faults(text: str, facts: TurnFacts) -> Iterator[ProseFault]:
    """Each number and identifier token. A name that mixes letters and digits
    in neither shape ("PfEMP1", "3D7", "SignalP-6.0") is prose, and so is a
    number a request message writes as a whole token."""
    said = {word for message in facts.request_messages for word in _words(message)}
    for found in A_TOKEN.findall(text):
        token = found.strip(EDGE_MARKS)
        identifier = bool(token) and an_identifier(token)
        if not identifier and (
            _A_NUMBER.fullmatch(token) is None or token.casefold() in said
        ):
            continue
        record_id = "" if identifier else product_of(facts, token)
        if record_id:
            reference = f"[record:{record_id}]"
            yield ProseFault(
                token=token,
                kind="product_text",
                references=(reference,),
                record_id=record_id,
            )
            continue
        digits = _THE_DIGITS.search(token)
        numbered = (
            ()
            if digits is None
            else number_references(facts, digits.group().replace(",", ""))
        )
        yield ProseFault(
            token=token,
            kind="identifier" if identifier else "number",
            references=record_references(facts, token)
            or value_word_references(facts, token)
            or (
                statistic_word_references(facts.cited_statistics(), token)
                if identifier
                else ()
            )
            or numbered,
        )


def _outside(prose: str) -> str:
    """The prose with each reference and each list item number taken out."""
    return without_item_numbers(A_REFERENCE.sub(" ", prose))


def shape_faults(prose: str, facts: TurnFacts | None = None) -> list[ProseFault]:
    """Each link, number and identifier the prose writes outside a reference,
    and each misplaced reference, with the references of ``facts`` that render
    it."""
    held = TurnFacts() if facts is None else facts
    text = _outside(prose)
    links = [
        ProseFault(token=link, kind="link", references=link_references(held, link))
        for link in _A_LINK.findall(text)
    ]
    tokens = list(_token_faults(_A_LINK.sub(" ", text), held))
    brackets = [
        ProseFault(token=token, kind="malformed_reference")
        for token in malformed_brackets(prose)
    ]
    placed = [
        ProseFault(token=m.token, kind=m.kind, references=(m.reference,))
        for m in misplacements(prose, held.counted_nouns())
    ]
    return list(dict.fromkeys([*brackets, *links, *tokens, *placed]))


def _unheld(prose: str, facts: TurnFacts) -> Iterator[re.Match[str]]:
    for match in A_REFERENCE.finditer(prose):
        if _rendered(match, facts) is None:
            yield match


def unheld_references(prose: str, facts: TurnFacts) -> list[str]:
    """Each reference of the prose that names nothing the facts hold."""
    return [match.group() for match in _unheld(prose, facts)]


def _unheld_fault(match: re.Match[str], facts: TurnFacts) -> ProseFault:
    kind, body = reference_kind(match), match.group("body") or ""
    statistics = facts.cited_statistics()
    if kind in {"stat", "cite"}:
        keyed = statistic_keyed_references(statistics, body, kind)
        if keyed:
            shown = keyed[:_GROUP_SHOWN]
            return ProseFault(
                token=match.group(), kind="keyed_reference", references=shown
            )
    held = statistic_group_references(statistics, body) if kind == "stat" else ()
    return ProseFault(
        token=match.group(), kind="unheld_reference", references=held[:_GROUP_SHOWN]
    )


def standalone_counts(prose: str, facts: TurnFacts) -> list[ProseFault]:
    written = {match.group() for match in A_REFERENCE.finditer(prose)}
    return [
        ProseFault(
            token=alone,
            kind="standalone_count",
            references=(f"[compare:{v.label}:result]",),
        )
        for c in facts.comparisons
        for v in c.variants
        if v.larger_alone
        and (alone := f"[compare:{v.label}]") in written
        and f"[compare:{v.label}:result]" not in written
    ]


def prose_faults(prose: str, facts: TurnFacts) -> list[ProseFault]:
    """Each reference that names nothing the facts hold, each variant size alone
    quoted without its count in the strategy, then each fact the prose writes
    outside a reference."""
    unheld = [_unheld_fault(match, facts) for match in _unheld(prose, facts)]
    alone = standalone_counts(prose, facts)
    misused = [
        ProseFault(token=m.token, kind=m.kind, references=(m.reference,))
        for m in misused_references(prose, facts.cited_statistics())
    ]
    disputes = [
        ProseFault(token=d.token, kind="unnamed_dispute", references=(d.reference,))
        for d in unnamed_disputes(prose, facts.cited_statistics())
    ]
    found = [*unheld, *alone, *misused, *disputes, *shape_faults(prose, facts)]
    return list(dict.fromkeys(found))


__all__ = [
    "FaultKind",
    "ProseFault",
    "linked_records",
    "nested_text",
    "prose_faults",
    "render_reply",
    "shape_faults",
    "shown_reply",
    "unheld_references",
]
