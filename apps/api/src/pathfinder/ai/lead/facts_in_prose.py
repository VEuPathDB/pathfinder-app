"""What a reply writes that the facts part beside it does not hold: a number,
an identifier or a link it does not show, a value's source other than its row's,
and a record's product written another way. Pure text reading."""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher

from pathfinder.domain.scratchpad_facts import hard_facts
from pathfinder.domain.strategy.operational_spec import ValueSource
from pathfinder.domain.strategy.words import _numeral
from pathfinder.domain.turn_facts import RECORD_WORDS, TurnFacts, value_words

# A link, an ordered list's item number, and a run of word characters that a
# number or an identifier is made of.
_A_URL = re.compile(r"https?://[^\s<>()\[\]\"'`]+")
_AN_ITEM_NUMBER = re.compile(r"^\s*\d+[.)](?=\s)", re.MULTILINE)
_A_TOKEN = re.compile(r"[\w:./,%+-]+")
_EDGE_MARKS = ".,:;/+-_"
# A number, a range, a ratio or a date is digits and these marks only.
_NUMBER_CHARACTERS = frozenset("0123456789.,%+-/")
# A link's path and query separate the identifiers a link shows.
_A_PATH_MARK = re.compile(r"[/?=&#]")
_AN_ORDINAL = re.compile(r"(\d+)(?:st|nd|rd|th)")
_SCIENTIFIC = re.compile(r"\d+(?:\.\d+)?[eE][+-]?\d+")
# A number written against its unit, as in 37C.
_A_GLUED_UNIT = re.compile(r"(\d[\d.,]*)([^\W\d_]+)")
# A thousands separator sits between a digit and exactly three more digits.
_A_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_A_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)
# Prose names one step or two sides as often as it counts, so these two
# number words are read as words.
_STRUCTURAL_NUMERALS = frozenset({"one", "two"})


def _link(found: str) -> str:
    return found.rstrip("/.,;:")


def _unglued(token: str) -> list[str]:
    """The token, or the number and the unit it is written against."""
    glued = None if _AN_ORDINAL.fullmatch(token) else _A_GLUED_UNIT.fullmatch(token)
    return [token] if glued is None else [glued.group(1), glued.group(2)]


def _tokens(text: str) -> list[str]:
    stripped = (token.strip(_EDGE_MARKS) for token in _A_TOKEN.findall(text))
    return [part for token in stripped if token for part in _unglued(token)]


def _a_number(token: str) -> bool:
    return any(c.isdigit() for c in token) and set(token) <= _NUMBER_CHARACTERS


def _the_number(token: str) -> str | None:
    """The number a token writes, an ordinal's, a number word's and a number
    in scientific notation's digits included, or None."""
    if _a_number(token):
        return _A_SEPARATOR.sub("", token)
    if _SCIENTIFIC.fullmatch(token):
        return format(Decimal(token).normalize(), "f")
    ordinal = _AN_ORDINAL.fullmatch(token)
    if ordinal is not None:
        return ordinal.group(1)
    word = token.casefold()
    spelled = _numeral(word)
    if spelled == word or word in _STRUCTURAL_NUMERALS:
        return None
    return spelled


def _an_identifier(token: str, machine_names: Collection[str]) -> bool:
    """A token with an identifier's shape: a site's gene id, a snake_case or
    colon-joined name, or a name the product uses and never shows."""
    shaped = "_" in token or ":" in token or token in hard_facts(token)
    return shaped or token in machine_names


def _neighbours(words: list[str], at: int) -> tuple[str, str]:
    before = words[at - 1].casefold() if at > 0 else ""
    after = words[at + 1].casefold() if at + 1 < len(words) else ""
    return before, after


@dataclass(frozen=True)
class _Held:
    """What the shown text holds: its tokens, the numbers it counts, and each
    number of a record's own words beside the words it stands next to."""

    tokens: frozenset[str]
    numbers: frozenset[str]
    labelled: frozenset[tuple[str, str]]

    def holds_number(self, number: str, before: str, after: str) -> bool:
        return (
            number in self.numbers
            or (before, number) in self.labelled
            or (number, after) in self.labelled
        )


def _counted_numbers(tokens: Collection[str]) -> set[str]:
    """Every number the tokens write, the parts a hyphen joins included."""
    numbers = {n for token in tokens if (n := _the_number(token)) is not None}
    numbers.update(
        n
        for token in tokens
        if _the_number(token) is None
        for part in token.split("-")
        if (n := _the_number(part)) is not None
    )
    return numbers


