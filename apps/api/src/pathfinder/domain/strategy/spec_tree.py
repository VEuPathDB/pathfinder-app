"""The step tree a spec converts to, and the spec re-keyed on the steps it built."""

from __future__ import annotations

from typing import NamedTuple

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    clone_with_fresh_ids,
)

from pathfinder.domain.strategy.combine_naming import combine_display_name
from pathfinder.domain.strategy.operational_spec import (
    MIN_COMBINE_INPUTS,
    Criterion,
    OperationalSpec,
    SavedStrategyRef,
    StructureNode,
)

# Swapping a combine's operands mirrors the operator that is not symmetric.
_MIRRORED_OPERATORS = {
    CombineOp.INTERSECT: CombineOp.INTERSECT,
    CombineOp.UNION: CombineOp.UNION,
    CombineOp.MINUS: CombineOp.RMINUS,
    CombineOp.RMINUS: CombineOp.MINUS,
    CombineOp.LONLY: CombineOp.RONLY,
    CombineOp.RONLY: CombineOp.LONLY,
}


class _Operand(NamedTuple):
    """A built combine input, and the saved strategy it stands for."""

    step: StrategyStepNode
    saved: SavedStrategyRef | None


class SpecTree(NamedTuple):
    """The tree a spec converts to, and the step each criterion became."""

    root: StrategyStepNode
    step_id_by_criterion: dict[str, str]


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
            parameters=crit.step_parameters,
            display_name=crit.title,
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
            parameters=crit.step_parameters,
            display_name=crit.title,
            primary_input=_node_to_step(node.inputs[0], by_id, minted),
        )
        minted[crit.id] = step.id
        return step
    # Combining n criteria takes n-1 nodes. A spec that emits one per criterion
    # carries a spare with nothing to combine against, and one operand is that
    # operand.
    if len(node.inputs) == 1:
        return _node_to_step(node.inputs[0], by_id, minted)
    if node.operator is None or len(node.inputs) < MIN_COMBINE_INPUTS:
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
        display_name=combine_display_name(operator),
        primary_input=left.step,
        secondary_input=right.step,
        expanded_strategy_id=saved.wdk_strategy_id if saved is not None else None,
        expanded_name=saved.name if saved is not None else None,
    )
    return _Operand(step=step, saved=None)
