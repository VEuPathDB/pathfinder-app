from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from veupathdb.domain.parameters import (
    ParamKind,
    ParamValue,
    UnboundParameter,
)
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyStepNode,
)
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraints import Constraint
from pathfinder.domain.strategy.named_taxa import NamedTaxon
from pathfinder.domain.strategy.number_precision import rounded_number
from pathfinder.domain.strategy.step_rationale import (
    AnalysisRationale,
    ChosenRationale,
    StepRationale,
)
from pathfinder.domain.strategy.words import names_a_run_of

CriterionRole = Literal["seed", "filter", "transform", "exclude"]
MIN_COMBINE_INPUTS = 2


class OpenSlot(UnboundParameter):
    """An unbound parameter, and the criterion of this spec that holds it.

    ``criterion_id`` is empty while the slot names a parameter alone, and holds
    the criterion once the slot is attached to one. ``param_kind`` is the kind
    of value the parameter takes, as its sheet gives it.
    """

    criterion_id: str = ""
    param_kind: ParamKind = "string"


ValueSource = Literal["stated", "chosen", "default", "card", "held"]


class BoundValue(CamelModel):
    """A bound value, who set it, and what the published sheet says of it.
    ``basis`` is the request's words, the model's reason or the card's option
    id; a default and a held value have none. No sheet read, no sheet fields."""

    model_config = ConfigDict(frozen=True)

    value: ParamValue
    source: ValueSource
    basis: str = ""
    # The option criterion a fold carried this value from, empty otherwise.
    carried_from: str = ""
    display_name: str = ""
    # The vocabulary's label of a pick, a filter field or a species code.
    label: str = ""
    # The value is the site's prompt in an empty box: it states nothing.
    placeholder: bool = False
    # The value is the initial value the site publishes for the parameter.
    at_default: bool = False
    # The sheet shows the parameter, or its vocabulary offers more than one
    # entry. A hidden parameter with no choice still rides the step.
    visible: bool = True
    # The sheet reads the parameter as a number or a pick of terms.
    number: bool = False
    # The decimal places the sheet's initial value shows, None for no number.
    decimals: int | None = None
    # The taxon a message names whose organisms the pick takes, else None.
    taxon: NamedTaxon | None = None

    @property
    def unset(self) -> bool:
        """Whether the value states nothing the site does not already send."""
        return self.placeholder or self.at_default

    def rounded(self) -> str | None:
        """The value at the precision of its sheet, or None for a value that is
        no number or that the researcher stated, which shows as written."""
        if not self.number or self.source == "stated":
            return None
        return rounded_number(self.value.to_wire(), self.decimals)

    def carried(self, criterion_id: str) -> BoundValue:
        """The value as a fold carries it from the option criterion."""
        return self.model_copy(update={"carried_from": criterion_id})

    def sourced(
        self,
        source: ValueSource,
        basis: str = "",
        taxon: NamedTaxon | None = None,
    ) -> BoundValue:
        """The value with who set it decided, and the words that decided it."""
        return self.model_copy(
            update={"source": source, "basis": basis, "taxon": taxon}
        )


CountedKind = Literal[
    "loosest_bound",
    "wildcard_phrase",
    "phrase_reading",
    "words_reading",
    "site_search_reach",
    "any_strain",
    "all_strains",
    "site_default",
    "bound_count",
]
MeasurementKind = Literal[
    CountedKind,
    "vocabulary_label",
    "options_not_taken",
    "not_measurable",
    "picked_from_a_cut_list",
    "picked_from_a_lookup",
    "label_without_the_concept",
]


class Measurement(CamelModel):
    """A count the site returned for another reading of one bound value, a
    label, the options a pick did not take, or why the value has no reading.

    ``reading`` is that other reading as the reply may show it, or for
    ``not_measurable`` the reason. ``count`` is None for a reading the site
    answers as words and for a reading whose count did not arrive.
    ``unchosen`` lists the labels of the options not taken while the
    vocabulary is small enough to list; ``unchosen_count`` counts them always.
    """

    model_config = ConfigDict(frozen=True)

    kind: MeasurementKind
    param: str
    count: int | None = None
    label: str = ""
    reading: str = ""
    unchosen: list[str] = Field(default_factory=list)
    unchosen_count: int = 0


