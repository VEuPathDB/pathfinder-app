from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from veupathdb.domain.parameters import ParamValue, UnboundParameter
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyStepNode,
)
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraints import Constraint
from pathfinder.domain.strategy.step_rationale import (
    AnalysisRationale,
    SearchRationale,
    StepRationale,
)

CriterionRole = Literal["seed", "filter", "transform", "exclude"]
MIN_COMBINE_INPUTS = 2


class OpenSlot(UnboundParameter):
    """An unbound parameter, and the criterion of this spec that holds it.

    ``criterion_id`` is empty while the slot names a parameter alone, and holds
    the criterion once the slot is attached to one.
    """

    criterion_id: str = ""


class AssumedValue(CamelModel):
    """A value the model chose that the criterion text does not state.

    It is reported as a constraint so the user reads it and can override it.
    """

    param_name: str
    value: str
    reason: str
    # The option criterion a fold absorbed to place this value. Empty while the
    # value is one FRAME chose at bind time.
    carried_from: str = ""


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


class StructureNode(CamelModel):
    kind: Literal["leaf", "combine", "transform"]
    criterion_id: str | None = None
    operator: CombineOp | None = None
    inputs: list[StructureNode] = Field(default_factory=list)


class SpecStructure(CamelModel):
    root: StructureNode


def criteria_under(node: StructureNode) -> frozenset[str]:
    """The criteria this subtree names.

    A leaf and a transform each name one; a combine names none of its own.
    """
    own = (
        frozenset({node.criterion_id})
        if node.kind != "combine" and node.criterion_id
        else frozenset[str]()
    )
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
    resolved_params: dict[str, ParamValue] = Field(default_factory=dict)
    # Params holding the search default rather than a value the request states.
    # Reported to the user, because a default is a safe choice and a silent one.
    defaulted_params: list[str] = Field(default_factory=list)
    open_params: list[OpenSlot] = Field(default_factory=list)
    confidence: float = 0.0
    assumptions: list[AssumedValue] = Field(default_factory=list)
    # The choices inside a criterion that matches no record. Empty otherwise.
    alternatives: list[ParameterAlternatives] = Field(default_factory=list)
    # The exported analysis this criterion is, once the EDA tools bound it.
    analysis: AnalysisBinding | None = None
    # The dataset whose analysis workflow realizes this criterion, while it waits.
    needs_analysis_on: str | None = None
    # Why the criterion runs its search, recorded when FRAME binds it.
    rationale: SearchRationale | None = None

    @property
    def bound(self) -> bool:
        return bool(self.search_name) or self.saved_strategy_ref is not None

    @property
    def pending_analysis(self) -> bool:
        """Whether the criterion waits for the analysis workflow to realize it."""
        return self.needs_analysis_on is not None

    @property
    def step_parameters(self) -> dict[str, ParamValue]:
        """The parameters the criterion's step carries."""
        if self.analysis is not None:
            return dict(self.analysis.step_parameters)
        return dict(self.resolved_params)

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
    own = {node.criterion_id} if node.kind != "combine" and node.criterion_id else set()
    for child in node.inputs:
        own |= _named_by(child)
    return own
