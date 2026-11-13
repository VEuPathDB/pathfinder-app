from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BeforeValidator, ConfigDict, Discriminator, Field, model_validator
from pydantic.json_schema import SkipJsonSchema
from veupathdb.model import CamelModel

from strategist.domain.log2_scale import Scale


class ConstraintKind(StrEnum):
    DATA_TYPE = "data_type"
    STATISTICAL_THRESHOLD = "statistical_threshold"
    FOLD_CHANGE = "fold_change"
    COMPARATOR = "comparator"
    ORGANISM = "organism"
    RECORD_TYPE = "record_type"
    PERCENTILE = "percentile"
    COMBINATION = "combination"
    COUNT = "count"
    ORTHOLOG = "ortholog"
    TEXT = "text"
    PROPERTY = "property"
    UNTYPED = "untyped"


# Every dimension a constraint can state, as an agent must spell it.
CONSTRAINT_KINDS = ", ".join(kind.value for kind in ConstraintKind)

# The dimensions every search of a strategy runs in. No single search states them.
STRATEGY_SCOPES = frozenset({ConstraintKind.ORGANISM, ConstraintKind.RECORD_TYPE})

# The kinds a thread holds any number of values of. Every other kind holds one
# value, so a new value of it replaces the old one.
MANY_VALUED_KINDS = frozenset(
    {
        ConstraintKind.COMBINATION,
        ConstraintKind.COUNT,
        ConstraintKind.ORTHOLOG,
        ConstraintKind.TEXT,
        ConstraintKind.PROPERTY,
        ConstraintKind.UNTYPED,
    }
)


def _untyped_when_other(kind: object) -> object:
    return ConstraintKind.UNTYPED if kind == "other" else kind


type StoredKind = Annotated[ConstraintKind, BeforeValidator(_untyped_when_other)]


# The record classes a request for genes is answered by: a genomics site's
# transcripts, and OrthoMCL's proteins, the gene level that site holds.
GENE_ANSWERING_CLASSES = frozenset({"transcript", "sequence"})
_ANSWERED_BY: dict[str, frozenset[str]] = {"gene": GENE_ANSWERING_CLASSES}


class ConstraintSource(StrEnum):
    USER_EXPLICIT = "user_explicit"
    ASSUMED = "assumed"


class ConstraintStatus(StrEnum):
    PROVISIONAL = "provisional"
    GROUNDED = "grounded"
    SUBSTITUTED = "substituted"
    UNGROUNDABLE = "ungroundable"
    NOT_VERIFIED = "not_verified"

    @property
    def shown(self) -> str:
        return self.value.replace("_", " ")


def new_requirement_id() -> str:
    return uuid4().hex[:12]


type DataKind = Literal["rna_seq", "microarray"]
type RecordRole = Literal["answer", "through"]
type PercentileEnd = Literal["top", "bottom"]
type FoldDirection = Literal["up", "down", "either"]
type Statistic = Literal["p_value", "adjusted_p", "fdr", "q_value", "unspecified"]
type Share = Annotated[float, Field(gt=0, le=100)]
type Bound = Annotated[float, Field(gt=0, le=1)]
type CountOp = Literal[">=", ">", "<=", "<", "="]
type RangeSide = Literal["lower", "upper"]
type Unverified = Literal["untyped", "no_value_to_compare", "no_step_states_it"]
type _Phrase = Annotated[str, Field(min_length=1)]


class PercentileValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.PERCENTILE] = ConstraintKind.PERCENTILE
    end: PercentileEnd
    share: Share

    @property
    def side(self) -> RangeSide:
        return "lower" if self.end == "top" else "upper"


class FoldChangeValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.FOLD_CHANGE] = ConstraintKind.FOLD_CHANGE
    cut: float | None = None
    scale: Scale = "fold"
    direction: FoldDirection = "either"

    @model_validator(mode="after")
    def _a_fold_is_above_zero(self) -> FoldChangeValue:
        if self.scale == "fold" and self.cut is not None and self.cut <= 0:
            msg = f"a fold cut is above 0, not {self.cut:g}"
            raise ValueError(msg)
        return self


class SignificanceValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.STATISTICAL_THRESHOLD] = (
        ConstraintKind.STATISTICAL_THRESHOLD
    )
    statistic: Statistic = "unspecified"
    at_most: Bound


class DataTypeValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.DATA_TYPE] = ConstraintKind.DATA_TYPE
    data: DataKind


class RecordTypeValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.RECORD_TYPE] = ConstraintKind.RECORD_TYPE
    record_class: str = Field(min_length=1)
    role: RecordRole = "answer"

    @property
    def answering_classes(self) -> frozenset[str]:
        return frozenset({self.record_class}) | _ANSWERED_BY.get(
            self.record_class, frozenset()
        )


class OrganismValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.ORGANISM] = ConstraintKind.ORGANISM
    organism: str = Field(min_length=1)


class CountValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.COUNT] = ConstraintKind.COUNT
    feature: _Phrase
    op: CountOp
    value: float

    def holds(self, number: float) -> bool:
        match self.op:
            case ">=":
                return number >= self.value
            case ">":
                return number > self.value
            case "<=":
                return number <= self.value
            case "<":
                return number < self.value
            case "=":
                return number == self.value

    @property
    def side(self) -> RangeSide | None:
        match self.op:
            case ">=" | ">":
                return "lower"
            case "<=" | "<":
                return "upper"
            case "=":
                return None

    @property
    def shown(self) -> str:
        return f"{self.feature} {self.op} {self.value:g}"


class OrthologValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.ORTHOLOG] = ConstraintKind.ORTHOLOG
    organisms: list[_Phrase] = Field(min_length=1)
    syntenic: bool | None = None


class TextValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.TEXT] = ConstraintKind.TEXT
    phrase: _Phrase
    exact: bool = False


class PropertyValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.PROPERTY] = ConstraintKind.PROPERTY
    phrase: _Phrase


class UntypedValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[ConstraintKind.UNTYPED] = ConstraintKind.UNTYPED
    text: _Phrase


RequirementValue = Annotated[
    PercentileValue
    | FoldChangeValue
    | SignificanceValue
    | DataTypeValue
    | RecordTypeValue
    | OrganismValue
    | CountValue
    | OrthologValue
    | TextValue
    | PropertyValue
    | UntypedValue,
    Discriminator("kind"),
]


def _untyped_other(value: object) -> object:
    match value:
        case {"kind": "other", "requested_value": str(text), **rest}:
            held: dict[object, object] = {**rest, "requested_value": text}
        case {"kind": "other", "requestedValue": str(text), **rest}:
            held = {**rest, "requestedValue": text}
        case _:
            return value
    return {**held, "kind": ConstraintKind.UNTYPED, "value": UntypedValue(text=text)}


class Constraint(CamelModel):
    id: SkipJsonSchema[str] = Field(default_factory=new_requirement_id)
    kind: ConstraintKind
    requested_value: str = Field(min_length=1)
    label: str = Field(min_length=1)
    source: ConstraintSource = ConstraintSource.ASSUMED
    quote: str = ""
    beside: SkipJsonSchema[str] = ""
    hard: bool = True
    """A hard requirement ('RNA-Seq only') blocks if unmet; a soft preference
    ('RNA-Seq preferred, microarray fallback ok') is surfaced but never blocks."""
    value: RequirementValue | None = None

    @model_validator(mode="before")
    @classmethod
    def _an_other_requirement_is_untyped(cls, value: object) -> object:
        return _untyped_other(value)

    @property
    def organism(self) -> str | None:
        match self.value:
            case OrganismValue(organism=organism):
                return organism
            case _:
                return None

    @property
    def side(self) -> RangeSide | None:
        match self.value:
            case CountValue() | PercentileValue() as bounded:
                return bounded.side
            case _:
                return None

    @model_validator(mode="after")
    def _a_value_is_of_the_requirement_s_kind(self) -> Constraint:
        if self.value is not None and self.value.kind != self.kind:
            msg = f"a {self.value.kind} value on a {self.kind} requirement"
            raise ValueError(msg)
        return self


def stored_requirement_id(kind: str, requested_value: str) -> str:
    return sha256(f"{kind}:{requested_value}".encode()).hexdigest()[:12]


def _with_stored_id(value: object) -> object:
    match value:
        case {"kind": str(kind), "requested_value": str(requested), **rest} if (
            "id" not in rest
        ):
            return {
                **rest,
                "kind": kind,
                "requested_value": requested,
                "id": stored_requirement_id(kind, requested),
            }
        case _:
            return value


StoredConstraint = Annotated[Constraint, BeforeValidator(_with_stored_id)]


class OpenLifecycle(CamelModel):
    """A requirement nothing has answered or retired yet."""

    model_config = ConfigDict(frozen=True)

    state: Literal["open"] = "open"


class WithdrawnLifecycle(CamelModel):
    """A requirement a later message of the researcher took back."""

    model_config = ConfigDict(frozen=True)

    state: Literal["withdrawn"] = "withdrawn"
    turn_id: str


class ReplacedLifecycle(CamelModel):
    """A requirement another requirement took the place of.

    ``by`` is the id of the requirement that replaced it.
    """

    model_config = ConfigDict(frozen=True)

    state: Literal["replaced"] = "replaced"
    by: str


Lifecycle = Annotated[
    OpenLifecycle | WithdrawnLifecycle | ReplacedLifecycle,
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
    unverified: Unverified | None = None
    lifecycle: Lifecycle = Field(default_factory=OpenLifecycle)

    @model_validator(mode="after")
    def _a_requirement_not_verified_says_why(self) -> GroundedConstraint:
        if (self.status is ConstraintStatus.NOT_VERIFIED) != (
            self.unverified is not None
        ):
            msg = "a requirement is not verified exactly when it names why"
            raise ValueError(msg)
        return self

    @property
    def retired(self) -> bool:
        """Whether the researcher withdrew the requirement or another replaced it."""
        return self.lifecycle.state in ("withdrawn", "replaced")

    @property
    def answered_by_a_parameter(self) -> bool:
        return self.status is ConstraintStatus.GROUNDED and bool(self.realized_param)


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


_Dimension = tuple[ConstraintKind, str]


def _dimension(c: Constraint) -> _Dimension:
    """What a constraint collapses on: a kind of many values on its typed value,
    or its id when it holds none, and every other kind on the kind alone."""
    if c.kind not in MANY_VALUED_KINDS:
        return (c.kind, "")
    if c.value is None:
        return (c.kind, c.id)
    return (c.kind, c.value.model_dump_json())


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