class ParameterAlternatives(CamelModel):
    """A vocabulary parameter of a binding, and the values it did not take."""

    param_name: str
    bound: list[str]
    option_count: int
    # Empty when the vocabulary is too large to list, or when a bound term
    # stands for options it is not listed among.
    other_options: list[str] = Field(default_factory=list)


class DroppedCriterion(CamelModel):
    """A criterion with no realizable WDK search. It is surfaced, never dropped."""

    text: str
    reason: str
    # The EDA dataset a drop recorded before a criterion could wait for its
    # analysis. The turn entry restates it as such a criterion.
    eda_dataset_id: str | None = None
    # The researcher's requirement the dropped text restated, which stays open.
    # It is a gap while no criterion of the spec states its value.
    requirement: Constraint | None = None


class UnexpressedText(CamelModel):
    """A text the request states that no search of the spec states.

    ``criterion_id`` is the criterion that holds it; once a drop holds it,
    ``criterion_id`` is None and ``requirement`` is the requirement held open.
    """

    model_config = ConfigDict(frozen=True)

    word: str
    criterion_id: str | None
    stated_in: str
    why: str
    requirement: Constraint | None = None


_NODE_SHAPES = {
    "leaf": (
        'a leaf is {"kind": "leaf", "criterionId": "<id>"}: one bound criterion, '
        "with no inputs and no operator."
    ),
    "combine": (
        'a combine is {"kind": "combine", "operator": "INTERSECT" | "UNION" | '
        '"MINUS", "inputs": [<left>, <right>]}: an operator over two or more '
        "subtrees, with no criterionId. A tree of one criterion is that "
        "criterion's leaf; with no criterion left, there is no tree to set."
    ),
    "transform": (
        'a transform is {"kind": "transform", "criterionId": "<id>", "inputs": '
        "[<subtree>]}: one criterion that maps exactly one input subtree, with no "
        "operator."
    ),
    "copy": (
        'a copy is {"kind": "copy", "inputs": [<subtree>]}: exactly one subtree '
        "the tree already states, with no criterionId and no operator."
    ),
}