def _held(shown: str) -> _Held:
    lines = shown.splitlines()
    words = [
        line.removeprefix(RECORD_WORDS)
        for line in lines
        if line.startswith(RECORD_WORDS)
    ]
    counted = [line for line in lines if not line.startswith(RECORD_WORDS)]
    held = _tokens(_A_PATH_MARK.sub(" ", "\n".join(counted)))
    labelled: set[tuple[str, str]] = set()
    record_tokens: set[str] = set()
    for line in words:
        found = _tokens(line)
        for at, token in enumerate(found):
            number = _the_number(token)
            if number is None:
                record_tokens.add(token)
                continue
            before, after = _neighbours(found, at)
            labelled.update({(before, number), (number, after)})
    return _Held(
        tokens=frozenset({*held, *record_tokens}),
        numbers=frozenset(_counted_numbers(held)),
        labelled=frozenset(labelled),
    )


def _printed(
    token: str,
    held: _Held,
    machine_names: Collection[str],
    neighbours: tuple[str, str] = ("", ""),
) -> bool:
    """Whether the token is a number or an identifier the facts do not hold.

    A hyphen joins a number to its unit, so each part is read on its own.
    """
    if token in held.tokens:
        return False
    number = _the_number(token)
    if number is not None:
        return not held.holds_number(number, *neighbours)
    if _A_UUID.fullmatch(token):
        return True
    if "-" in token:
        return any(_printed(p, held, machine_names) for p in token.split("-"))
    return _an_identifier(token, machine_names)


def outside_the_facts(
    prose: str, shown: str, machine_names: Collection[str]
) -> list[str]:
    """Every link, number and identifier the prose prints that ``shown`` does not.

    A number or an identifier the facts show whole is a fact inside the block.
    A number of a record's own words is held only beside the same word.
    """
    held_links = {_link(found) for found in _A_URL.findall(shown)}
    held = _held(shown)
    links = [
        _link(found)
        for found in _A_URL.findall(prose)
        if _link(found) not in held_links
    ]
    words = _tokens(_A_URL.sub(" ", _AN_ITEM_NUMBER.sub(" ", prose)))
    printed = [
        token
        for at, token in enumerate(words)
        if _printed(token, held, machine_names, _neighbours(words, at))
    ]
    return list(dict.fromkeys([*links, *printed]))


# The words that say who set a value, longest first, and the sources a row may
# show for each. A value the strategy held names no setter, so any word fits it.
_SOURCE_WORDS: tuple[tuple[tuple[str, ...], ValueSource], ...] = (
    (("you", "asked", "for"), "stated"),
    (("you", "stated"), "stated"),
    (("you", "named"), "stated"),
    (("you", "specified"), "stated"),
    (("you", "requested"), "stated"),
    (("you", "chose"), "card"),
    (("you", "picked"), "card"),
    (("site's", "default"), "default"),
    (("site", "default"), "default"),
    (("default",), "default"),
    (("i", "chose"), "chosen"),
    (("i", "picked"), "chosen"),
    (("chosen",), "chosen"),
)
_FITS: dict[ValueSource, frozenset[ValueSource]] = {
    "stated": frozenset({"stated", "card", "held"}),
    "card": frozenset({"stated", "card", "held"}),
    "default": frozenset({"default", "held"}),
    "chosen": frozenset({"chosen", "held"}),
}
# A clause ends at a mark, and a noun phrase at one of these words.
_A_CLAUSE_MARK = re.compile(r"[,;:!?()\[\]\n]|\.(?!\d)")
_COPULAS = frozenset({"is", "are", "was", "were", "stays", "remains"})
_ARTICLES = frozenset({"the", "a", "an"})
_PHRASE_ENDS = (
    frozenset(
        {"from", "of", "in", "at", "on", "for", "with", "by", "to", "and", "or"}
        | {"but", "which", "that", "because", "so", "as", "than", "while", "where"}
    )
    | _COPULAS
    | _ARTICLES
)


@dataclass(frozen=True)
class MisattributedSource:
    """A phrase that names a value and a source its facts row does not show."""

    phrase: str
    claimed: ValueSource
    shown: frozenset[ValueSource]


def _term_at(words: Sequence[str], at: int) -> tuple[int, ValueSource] | None:
    """The length and the source of the source term that starts at ``at``."""
    for term, source in _SOURCE_WORDS:
        if tuple(words[at : at + len(term)]) == term:
            return len(term), source
    return None


def _after(words: Sequence[str], start: int) -> int:
    """Where the noun phrase that starts at ``start`` ends."""
    end = start + 1 if start < len(words) and words[start] == "of" else start
    while end < len(words) and words[end] not in _PHRASE_ENDS:
        end += 1
    return end


