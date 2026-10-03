"""How a researcher's message states a requirement: an organism written with
its genus abbreviated, and the operator its words put between a combination's
terms."""

from __future__ import annotations

import itertools
import re
from collections import Counter
from collections.abc import Sequence
from typing import Literal, NamedTuple

from veupathdb.model import CamelModel

from pathfinder.domain.strategy.constraints import (
    CombinationOperator,
    CombinationRequest,
    Constraint,
    ConstraintKind,
    message_states,
)
from pathfinder.domain.strategy.words import WORD, words_of

# A binomial is a genus and a species epithet, and only a genus abbreviates.
_BINOMIAL_WORDS = 2


def _genus_abbreviated(value: str) -> str:
    """The binomial with its genus as an initial, as a researcher writes it.

    A one-word name abbreviates to a single letter, which names nothing, so it
    is returned whole.
    """
    words = words_of(value)
    if len(words) < _BINOMIAL_WORDS:
        return value
    return " ".join([words[0][0], *words[1:]])


def message_states_constraint(message: str, constraint: Constraint) -> bool:
    """Whether the message states the value this constraint carries.

    A combination is stated when the message carries its terms and joins them
    with its operator: both are the user's. An organism is written as the
    binomial, which the message may carry with the genus abbreviated.
    """
    value = constraint.requested_value
    if constraint.kind is ConstraintKind.ORGANISM:
        return message_states(message, value) or message_states(
            message, _genus_abbreviated(value)
        )
    request = (
        CombinationRequest.parse(value)
        if constraint.kind is ConstraintKind.COMBINATION
        else None
    )
    if request is None:
        return message_states(message, value)
    return combination_operator_is_stated(message, request)


_AND_OR_RE = re.compile(r"\band\s*/\s*or\b", re.IGNORECASE)
_UNION_RE = re.compile(r"\bunion\b", re.IGNORECASE)
_INTERSECT_RE = re.compile(r"\bintersect(?:ion|s|ed)?\b", re.IGNORECASE)
_JOINING_WORDS = frozenset({"with", "plus"})
_AS_WELL_AS = "as well as"
_EITHER = "either"
_CLAUSE_BREAK_RE = re.compile(r"[,;:.!?]")
# An "include" verb adds an alternative to what the request already finds.
_ADDS_AN_ALTERNATIVE_RE = re.compile(
    r"\balso\s+include|\bto\s+include\b|(?:^|[,;.]\s*)include\b"
    r"|\bas\s+an?\s+alternative\b",
    re.IGNORECASE,
)
# Words that add a term and state neither operator: a class added to a class
# is an OR, a property added to a property is an AND.
_STATES_NEITHER_RE = re.compile(
    r"\bin\s+addition\s+to\b|\bas\s+well\b(?!\s+as\b)", re.IGNORECASE
)


def adds_an_alternative(text: str) -> bool:
    """Whether the text adds an alternative with an "include" verb."""
    return bool(_ADDS_AN_ALTERNATIVE_RE.search(text))


def _states_neither(text: str) -> bool:
    return bool(_STATES_NEITHER_RE.search(text))


# What a connective's own words state. "list" is a bare separator, which takes
# the operator of the next conjunction in the list.
_Stated = Literal["OR", "AND", "both", "list"]


class Connective(CamelModel):
    """The message text between two consecutive terms, and the operator it states.

    ``operator`` is None when the text states both operators.
    """

    before: str
    after: str
    text: str
    operator: CombinationOperator | None


class CombinationReading(CamelModel):
    """How the message itself joins a combination's terms, in message order.

    ``named`` is the operator the message names as a set operation, or OR when
    the words after the last term add it as an alternative.
    """

    connectives: list[Connective]
    named: CombinationOperator | None = None

    def states(self, operator: CombinationOperator) -> bool:
        if self.named is not None:
            return self.named == operator
        return all(c.operator == operator for c in self.connectives)

    def departures(self, operator: CombinationOperator) -> list[Connective]:
        """The connectives that do not state this operator."""
        return [c for c in self.connectives if c.operator != operator]


class _Span(NamedTuple):
    term: str
    start: int
    end: int


def _phrase(wanted: Sequence[str], words: Sequence[str]) -> tuple[int, int] | None:
    """Where the term's words run in order in the message, first occurrence."""
    width = len(wanted)
    return next(
        (
            (left, left + width - 1)
            for left in range(len(words) - width + 1)
            if list(words[left : left + width]) == list(wanted)
        ),
        None,
    )