class _SpareWrapper(BaseModel):
    """A raw combine node of exactly one input."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    kind: Literal["combine"]
    inputs: Annotated[list[object], Field(min_length=1, max_length=1)]


class StructureNode(CamelModel):
    """One node of the stated tree.

    A copy restates the subtree it holds, which the tree states elsewhere, and
    is stated as criteria of its own before anything builds it.
    """

    kind: Literal["leaf", "combine", "transform", "copy"]
    criterion_id: str | None = None
    operator: CombineOp | None = None
    inputs: list[StructureNode] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _a_spare_wrapper_is_its_input(cls, data: object) -> object:
        """A combine of one input combines nothing, so it is that input."""
        try:
            wrapper = _SpareWrapper.model_validate(data)
        except ValidationError:
            return data
        return cls.model_validate(wrapper.inputs[0]).model_dump(by_alias=True)

    @model_validator(mode="after")
    def _in_the_shape_of_its_kind(self) -> StructureNode:
        named = self.criterion_id is not None
        joined = self.operator is not None
        count = len(self.inputs)
        fits = {
            "leaf": named and not joined and count == 0,
            "combine": joined and not named and count >= MIN_COMBINE_INPUTS,
            "transform": named and not joined and count == 1,
            "copy": not named and not joined and count == 1,
        }[self.kind]
        if not fits:
            raise ValueError(_NODE_SHAPES[self.kind])
        return self

    @property
    def combine_operator(self) -> CombineOp:
        """The operator of a combine. Only a copy that skips validation has none."""
        if self.operator is None:
            raise ValueError(_NODE_SHAPES[self.kind])
        return self.operator

    @property
    def named_criterion(self) -> str:
        """The criterion a leaf or a transform runs."""
        if self.criterion_id is None:
            raise ValueError(_NODE_SHAPES[self.kind])
        return self.criterion_id


class SpecStructure(CamelModel):
    root: StructureNode


def criteria_under(node: StructureNode) -> frozenset[str]:
    """The criteria this subtree names.

    A leaf and a transform each name one; a combine and a copy name none of
    their own.
    """
    own = frozenset({node.criterion_id}) if node.criterion_id else frozenset[str]()
    return own.union(*(criteria_under(child) for child in node.inputs))


class SavedStrategyRef(CamelModel):
    """A saved strategy the user reuses as the input of a criterion.

    ``subtree`` is the saved strategy's steps, cloned with fresh ids, so the
    build pushes steps of its own instead of borrowing the saved strategy's.
    """

    conversation_id: str
    name: str
    wdk_strategy_id: int
    root_count: int | None = None
    step_count: int = 0
    subtree: StrategyStepNode

    @property
    def label(self) -> str:
        """The saved strategy named with the size it brings."""
        size = f"{self.step_count} steps"
        if self.root_count is not None:
            size = f"{self.root_count} results, {size}"
        return f"saved strategy {self.name!r} ({size})"


class Criterion(CamelModel):
    id: str
    text: str
    search_name: str = ""
    # The search's name on the site, which is what its step is titled.
    search_display_name: str | None = None
    # Set instead of ``search_name`` when the criterion reuses a saved strategy.
    saved_strategy_ref: SavedStrategyRef | None = None
    role: CriterionRole = "filter"
    # The parameter WDK marks as the search's organism, None when it marks none.
    organism_param: str | None = None
    resolved_params: dict[str, BoundValue] = Field(default_factory=dict)
    # The name the site shows each bound parameter by, read when it binds.
    param_display_names: dict[str, str] = Field(default_factory=dict)
    # The counts the site returned for other readings of the bound values.
    measurements: list[Measurement] = Field(default_factory=list)
    open_params: list[OpenSlot] = Field(default_factory=list)
    confidence: float = 0.0
    # The choices inside a criterion that matches no record. Empty otherwise.
    alternatives: list[ParameterAlternatives] = Field(default_factory=list)
    # The records the binding matched when it was bound. None when no count
    # arrived, and whenever a value changes after the count.
    result_count: int | None = None
    # The exported analysis this criterion is, once the EDA tools bound it.
    analysis: AnalysisBinding | None = None
    # The dataset whose analysis workflow realizes this criterion, while it waits.
    needs_analysis_on: str | None = None
    # Why the criterion runs its search: FRAME's choice when it binds it, or
    # the controls a separation measured it against.
    rationale: ChosenRationale | None = None
    # Words of the text that narrow it and that no search the binding pass read
    # can state. Each is reported unmet until a search states it.
    unexpressed_qualifiers: list[str] = Field(default_factory=list)

    @property
    def bound(self) -> bool:
        return bool(self.search_name) or self.saved_strategy_ref is not None

    @property
    def pending_analysis(self) -> bool:
        """Whether the criterion waits for the analysis workflow to realize it."""
        return self.needs_analysis_on is not None

    @property
    def param_values(self) -> dict[str, ParamValue]:
        """The bound values, without who set them."""
        return {name: bound.value for name, bound in self.resolved_params.items()}

    @property
    def shown_values(self) -> dict[str, BoundValue]:
        """The bound values whose parameter the site shows, by parameter name."""
        return {
            name: bound for name, bound in self.resolved_params.items() if bound.visible
        }

    def set_by(self, source: ValueSource) -> dict[str, BoundValue]:
        """The bound values this source set, by parameter name."""
        return {
            name: bound
            for name, bound in self.resolved_params.items()
            if bound.source == source
        }

    def display_name_of(self, param: str) -> str:
        """The name the site shows the parameter by, else the parameter's own."""
        held = self.resolved_params.get(param)
        if held is not None and held.display_name:
            return held.display_name
        return self.param_display_names.get(param, param)

    def defaulted(self) -> list[str]:
        """The params holding the site default, sorted by name."""
        return sorted(self.set_by("default"))

    @property
    def step_parameters(self) -> dict[str, ParamValue]:
        """The parameters the criterion's step carries."""
        if self.analysis is not None:
            return dict(self.analysis.step_parameters)
        return self.param_values

    @property
    def title(self) -> str:
        """The name the step carries: what runs, else the researcher's words."""
        return self.search_display_name or self.text[:60]

    @property
    def step_rationale(self) -> StepRationale | None:
        """Why the step runs what it runs: its analysis, else the search choice."""
        if self.analysis is not None:
            return AnalysisRationale.of(self.analysis)
        return self.rationale

    def counted_at(self, count: int | None) -> Criterion:
        """The criterion with a bind count that did not arrive replaced by the
        count its built step holds, which counts the same values."""
        if self.result_count is not None or count is None:
            return self
        return self.model_copy(
            update={
                "result_count": count,
                "measurements": [
                    m.model_copy(update={"count": count})
                    if m.kind == "bound_count" and m.count is None
                    else m
                    for m in self.measurements
                ],
            }
        )