def _before(words: Sequence[str], end: int) -> int:
    """Where the noun phrase that ends at ``end`` starts."""
    start = end
    while start > 0 and words[start - 1] not in _PHRASE_ENDS:
        start -= 1
    return start


def _named_span(
    words: Sequence[str], at: int, length: int, source: ValueSource
) -> tuple[int, int, int, int]:
    """The span of the phrase the term at ``at`` speaks of, and its value words:
    the words after the term, or before a researcher's term, or the subject of
    the copula the term completes."""
    after = _after(words, at + length)
    if after > at + length:
        return at, after, at + length, after
    lead = at - 1 if at > 0 and words[at - 1] in _ARTICLES else at
    if source in {"stated", "card"}:
        start = _before(words, at)
        return start, at + length, start, at
    if lead > 0 and words[lead - 1] in _COPULAS:
        start = _before(words, lead - 1)
        return start, at + length, start, lead - 1
    return at, at + length, at, at


def _clause_sources(clause: str, facts: TurnFacts) -> MisattributedSource | None:
    shown_words = clause.split()
    words = [" ".join(value_words(w)) for w in shown_words]
    at = 0
    while at < len(words):
        term = _term_at(words, at)
        if term is None:
            at += 1
            continue
        length, claimed = term
        start, end, first, last = _named_span(words, at, length, claimed)
        named = facts.sources_named(value_words(" ".join(shown_words[first:last])))
        if named and not named & _FITS[claimed]:
            phrase = " ".join(shown_words[start:end]).strip("*_`\"'")
            return MisattributedSource(phrase=phrase, claimed=claimed, shown=named)
        at += length
    return None


def misattributed_source(prose: str, facts: TurnFacts) -> MisattributedSource | None:
    """The first phrase that says a value was set by a source its facts row
    does not show, or None."""
    for clause in _A_CLAUSE_MARK.split(prose):
        found = _clause_sources(clause, facts)
        if found is not None:
            return found
    return None


@dataclass(frozen=True)
class AlteredRecordText:
    """A word of a record's product the reply writes another way."""

    record_id: str
    written: str
    recorded: str


# A written word this close to the record's word, letter by letter, is a copy
# of it written another way.
_RESPELLED = 0.8
# A shorter word is too short to tell a respelling from another word.
_SHORTEST_RESPELLED = 4
# The record's words a copy matches on the one side an edge of the product leaves.
_EDGE_CONTEXT = 2


def _as_written(word: str) -> str:
    """The word without the marks around it, a parenthesis it opens or closes
    alone included."""
    bare = word.strip(".,;:!?*_`\"'")
    if bare.startswith("(") and ")" not in bare:
        bare = bare[1:]
    if bare.endswith(")") and "(" not in bare:
        bare = bare[:-1]
    return bare


def _record_word(word: str) -> str:
    return _as_written(word).casefold()


def _in_context(
    written: Sequence[str], at: int, recorded: Sequence[str], j: int
) -> bool:
    """Whether the words beside the written word are the record's words beside
    its word: one on each side, or two on the one side an edge leaves."""
    last = len(recorded) - 1
    if 0 < j < last:
        pairs = [(at - 1, j - 1), (at + 1, j + 1)]
    else:
        step = 1 if j == 0 else -1
        pairs = [(at + step * k, j + step * k) for k in range(1, _EDGE_CONTEXT + 1)]
    return all(
        0 <= r <= last and 0 <= w < len(written) and written[w] == recorded[r]
        for w, r in pairs
    )


def _respelled(word: str, record_word: str) -> bool:
    return (
        word != record_word
        and min(len(word), len(record_word)) >= _SHORTEST_RESPELLED
        and SequenceMatcher(None, word, record_word).ratio() >= _RESPELLED
    )


def altered_record_text(prose: str, facts: TurnFacts) -> list[AlteredRecordText]:
    """Each word of a record's product the prose writes another way, beside the
    record's own words around it."""
    shown = prose.split()
    written = [_record_word(w) for w in shown]
    found: list[AlteredRecordText] = []
    for record_id, product in facts.record_products():
        recorded_shown = product.split()
        recorded = [_record_word(w) for w in recorded_shown]
        found.extend(
            AlteredRecordText(
                record_id=record_id,
                written=_as_written(shown[at]),
                recorded=_as_written(recorded_shown[j]),
            )
            for at, word in enumerate(written)
            for j, record_word in enumerate(recorded)
            if _respelled(word, record_word) and _in_context(written, at, recorded, j)
        )
    return list(dict.fromkeys(found))