def _window(wanted: set[str], words: Sequence[str]) -> tuple[int, int] | None:
    """The shortest run of message words that carries every word of the term."""
    held: Counter[str] = Counter()
    missing = len(wanted)
    best: tuple[int, int] | None = None
    left = 0
    for right, word in enumerate(words):
        if word in wanted:
            held[word] += 1
            missing -= held[word] == 1
        while wanted and not missing:
            if best is None or right - left < best[1] - best[0]:
                best = (left, right)
            dropped = words[left]
            if dropped in wanted:
                held[dropped] -= 1
                missing += held[dropped] == 0
            left += 1
    return best


def _span(term: str, tokens: Sequence[re.Match[str]]) -> _Span | None:
    """Where the message carries the term: its phrase, else its words' shortest run."""
    wanted = words_of(term)
    words = [token.group().casefold() for token in tokens]
    found = _phrase(wanted, words) or _window(set(wanted), words)
    if not wanted or found is None:
        return None
    return _Span(term, tokens[found[0]].start(), tokens[found[1]].end())


def _between(message: str, first: _Span, second: _Span) -> tuple[str, list[str]]:
    """The connective text and its words.

    Two spans that share a phrase are joined by the words before the second
    that are not the first term's own.
    """
    if second.start >= first.end:
        text = message[first.end : second.start]
        return text, words_of(text)
    text = message[first.start : second.start]
    own = set(words_of(first.term))
    return text, [word for word in words_of(text) if word not in own]


def _stated_by(text: str, words: Sequence[str]) -> _Stated:
    if _AND_OR_RE.search(text) or adds_an_alternative(text):
        return "OR"
    if _states_neither(text):
        return "both"
    says_or, says_and = "or" in words, "and" in words
    if says_or and says_and:
        return "both"
    if says_or:
        return "OR"
    if says_and or _JOINING_WORDS & set(words) or _AS_WELL_AS in " ".join(words):
        return "AND"
    return "list"


def _named_operator(message: str) -> CombinationOperator | None:
    union, intersect = _UNION_RE.search(message), _INTERSECT_RE.search(message)
    if union and not intersect:
        return "OR"
    if intersect and not union:
        return "AND"
    return None


def _resolved(
    stated: Sequence[_Stated], default: CombinationOperator | None
) -> list[CombinationOperator | None]:
    """Each connective's operator, a bare separator taking the next conjunction's."""
    following: CombinationOperator | None = default
    resolved: list[CombinationOperator | None] = []
    for own in reversed(stated):
        match own:
            case "OR" | "AND":
                following = own
            case "both":
                following = None
            case "list":
                pass
        resolved.append(following)
    return resolved[::-1]


def read_combination(
    message: str, request: CombinationRequest
) -> CombinationReading | None:
    """How the message joins the request's terms, or None when a term is absent.

    Each term is located by its words, and the connectives are read between
    consecutive terms in message order. An "or" inside one term's span is an
    alternative within that term, so it is never read as a connective.
    """
    tokens = list(WORD.finditer(message))
    located = [_span(term, tokens) for term in request.terms]
    spans = sorted(
        (span for span in located if span is not None),
        key=lambda span: (span.start, span.end),
    )
    if len(spans) != len(located):
        return None
    pairs = list(itertools.pairwise(spans))
    between = [_between(message, first, second) for first, second in pairs]
    clause = _CLAUSE_BREAK_RE.split(message[: spans[0].start])[-1]
    opening = [*words_of(clause), *words_of(spans[0].term)[:1]]
    default: CombinationOperator | None = (
        "OR"
        if _EITHER in opening or adds_an_alternative(clause)
        else None
        if _states_neither(clause)
        else "AND"
    )
    operators = _resolved([_stated_by(*joined) for joined in between], default)
    trailing = _CLAUSE_BREAK_RE.split(message[spans[-1].end :])[0]
    if operators and _states_neither(trailing):
        operators[-1] = None
    named = _named_operator(message)
    return CombinationReading(
        connectives=[
            Connective(before=first.term, after=second.term, text=text, operator=op)
            for (first, second), (text, _), op in zip(
                pairs, between, operators, strict=True
            )
        ],
        named="OR" if named is None and adds_an_alternative(trailing) else named,
    )


def combination_operator_is_stated(message: str, request: CombinationRequest) -> bool:
    """Whether the message carries every term and joins them with this operator."""
    reading = read_combination(message, request)
    return reading is not None and reading.states(request.operator)
