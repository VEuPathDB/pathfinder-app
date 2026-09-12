from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Literal

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
    """Merge the provisional constraints with the ones the user states.

    The explicit set wins per dimension and takes ``user_explicit``: a value
    the user states is explicit whatever the caller tagged it.
    """

    by_dimension: dict[_Dimension, Constraint] = {_dimension(c): c for c in provisional}
    for c in explicit:
        by_dimension[_dimension(c)] = c.model_copy(
            update={"source": ConstraintSource.USER_EXPLICIT}
        )
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
