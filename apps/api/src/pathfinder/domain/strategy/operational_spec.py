from __future__ import annotations

from typing import Literal, NamedTuple

from pydantic import ConfigDict, Field
from veupathdb.domain.parameters import ParamValue, UnboundParameter, to_wire
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    clone_with_fresh_ids,
)
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.constraints import Constraint

CriterionRole = Literal["seed", "filter", "transform", "exclude"]
_MIN_COMBINE_INPUTS = 2

# Swapping a combine's operands mirrors the operator that is not symmetric.
_MIRRORED_OPERATORS = {
    CombineOp.INTERSECT: CombineOp.INTERSECT,
    CombineOp.UNION: CombineOp.UNION,
    CombineOp.MINUS: CombineOp.RMINUS,
    CombineOp.RMINUS: CombineOp.MINUS,
    CombineOp.LONLY: CombineOp.RONLY,
    CombineOp.RONLY: CombineOp.LONLY,
}


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
    # The EDA dataset the criterion is realized from, when its search is
    # EDA-backed. The Lead builds those with its EDA tools.
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

    @property
    def bound(self) -> bool:
        return bool(self.search_name) or self.saved_strategy_ref is not None


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

    @property
    def ready_to_build(self) -> bool:
        if not self.criteria or self.structure is None or self.open_slots:
            return False
        return all(c.bound and not c.open_params for c in self.criteria)


class _Operand(NamedTuple):
    """A built combine input, and the saved strategy it stands for."""

    step: StrategyStepNode
    saved: SavedStrategyRef | None


class SpecTree(NamedTuple):
    """The tree a spec converts to, and the step each criterion became."""

    root: StrategyStepNode
    step_id_by_criterion: dict[str, str]


def eda_backed_drops(spec: OperationalSpec | None) -> list[DroppedCriterion]:
    """Every dropped criterion the Lead's EDA tools realize, in drop order."""
    if spec is None:
        return []
    return [dropped for dropped in spec.dropped if dropped.eda_dataset_id]


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


class FoldedSpec(CamelModel):
    """The spec the fold produced, and the options it could not place."""

    model_config = ConfigDict(frozen=True)

    spec: OperationalSpec
    unplaced: tuple[str, ...] = ()


def fold_option_criteria(spec: OperationalSpec) -> FoldedSpec:
    """Move an option onto the step that runs its search.

    A criterion the structure leaves out states its values on the criterion that
    names the same search; one no single criterion carries is reported unplaced.
    """
    named = structure_criteria(spec.structure)
    if all(c.id in named for c in spec.criteria):
        return FoldedSpec(spec=spec)
    folded = spec.model_copy(deep=True)
    carriers = [c for c in folded.criteria if c.id in named]
    absorbed: set[str] = set()
    unplaced: list[str] = []
    for option in folded.criteria:
        if option.id in named or not option.search_name or option.open_params:
            continue
        runs_it = [c for c in carriers if c.search_name == option.search_name]
        if len(runs_it) != 1 or not _carry_the_option(runs_it[0], option):
            unplaced.append(option.id)
            continue
        absorbed.add(option.id)
    if not absorbed:
        return FoldedSpec(spec=spec, unplaced=tuple(unplaced))
    folded.criteria = [c for c in folded.criteria if c.id not in absorbed]
    return FoldedSpec(spec=folded, unplaced=tuple(unplaced))


def carried_values(carrier: Criterion) -> dict[str, str]:
    """The wire values a fold has already carried onto this criterion."""
    return {a.param_name: a.value for a in carrier.assumptions if a.carried_from}


def _carry_the_option(carrier: Criterion, option: Criterion) -> bool:
    """Give the carrier the values the option states, and report that it can.

    A value the option defaulted or the carrier's own text states does not
    move, and a value contradicting one the fold carried moves nothing at all.
    """
    carried = carried_values(carrier)
    assumed = {a.param_name for a in carrier.assumptions if not a.carried_from}
    defaulted = set(option.defaulted_params)
    stated: dict[str, ParamValue] = {}
    for name, value in option.resolved_params.items():
        if name in defaulted:
            continue
        if name in carried:
            if carried[name] != to_wire(value):
                return False
            continue
        held = name in carrier.resolved_params and name not in carrier.defaulted_params
        if held and name not in assumed:
            continue
        stated[name] = value
    carrier.resolved_params.update(stated)
    carrier.defaulted_params = sorted(set(carrier.defaulted_params) - set(stated))
    # The option replaces the assumption it overrides, so one value has one
    # reason on the ledger.
    carrier.assumptions = [
        *(a for a in carrier.assumptions if a.param_name not in stated),
        *(
            AssumedValue(
                param_name=name,
                value=to_wire(value),
                reason=option.text,
                carried_from=option.id,
            )
            for name, value in stated.items()
        ),
    ]
    return True


