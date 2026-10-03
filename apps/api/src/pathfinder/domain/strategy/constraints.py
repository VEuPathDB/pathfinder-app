from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Discriminator, Field, model_validator
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.words import FILLER_WORDS, words_of


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

# The dimensions every search of a strategy runs in. No single search states them.
STRATEGY_SCOPES = frozenset({ConstraintKind.ORGANISM, ConstraintKind.RECORD_TYPE})


# The nouns every site counts a gene answer in.
GENE_RECORD_NOUNS = frozenset({"gene", "genes", "transcript", "transcripts"})
# The words a record-type phrase adds to the noun it names.
_RECORD_QUALIFIERS = frozenset({"record", "records", "level", "data", "type", "types"})


def record_noun(text: str) -> str:
    """The words of the text, less the words that only say it names a record type."""
    words = re.findall(r"[a-z0-9]+", text.casefold())
    return " ".join(word for word in words if word not in _RECORD_QUALIFIERS)


def qualifies_a_record_noun(text: str) -> bool:
    """Whether the text adds a content word to a gene record noun, as a gene
    type does. Such a text names a value of the record, not a record class."""
    words = record_noun(text).split()
    return bool(GENE_RECORD_NOUNS.intersection(words)) and any(
        word not in GENE_RECORD_NOUNS and word not in FILLER_WORDS for word in words
    )


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

    @model_validator(mode="after")
    def _a_value_of_a_record_is_no_record_type(self) -> Constraint:
        """A record type that qualifies a record noun states a value of it."""
        if self.kind is ConstraintKind.RECORD_TYPE and qualifies_a_record_noun(
            self.requested_value
        ):
            self.kind = ConstraintKind.OTHER
        return self

    @property
    def key(self) -> str:
        """The identity of the requirement: its dimension and the value it states."""
        return f"{self.kind.value}:{self.requested_value}"


class OpenLifecycle(CamelModel):
    """A requirement nothing has answered or retired yet."""

    model_config = ConfigDict(frozen=True)

    state: Literal["open"] = "open"


class BoundLifecycle(CamelModel):
    """A requirement a criterion's values state."""

    model_config = ConfigDict(frozen=True)

    state: Literal["bound"] = "bound"
    criterion_id: str
    params: list[str] = Field(default_factory=list)


class WithdrawnLifecycle(CamelModel):
    """A requirement a later message of the researcher took back."""

    model_config = ConfigDict(frozen=True)

    state: Literal["withdrawn"] = "withdrawn"
    turn_id: str


class ReplacedLifecycle(CamelModel):
    """A requirement another requirement took the place of.

    ``by`` is the key of the requirement that replaced it.
    """

    model_config = ConfigDict(frozen=True)

    state: Literal["replaced"] = "replaced"
    by: str


Lifecycle = Annotated[
    OpenLifecycle | BoundLifecycle | WithdrawnLifecycle | ReplacedLifecycle,
    Discriminator("state"),
]


class GroundedConstraint(CamelModel):
    constraint: Constraint
    status: ConstraintStatus
    realized_value: str | None = None
    # The parameter the value was read from, empty when the grounding read no
    # single parameter.
    realized_param: str = ""
    note: str = ""
    lifecycle: Lifecycle = Field(default_factory=OpenLifecycle)

    @property
    def retired(self) -> bool:
        """Whether the researcher withdrew the requirement or another replaced it."""
        return self.lifecycle.state in ("withdrawn", "replaced")


def message_states(message: str, value: str) -> bool:
    """Whether the message carries every word of this value.

    A classifier rewrites what it captures into a canonical value, so the words
    are the test and the phrasing is not. This reads words and not meaning: a
    short value whose words all appear somewhere in the message counts as
    stated.
    """
    carried = set(words_of(message))
    stated = words_of(value)
    return bool(stated) and all(word in carried for word in stated)


def content_words(value: str) -> frozenset[str]:
    """The words of the value that are not filler."""
    return frozenset(word for word in words_of(value) if word not in FILLER_WORDS)


def states_the_content(text: str, value: str) -> bool:
    """Whether the text carries every word of the value that is not filler."""
    wanted = content_words(value)
    return bool(wanted) and wanted <= set(words_of(text))


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


_Dimension = tuple[ConstraintKind, str | frozenset[str]]


