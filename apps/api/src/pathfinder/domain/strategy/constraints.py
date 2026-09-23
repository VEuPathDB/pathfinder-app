from __future__ import annotations

import itertools
import re
from collections import Counter
from collections.abc import Sequence
from enum import StrEnum
from typing import Literal, NamedTuple

from pydantic import Field
from veupathdb.model import CamelModel


class ConstraintKind(StrEnum):
    DATA_TYPE = "data_type"
    STATISTICAL_THRESHOLD = "statistical_threshold"
    FOLD_CHANGE = "fold_change"
    COMPARATOR = "comparator"
    ORGANISM = "organism"
    RECORD_TYPE = "record_type"
    PERCENTILE = "percentile"
    COMBINATION = "combination"
    OTHER = "other"


# Every dimension a constraint can state, as an agent must spell it.
CONSTRAINT_KINDS = ", ".join(kind.value for kind in ConstraintKind)


class ConstraintSource(StrEnum):
    USER_EXPLICIT = "user_explicit"
    ASSUMED = "assumed"


class ConstraintStatus(StrEnum):
    PROVISIONAL = "provisional"
    GROUNDED = "grounded"
    SUBSTITUTED = "substituted"
    UNGROUNDABLE = "ungroundable"


class Constraint(CamelModel):
    kind: ConstraintKind
    requested_value: str = Field(min_length=1)
    label: str = Field(min_length=1)
    source: ConstraintSource = ConstraintSource.ASSUMED
    hard: bool = True
    """A hard requirement ('RNA-Seq only') blocks if unmet; a soft preference
    ('RNA-Seq preferred, microarray fallback ok') is surfaced but never blocks."""


class GroundedConstraint(CamelModel):
    constraint: Constraint
    status: ConstraintStatus
    realized_value: str | None = None
    # The parameter the value was read from, empty when the grounding read no
    # single parameter.
    realized_param: str = ""
    note: str = ""


_QUESTION_LIMIT = 300
_LABEL_LIMIT = 120


class OpenQuestion(CamelModel):
    """A question the assistant asked the user, and the value it recommended.

    The recommendation is typed here so the next turn reads it instead of the
    reply text that offered it.
    """

    question: str = Field(min_length=1, max_length=_QUESTION_LIMIT)
    dimension: ConstraintKind = ConstraintKind.OTHER
    recommended_value: str = ""

    @property
    def decides_a_dimension(self) -> bool:
        """Whether the question names the dimension its answer states.

        A question recorded as bare text carries the default dimension, which
        names nothing.
        """
        return (
            bool(self.recommended_value) or self.dimension is not ConstraintKind.OTHER
        )

    def recommendation(self) -> Constraint | None:
        """The recommended value as a constraint, or None when none was offered."""
        if not self.recommended_value:
            return None
        return Constraint(
            kind=self.dimension,
            requested_value=self.recommended_value,
            label=self.question[:_LABEL_LIMIT],
            source=ConstraintSource.ASSUMED,
            hard=False,
        )


_WORD_RE = re.compile(r"[a-z0-9]+")
# A binomial is a genus and a species epithet, and only a genus abbreviates.
_BINOMIAL_WORDS = 2


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.casefold())


def message_states(message: str, value: str) -> bool:
    """Whether the message carries every word of this value.

    A classifier rewrites what it captures into a canonical value, so the words
    are the test and the phrasing is not. This reads words and not meaning: a
    short value whose words all appear somewhere in the message counts as
    stated.
    """
    carried = set(_words(message))
    stated = _words(value)
    return bool(stated) and all(word in carried for word in stated)


def _genus_abbreviated(value: str) -> str:
    """The binomial with its genus as an initial, as a researcher writes it.

    A one-word name abbreviates to a single letter, which names nothing, so it
    is returned whole.
    """
    words = _words(value)
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


def standing_recommendations(
    questions: Sequence[OpenQuestion], stated: Sequence[Constraint]
) -> list[Constraint]:
    """The recommended values the latest message leaves standing.

    A message that states a value on a dimension replaces every recommendation
    on it, so the ledger never carries two answers to one question.
    """
    replaced = {c.kind for c in stated}
    offered = (q.recommendation() for q in questions)
    return [c for c in offered if c is not None and c.kind not in replaced]


_UNMET = {ConstraintStatus.UNGROUNDABLE, ConstraintStatus.SUBSTITUTED}


def is_blocking(grounded: GroundedConstraint) -> bool:
    return (
        grounded.constraint.source is ConstraintSource.USER_EXPLICIT
        and grounded.constraint.hard
        and grounded.status in _UNMET
    )


def provisional_constraints(constraints: list[Constraint]) -> list[GroundedConstraint]:
    """Wrap constraints as ``provisional``: captured, with no plan yet to
    ground them against. A provisional constraint never blocks, and it is
    surfaced so the user reads what was captured."""

    return [
        GroundedConstraint(constraint=c, status=ConstraintStatus.PROVISIONAL)
        for c in constraints
    ]


def organism_hints_from(requirements: Sequence[Constraint]) -> list[str]:
    """The organisms the requirements state, in the order stated, without repeats."""
    return list(
        dict.fromkeys(
            c.requested_value for c in requirements if c.kind is ConstraintKind.ORGANISM
        )
    )


