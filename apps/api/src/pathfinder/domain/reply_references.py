"""The references a reply writes in place of a fact, the text each renders from
the turn's facts, and the faults of a reply that writes a fact itself."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from itertools import combinations
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from pathfinder.domain.comparison_facts import ComparedVariant
from pathfinder.domain.count_words import counted
from pathfinder.domain.reference_grammar import (
    A_REFERENCE,
    COUNTED_REFERENCES,
    malformed_brackets,
    reference_and_its_noun,
    reference_kind,
)
from pathfinder.domain.reference_placement import misplacements
from pathfinder.domain.scratchpad_facts import hard_facts
from pathfinder.domain.strategy.operational_spec import ValueSource
from pathfinder.domain.turn_facts import ParameterFact, TurnFacts

_A_LINK = re.compile(r"(?:https?://|www\.)[^\s<>()\[\]\"'`]+")
# An ordered list's item number is the list's mark, not a fact.
_AN_ITEM_NUMBER = re.compile(r"^\s*(\d+)[.)](?=\s)", re.MULTILINE)
_A_TOKEN = re.compile(r"[\w:./,%+-]+")
_EDGE_MARKS = ".,:;/+-_"
_A_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)
_A_SOURCE_WORD = re.compile(r"\b(?:default|chosen|stated|you asked)\b", re.IGNORECASE)
_THE_DIGITS = re.compile(r"\d[\d,]*(?:\.\d+)?")
_NUM = r"\d[\d,]*(?:\.\d+)?(?:[eE][+-]?\d+)?"
# A count or a value: a number, a range or ratio of numbers, with a percent or a
# unit glued to it ("37C", "5x", "2-fold"), or a log scale ("log2").
_A_NUMBER = re.compile(rf"[+-]?{_NUM}(?:[-/]{_NUM})*(?:%|-?[A-Za-z]{{1,4}})?|log\d+")
# The protein-domain and Ensembl accessions a record carries.
_AN_ACCESSION = re.compile(r"PF\d{5}|IPR\d{6}|ENS[A-Z]*[GTP]\d{11}")
# The count a comparison reference names after its variant.
_COMPARED = ("unique", "result", "shared")

_SOURCE_WORDS: dict[ValueSource, str] = {
    "stated": "you stated",
    "card": "your answer on a card",
    "default": "the site's default",
    "chosen": "chosen",
    "held": "held by the strategy",
}
# The value sources each source word of a reply says.
_SAID_BY: dict[str, frozenset[ValueSource]] = {
    "default": frozenset({"default"}),
    "chosen": frozenset({"chosen"}),
    "stated": frozenset({"stated", "card"}),
    "you asked": frozenset({"stated", "card"}),
}

type FaultKind = Literal[
    "number",
    "identifier",
    "link",
    "source_word",
    "unheld_reference",
    "malformed_reference",
    "number_word",
    "noun_after_count",
    "product_text",
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


class UnheldReferenceError(ValueError):
    """A reference names nothing the facts hold."""


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


def _last_change(facts: TurnFacts, side: str) -> int | None:
    return None if facts.last_change is None else facts.last_change.count(side)


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
            return _last_change(facts, body)
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
    read = next(
        (s for s in (*facts.sources, *facts.named_genes) if s.record_id == record_id),
        None,
    )
    if read is not None:
        product = f" ({read.product})" if read.product else ""
        return f"[{record_id}]({read.url}){product}"
    listed = next(
        (r for fact in facts.listed for r in fact.records if r.record_id == record_id),
        None,
    )
    return None if listed is None else f"[{record_id}]({listed.url})"


def _with_noun(count: int | None, facts: TurnFacts) -> str | None:
    return None if count is None else counted(count, facts.record_noun)


def _step_count(facts: TurnFacts, body: str) -> str | None:
    step = facts.step(body)
    return None if step is None else _with_noun(step.count, facts)


def _step_count_before(facts: TurnFacts, body: str) -> str | None:
    step = facts.step(body)
    return None if step is None else _with_noun(step.count_before, facts)


def _value(facts: TurnFacts, body: str) -> str | None:
    param = _parameter(facts, body)
    return None if param is None else param.shown()


def _source(facts: TurnFacts, body: str) -> str | None:
    param = _parameter(facts, body)
    return None if param is None else _SOURCE_WORDS[param.source]


_RENDERERS: dict[str, Callable[[TurnFacts, str], str | None]] = {
    "root": lambda facts, _: _with_noun(facts.root_count, facts),
    "root_before": lambda facts, _: _with_noun(facts.root_count_before, facts),
    "url": lambda facts, _: facts.strategy_url,
    "count": _step_count,
    "before": _step_count_before,
    "diff": lambda facts, body: _with_noun(_difference(facts, body), facts),
    "compare": lambda facts, body: _with_noun(_compared(facts, body), facts),
    "last_change": lambda facts, body: _with_noun(_last_change(facts, body), facts),
    "value": _value,
    "source": _source,
    "record": _record,
}


def _rendered(match: re.Match[str], facts: TurnFacts) -> str | None:
    """What one reference renders, or None when the facts hold nothing it names."""
    return _RENDERERS[reference_kind(match)](facts, match.group("body") or "")


def render_reply(prose: str, facts: TurnFacts) -> str:
    """The reply with each reference replaced by the fact it names. A count
    reference carries the record noun, so the noun written after it is absorbed."""

    def replaced(match: re.Match[str]) -> str:
        rendered = _rendered(match, facts)
        if rendered is None:
            reference = match.group().removesuffix(match.group("noun") or "")
            msg = f"{reference} names nothing the facts hold"
            raise UnheldReferenceError(msg)
        noun = match.group("noun") or ""
        return (
            rendered if reference_kind(match) in COUNTED_REFERENCES else rendered + noun
        )

    return reference_and_its_noun(facts.record_noun).sub(replaced, prose)


def _count_references(facts: TurnFacts) -> Iterator[tuple[str, int]]:
    """Each reference to a count the facts hold, with its count."""
    for step in facts.steps:
        if step.count is not None:
            yield step.step_id, step.count
        if step.count_before is not None:
            yield f"before:{step.step_id}", step.count_before
    for name, count in (
        ("root", facts.root_count),
        ("root_before", facts.root_count_before),
        ("last_change:before", _last_change(facts, "before")),
        ("last_change:after", _last_change(facts, "after")),
    ):
        if count is not None:
            yield name, count
    for comparison in facts.comparisons:
        for v in comparison.variants:
            yield f"compare:{v.label}", v.gene_count
            yield f"compare:{v.label}:unique", v.unique_count
            if v.result_count is not None:
                yield f"compare:{v.label}:result", v.result_count


def _shown(side: str) -> str:
    """A count side as a reference of its own."""
    if side in ("root", "root_before") or side.startswith(
        ("before:", "compare:", "last_change:")
    ):
        return f"[{side}]"
    return f"[count:{side}]"


def _number_references(facts: TurnFacts, number: str) -> tuple[str, ...]:
    """The references that render the number: a count, a difference of two
    counts, the genes two variants share, or a value."""
    counts = list(_count_references(facts))
    held = [_shown(side) for side, n in counts if str(n) == number]
    held.extend(
        f"[diff:{a},{b}]"
        for (a, n), (b, m) in combinations(counts, 2)
        if str(abs(n - m)) == number
    )
    held.extend(
        f"[compare:{o.a},{o.b}:shared]"
        for c in facts.comparisons
        for o in c.overlaps
        if str(o.shared) == number
    )
    held.extend(
        f"[value:{step.step_id}.{p.name}]"
        for step in facts.steps
        for p in step.parameters
        if p.value == number
    )
    return tuple(dict.fromkeys(held))


def _record_references(facts: TurnFacts, token: str) -> tuple[str, ...]:
    ids = {
        *(s.record_id for s in (*facts.sources, *facts.named_genes)),
        *(r.record_id for fact in facts.listed for r in fact.records),
    }
    return (f"[record:{token}]",) if token in ids else ()


def _link_references(facts: TurnFacts, link: str) -> tuple[str, ...]:
    if link == facts.strategy_url:
        return ("[url]",)
    return tuple(
        f"[record:{s.record_id}]"
        for s in (*facts.sources, *facts.named_genes)
        if s.record_id and s.url == link
    )


def _source_references(facts: TurnFacts, word: str) -> tuple[str, ...]:
    said = _SAID_BY[" ".join(word.casefold().split())]
    return tuple(
        f"[source:{step.step_id}.{p.name}]"
        for step in facts.steps
        for p in step.parameters
        if p.source in said
    )


def _an_identifier(token: str) -> bool:
    """A site's gene id, a domain or Ensembl accession, a search name, or a
    snake_case, colon-joined or uuid token. A count is never an identifier."""
    named = any(c.isalpha() for c in token) and token in hard_facts(token)
    shaped = "_" in token or ":" in token or named
    accession = _AN_ACCESSION.fullmatch(token) or _A_UUID.fullmatch(token)
    return shaped or accession is not None


def _value_word_references(facts: TurnFacts, token: str) -> tuple[str, ...]:
    """The value references whose value or label holds the token as a word."""
    return tuple(
        f"[value:{step.step_id}.{p.name}]"
        for step in facts.steps
        for p in step.parameters
        if token in p.value.split() or token in p.label.split()
    )


def _product_of(facts: TurnFacts, token: str) -> str:
    """The id of a record whose product holds the number as a word, or ""."""
    return next(
        (
            s.record_id
            for s in (*facts.sources, *facts.named_genes)
            if s.record_id
            and token in (w.strip(_EDGE_MARKS) for w in _A_TOKEN.findall(s.product))
        ),
        "",
    )


def _words(text: str) -> set[str]:
    """The whole tokens of the text, case folded."""
    return {found.strip(_EDGE_MARKS).casefold() for found in _A_TOKEN.findall(text)}


def _token_faults(text: str, facts: TurnFacts) -> Iterator[ProseFault]:
    """Each number and identifier token. A name that mixes letters and digits
    in neither shape ("PfEMP1", "3D7", "SignalP-6.0") is prose, and so is a
    number a request message writes as a whole token."""
    said = {word for message in facts.request_messages for word in _words(message)}
    for found in _A_TOKEN.findall(text):
        token = found.strip(_EDGE_MARKS)
        identifier = bool(token) and _an_identifier(token)
        if not identifier and (
            _A_NUMBER.fullmatch(token) is None or token.casefold() in said
        ):
            continue
        record_id = "" if identifier else _product_of(facts, token)
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
            else _number_references(facts, digits.group().replace(",", ""))
        )
        yield ProseFault(
            token=token,
            kind="identifier" if identifier else "number",
            references=_record_references(facts, token)
            or _value_word_references(facts, token)
            or numbered,
        )


def _without_item_numbers(text: str) -> str:
    """The text with each ordered list's item numbers taken out. An item number
    is one that starts a list or follows the item number before it."""
    previous = 0

    def exempt(match: re.Match[str]) -> str:
        nonlocal previous
        number = int(match.group(1))
        if number not in (1, previous + 1):
            return match.group()
        previous = number
        return " "

    return _AN_ITEM_NUMBER.sub(exempt, text)


def _outside(prose: str) -> str:
    """The prose with each reference and each list item number taken out."""
    return _without_item_numbers(A_REFERENCE.sub(" ", prose))


def shape_faults(prose: str, facts: TurnFacts | None = None) -> list[ProseFault]:
    """Each link, number, identifier and source word the prose writes outside a
    reference, and each misplaced reference, with the references of ``facts``
    that render it."""
    held = TurnFacts() if facts is None else facts
    text = _outside(prose)
    links = [
        ProseFault(token=link, kind="link", references=_link_references(held, link))
        for link in _A_LINK.findall(text)
    ]
    words = [
        ProseFault(
            token=word.group(),
            kind="source_word",
            references=_source_references(held, word.group()),
        )
        for word in _A_SOURCE_WORD.finditer(text)
    ]
    tokens = list(_token_faults(_A_LINK.sub(" ", text), held))
    brackets = [
        ProseFault(token=token, kind="malformed_reference")
        for token in malformed_brackets(prose)
    ]
    placed = [
        ProseFault(token=m.token, kind=m.kind, references=(m.reference,))
        for m in misplacements(prose, held.record_noun)
    ]
    return list(dict.fromkeys([*brackets, *links, *tokens, *words, *placed]))


def unheld_references(prose: str, facts: TurnFacts) -> list[str]:
    """Each reference of the prose that names nothing the facts hold."""
    return [
        match.group()
        for match in A_REFERENCE.finditer(prose)
        if _rendered(match, facts) is None
    ]


def prose_faults(prose: str, facts: TurnFacts) -> list[ProseFault]:
    """Each reference that names nothing the facts hold, then each fact the
    prose writes outside a reference."""
    unheld = [
        ProseFault(token=reference, kind="unheld_reference")
        for reference in unheld_references(prose, facts)
    ]
    return list(dict.fromkeys([*unheld, *shape_faults(prose, facts)]))


__all__ = [
    "ProseFault",
    "UnheldReferenceError",
    "prose_faults",
    "render_reply",
    "shape_faults",
    "unheld_references",
]