class OperationalSpec(CamelModel):
    goal: str = ""
    interpreted_goal: str = ""
    record_type: str = "transcript"
    organism_scope: str | None = None
    title: str = ""
    criteria: list[Criterion] = Field(default_factory=list)
    structure: SpecStructure | None = None
    dropped: list[DroppedCriterion] = Field(default_factory=list)
    open_slots: list[OpenSlot] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_criterion_per_id(self) -> OperationalSpec:
        """A criterion id addresses one criterion, and one step once it is built."""
        ids = [c.id for c in self.criteria]
        repeated = sorted({cid for cid in ids if ids.count(cid) > 1})
        if repeated:
            msg = f"the spec names criteria {repeated} more than once"
            raise ValueError(msg)
        return self

    def unexpressed(self) -> list[UnexpressedText]:
        """Every text no search states: each criterion's own words, then each
        requirement a drop holds open that no criterion of the spec states."""
        held = [
            UnexpressedText(
                word=word,
                criterion_id=c.id,
                stated_in=c.text,
                why=(
                    f"{c.title} cannot state '{word}', and no search the "
                    f"framing pass read has a parameter that does"
                ),
            )
            for c in self.criteria
            for word in c.unexpressed_qualifiers
        ]
        dropped = [
            UnexpressedText(
                word=kept.requested_value,
                criterion_id=None,
                stated_in=kept.label,
                why=d.reason,
                requirement=kept,
            )
            for d in self.dropped
            if (kept := d.requirement) is not None
            and not any(
                names_a_run_of(c.text, kept.requested_value) for c in self.criteria
            )
        ]
        return [*held, *dropped]

    def counted_at(self, step_counts: Mapping[str, int | None]) -> OperationalSpec:
        """The spec with each criterion whose bind count did not arrive counted
        at its built step's count."""
        return self.model_copy(
            update={
                "criteria": [c.counted_at(step_counts.get(c.id)) for c in self.criteria]
            }
        )

    @property
    def ready_to_build(self) -> bool:
        """Whether a build has criteria to mint; one awaiting its analysis waits."""
        built = [c for c in self.criteria if not c.pending_analysis]
        if not built or self.structure is None or self.open_slots:
            return False
        return all(c.bound and not c.open_params for c in built)


def pending_analyses(spec: OperationalSpec | None) -> list[Criterion]:
    """Every criterion waiting for the Lead's EDA tools, in spec order."""
    if spec is None:
        return []
    return [criterion for criterion in spec.criteria if criterion.pending_analysis]


def structure_criteria(structure: SpecStructure | None) -> frozenset[str]:
    """The criterion ids a structure states a step for."""
    if structure is None:
        return frozenset()
    return frozenset(_named_by(structure.root))


def _named_by(node: StructureNode) -> set[str]:
    own = {node.criterion_id} if node.criterion_id else set()
    for child in node.inputs:
        own |= _named_by(child)
    return own