def combination_requirements_from(
    requirements: Sequence[Constraint],
) -> list[Constraint]:
    """The stated combinations, in the order stated."""
    return [c for c in requirements if c.kind is ConstraintKind.COMBINATION]


_Dimension = tuple[ConstraintKind, str]


def _dimension(c: Constraint) -> _Dimension:
    """What a constraint collapses on.

    A combination names the criteria it is about, so two of them are two
    dimensions; every other kind holds one value per kind.
    """
    if c.kind is ConstraintKind.COMBINATION:
        return (c.kind, c.requested_value)
    return (c.kind, "")


def merge_constraints(
    provisional: list[Constraint], explicit: list[Constraint]
) -> list[Constraint]:
    """Merge the provisional constraints with the ones the thread has stated.

    A stated constraint wins its dimension and keeps the source it was recorded
    with: who stated a value is decided when the thread records it, not here.
    """

    by_dimension: dict[_Dimension, Constraint] = {_dimension(c): c for c in provisional}
    for c in explicit:
        by_dimension[_dimension(c)] = c
    return list(by_dimension.values())


_SHARE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)", re.IGNORECASE)
_TOP_RE = re.compile(r"\btop\b|\bhighest\b", re.IGNORECASE)
_BOTTOM_RE = re.compile(r"\bbottom\b|\blowest\b", re.IGNORECASE)
_FULL_SCALE = 100.0


class PercentileRequest(CamelModel):
    """A share of a ranked population, read from what the user stated."""

    direction: Literal["top", "bottom"]
    share: float

    @classmethod
    def parse(cls, text: str) -> PercentileRequest | None:
        share = _SHARE_RE.search(text)
        if share is None:
            return None
        if _TOP_RE.search(text):
            direction: Literal["top", "bottom"] = "top"
        elif _BOTTOM_RE.search(text):
            direction = "bottom"
        else:
            return None
        return cls(direction=direction, share=float(share.group(1)))

    @property
    def bound(self) -> float:
        """The percentile value that realizes this share."""
        return _FULL_SCALE - self.share if self.direction == "top" else self.share

    def share_of(self, bound: float) -> float:
        return _FULL_SCALE - bound if self.direction == "top" else bound


CombinationOperator = Literal["OR", "AND"]

_SEPARATORS: dict[CombinationOperator, str] = {"OR": " OR ", "AND": " AND "}
_MIN_COMBINATION_TERMS = 2


class CombinationRequest(CamelModel):
    """How the user said their evidence lines combine: one operator over the
    phrases that name the criteria.

    The phrases are the anchor, not criterion ids: a build renumbers the
    criteria on the step ids it mints, and the words survive that.
    """

    operator: CombinationOperator
    terms: list[str] = Field(min_length=_MIN_COMBINATION_TERMS)

    @classmethod
    def parse(cls, text: str) -> CombinationRequest | None:
        """Read one operator over two or more terms, or nothing.

        The operator is an uppercase word between spaces. A string that holds
        both operators states no single combination, so it is unparseable.
        """
        stated: list[CombinationOperator] = [
            operator for operator, separator in _SEPARATORS.items() if separator in text
        ]
        if len(stated) != 1:
            return None
        operator = stated[0]
        terms = [part.strip() for part in text.split(_SEPARATORS[operator])]
        if len(terms) < _MIN_COMBINATION_TERMS or not all(terms):
            return None
        return cls(operator=operator, terms=terms)

    @property
    def expression(self) -> str:
        """The combination as one line, in the user's own words."""
        return _SEPARATORS[self.operator].join(self.terms)


_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_AND_OR_RE = re.compile(r"\band\s*/\s*or\b", re.IGNORECASE)
_UNION_RE = re.compile(r"\bunion\b", re.IGNORECASE)
_INTERSECT_RE = re.compile(r"\bintersect(?:ion|s|ed)?\b", re.IGNORECASE)
_JOINING_WORDS = frozenset({"with", "plus"})
_AS_WELL_AS = "as well as"
_EITHER = "either"
_CLAUSE_BREAK_RE = re.compile(r"[,;:.!?]")

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

    ``named`` is the operator the message names as a set operation.
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
    wanted = _words(term)
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
        return text, _words(text)
    text = message[first.start : second.start]
    own = set(_words(first.term))
    return text, [word for word in _words(text) if word not in own]


def _stated_by(text: str, words: Sequence[str]) -> _Stated:
    if _AND_OR_RE.search(text):
        return "OR"
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
    stated: Sequence[_Stated], default: CombinationOperator
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
    tokens = list(_TOKEN_RE.finditer(message))
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
    opening = [*_words(clause), *_words(spans[0].term)[:1]]
    default: CombinationOperator = "OR" if _EITHER in opening else "AND"
    operators = _resolved([_stated_by(*joined) for joined in between], default)
    return CombinationReading(
        connectives=[
            Connective(before=first.term, after=second.term, text=text, operator=op)
            for (first, second), (text, _), op in zip(
                pairs, between, operators, strict=True
            )
        ],
        named=_named_operator(message),
    )


def combination_operator_is_stated(message: str, request: CombinationRequest) -> bool:
    """Whether the message carries every term and joins them with this operator."""
    reading = read_combination(message, request)
    return reading is not None and reading.states(request.operator)