def _dimension(c: Constraint) -> _Dimension:
    """What a constraint collapses on: a combination on its value, an other
    value on its non-filler words, and every other kind on the kind alone."""
    if c.kind is ConstraintKind.COMBINATION:
        return (c.kind, c.requested_value)
    if c.kind is ConstraintKind.OTHER:
        return (c.kind, content_words(c.requested_value))
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
_ORDINAL_RE = re.compile(r"(\d+(?:\.\d+)?)(?:st|nd|rd|th)\s+percentile", re.IGNORECASE)
_TOP_RE = re.compile(r"\btop\b|\bhighest\b", re.IGNORECASE)
_BOTTOM_RE = re.compile(r"\bbottom\b|\blowest\b", re.IGNORECASE)
# A percentile named as a cut is a lower bound unless the text puts the genes
# below it.
_BELOW_RE = re.compile(r"\bbelow\b|\bunder\b|\bat most\b", re.IGNORECASE)
# A percentile named by one number and the end it bounds: "minimum
# percentile 1", "percentile 75 or above", "80 or higher".
_PERCENTILE_WORD_RE = re.compile(r"\bpercentile\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_UPPER_RE = re.compile(
    r"\bmax(?:imum)?\b|\bat most\b|\bor (?:lower|below)\b", re.IGNORECASE
)
_LOWER_RE = re.compile(
    r"\bmin(?:imum)?\b|\bat least\b|\bor (?:higher|above)\b", re.IGNORECASE
)
_FULL_SCALE = 100.0


class PercentileRequest(CamelModel):
    """A share of a ranked population, read from what the user stated."""

    direction: Literal["top", "bottom"]
    share: float

    @classmethod
    def parse(cls, text: str) -> PercentileRequest | None:
        """A share with its end ("top 5 percent"), or the percentile that
        bounds it ("95th percentile", "below the 10th percentile", "minimum
        percentile 1")."""
        ordinal = _ORDINAL_RE.search(text)
        if ordinal is not None:
            bound = float(ordinal.group(1))
            if _BOTTOM_RE.search(text) or _BELOW_RE.search(text):
                return cls(direction="bottom", share=bound)
            return cls(direction="top", share=_FULL_SCALE - bound)
        share = _SHARE_RE.search(text)
        numbers = _NUMBER_RE.findall(text)
        if share is None and _PERCENTILE_WORD_RE.search(text) and len(numbers) == 1:
            return cls._bounded_at(float(numbers[0]), text)
        if share is None:
            return None
        if _TOP_RE.search(text):
            direction: Literal["top", "bottom"] = "top"
        elif _BOTTOM_RE.search(text):
            direction = "bottom"
        else:
            return None
        return cls(direction=direction, share=float(share.group(1)))

    @classmethod
    def _bounded_at(cls, bound: float, text: str) -> PercentileRequest | None:
        """The share a named bound keeps, or None when the text names no end."""
        if _UPPER_RE.search(text):
            return cls(direction="bottom", share=bound)
        if _LOWER_RE.search(text):
            return cls(direction="top", share=_FULL_SCALE - bound)
        return None

    @property
    def bound(self) -> float:
        """The percentile value that realizes this share."""
        return _FULL_SCALE - self.share if self.direction == "top" else self.share

    def share_of(self, bound: float) -> float:
        return _FULL_SCALE - bound if self.direction == "top" else bound


CombinationOperator = Literal["OR", "AND"]

_SEPARATORS: dict[CombinationOperator, str] = {"OR": " OR ", "AND": " AND "}
# The operator each separator states. MINUS states a subtraction, which no
# single combination operator holds.
_STATED_BY: dict[str, CombinationOperator | None] = {
    "OR": "OR",
    "AND": "AND",
    "UNION": "OR",
    "INTERSECT": "AND",
    "MINUS": None,
}
# An uppercase OR or AND, or an operator word in any case, between spaces.
_SEPARATOR_RE = re.compile(r" (OR|AND) | ((?i:UNION|INTERSECT|MINUS)) ")
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

        The operator is an uppercase OR or AND, or UNION, INTERSECT or MINUS in
        any case, between spaces. A string that states two operators, or a
        subtraction, states no single combination, so it is unparseable.
        """
        parts = _SEPARATOR_RE.split(text)
        words = [
            (upper or other).upper()
            for upper, other in zip(parts[1::3], parts[2::3], strict=True)
        ]
        stated: set[CombinationOperator | None] = {_STATED_BY[word] for word in words}
        if len(stated) != 1:
            return None
        [operator] = stated
        terms = [part.strip() for part in parts[::3]]
        if operator is None or not all(terms):
            return None
        return cls(operator=operator, terms=terms)

    @property
    def expression(self) -> str:
        """The combination as one line, in the user's own words."""
        return _SEPARATORS[self.operator].join(self.terms)