def build_step_tree(spec: OperationalSpec) -> SpecTree:
    """Convert the spec and report the step id it minted for each criterion."""
    if spec.structure is None:
        msg = "spec has no structure"
        raise ValueError(msg)
    by_id = {c.id: c for c in spec.criteria}
    minted: dict[str, str] = {}
    return SpecTree(
        root=_node_to_step(spec.structure.root, by_id, minted),
        step_id_by_criterion=minted,
    )


def renumber_criteria(
    spec: OperationalSpec, step_id_by_criterion: dict[str, str]
) -> OperationalSpec:
    """Re-key the spec on the step ids a build produced.

    A criterion and the step it built are then the same address, so a later
    edit changes that step rather than rebuilding the strategy around it.
    """
    renumbered = spec.model_copy(deep=True)
    for criterion in renumbered.criteria:
        criterion.id = step_id_by_criterion.get(criterion.id, criterion.id)
    for slot in renumbered.open_slots:
        slot.criterion_id = step_id_by_criterion.get(
            slot.criterion_id, slot.criterion_id
        )
    if renumbered.structure is not None:
        _renumber_structure(renumbered.structure.root, step_id_by_criterion)
    return renumbered


def _renumber_structure(node: StructureNode, mapping: dict[str, str]) -> None:
    if node.criterion_id is not None:
        node.criterion_id = mapping.get(node.criterion_id, node.criterion_id)
    for child in node.inputs:
        _renumber_structure(child, mapping)


def _bound_criterion(
    node: StructureNode, by_id: dict[str, Criterion], label: str
) -> Criterion:
    crit = by_id.get(node.criterion_id or "")
    if crit is None or not crit.bound:
        msg = f"{label} {node.criterion_id!r} is missing or unbound"
        raise ValueError(msg)
    return crit


def _node_to_step(
    node: StructureNode, by_id: dict[str, Criterion], minted: dict[str, str]
) -> StrategyStepNode:
    if node.kind == "leaf":
        crit = _bound_criterion(node, by_id, "criterion")
        if crit.saved_strategy_ref is not None:
            saved_step = clone_with_fresh_ids(crit.saved_strategy_ref.subtree)
            minted[crit.id] = saved_step.id
            return saved_step
        step = StrategyStepNode(
            search_name=crit.search_name,
            parameters=dict(crit.resolved_params),
            display_name=crit.text[:60],
        )
        minted[crit.id] = step.id
        return step
    if node.kind == "transform":
        crit = _bound_criterion(node, by_id, "transform criterion")
        if not node.inputs:
            msg = f"transform criterion {node.criterion_id!r} has no input step"
            raise ValueError(msg)
        step = StrategyStepNode(
            search_name=crit.search_name,
            parameters=dict(crit.resolved_params),
            display_name=crit.text[:60],
            primary_input=_node_to_step(node.inputs[0], by_id, minted),
        )
        minted[crit.id] = step.id
        return step
    # Combining n criteria takes n-1 nodes. A spec that emits one per criterion
    # carries a spare with nothing to combine against, and one operand is that
    # operand.
    if len(node.inputs) == 1:
        return _node_to_step(node.inputs[0], by_id, minted)
    if node.operator is None or len(node.inputs) < _MIN_COMBINE_INPUTS:
        msg = "combine node needs an operator and at least two inputs"
        raise ValueError(msg)
    combined = _combine(
        _node_to_operand(node.inputs[0], by_id, minted),
        _node_to_operand(node.inputs[1], by_id, minted),
        node.operator,
    )
    for extra in node.inputs[2:]:
        combined = _combine(
            combined, _node_to_operand(extra, by_id, minted), node.operator
        )
    return combined.step


def _node_to_operand(
    node: StructureNode, by_id: dict[str, Criterion], minted: dict[str, str]
) -> _Operand:
    """One side of a combine, and the saved strategy it stands for."""
    saved = None
    if node.kind == "leaf":
        crit = by_id.get(node.criterion_id or "")
        saved = crit.saved_strategy_ref if crit is not None else None
    return _Operand(step=_node_to_step(node, by_id, minted), saved=saved)


def _combine(left: _Operand, right: _Operand, operator: CombineOp) -> _Operand:
    """Join two operands, with any saved strategy on the secondary side.

    WDK marks the SECONDARY input of a combine as the collapsed saved
    strategy, so an operand that names one moves there and the operator
    mirrors to keep the question the same.
    """
    if left.saved is not None and right.saved is None:
        mirrored = _MIRRORED_OPERATORS.get(operator)
        if mirrored is None:
            msg = (
                f"{operator.value} cannot take a saved strategy on its left "
                f"input; put the saved strategy on the right"
            )
            raise ValueError(msg)
        left, right, operator = right, left, mirrored
    saved = right.saved
    step = StrategyStepNode(
        search_name=COMBINE_SEARCH_NAME,
        operator=operator,
        primary_input=left.step,
        secondary_input=right.step,
        expanded_strategy_id=saved.wdk_strategy_id if saved is not None else None,
        expanded_name=saved.name if saved is not None else None,
    )
    return _Operand(step=step, saved=None)
