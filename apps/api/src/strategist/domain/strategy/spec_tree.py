"""The step tree a spec converts to, each step under its criterion's id."""

from __future__ import annotations

from typing import NamedTuple

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    ColocationParams,
    CombineOp,
    StrategyStepNode,
    clone_with_fresh_ids,
)

from strategist.domain.strategy.combine_naming import combine_display_name
from strategist.domain.strategy.combine_order import MIRRORED_OPERATORS, flat_join
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    StructureNode,
)
from strategist.domain.strategy.saved_strategy_ref import SavedStrategyRef
from strategist.domain.strategy.step_naming import criterion_title


class _Operand(NamedTuple):
    """A built combine input, and the saved strategy it stands for."""

    step: StrategyStepNode
    saved: SavedStrategyRef | None


def build_step_tree(spec: OperationalSpec) -> StrategyStepNode:
    if spec.structure is None:
        msg = "spec has no structure"
        raise ValueError(msg)
    by_id = {c.id: c for c in spec.criteria}
    return _node_to_step(spec.structure.root, by_id)


def node_for(criterion: Criterion) -> StrategyStepNode:
    return StrategyStepNode(
        id=criterion.id,
        search_name=criterion.search_name,
        parameters=criterion.step_parameters,
        display_name=criterion_title(criterion).name,
        wdk_weight=criterion.weight,
    )


def _bound_criterion(
    node: StructureNode, by_id: dict[str, Criterion], label: str
) -> Criterion:
    crit = by_id.get(node.named_criterion)
    if crit is None or not crit.bound:
        msg = f"{label} {node.named_criterion!r} is missing or unbound"
        raise ValueError(msg)
    return crit


def _node_to_step(node: StructureNode, by_id: dict[str, Criterion]) -> StrategyStepNode:
    if node.kind == "leaf":
        crit = _bound_criterion(node, by_id, "criterion")
        if crit.saved_strategy_ref is not None:
            saved = clone_with_fresh_ids(crit.saved_strategy_ref.subtree)
            return saved.model_copy(update={"id": crit.id})
        return node_for(crit)
    if node.kind == "transform":
        crit = _bound_criterion(node, by_id, "transform criterion")
        return node_for(crit).model_copy(
            update={"primary_input": _node_to_step(node.inputs[0], by_id)}
        )
    if node.kind == "copy":
        msg = "a copy is stated as criteria of its own before the build"
        raise ValueError(msg)
    operator = node.combine_operator
    combined = _combine(
        _node_to_operand(node.inputs[0], by_id),
        _node_to_operand(node.inputs[1], by_id),
        operator,
        node.colocation_params,
    )
    for extra in node.inputs[2:]:
        combined = _combine(
            combined,
            _node_to_operand(extra, by_id),
            operator,
            node.colocation_params,
        )
    return combined.step


def _node_to_operand(node: StructureNode, by_id: dict[str, Criterion]) -> _Operand:
    """One side of a combine, and the saved strategy it stands for."""
    saved = None
    if node.kind == "leaf":
        crit = by_id.get(node.named_criterion)
        saved = crit.saved_strategy_ref if crit is not None else None
    return _Operand(step=_node_to_step(node, by_id), saved=saved)


def _combine(
    left: _Operand,
    right: _Operand,
    operator: CombineOp,
    colocation: ColocationParams | None,
) -> _Operand:
    """Join two operands, with any saved strategy on the secondary side.

    WDK marks the SECONDARY input of a combine as the collapsed saved
    strategy, so an operand that names one moves there and the operator
    mirrors to keep the question the same.
    """
    if left.saved is None and right.saved is None:
        left, right, operator = flat_join(
            left,
            right,
            operator,
            left_nests=left.step.primary_input is not None,
            right_nests=right.step.primary_input is not None,
        )
    elif left.saved is not None and right.saved is None:
        mirrored = MIRRORED_OPERATORS.get(operator)
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
        colocation_params=colocation,
        display_name=combine_display_name(operator),
        primary_input=left.step,
        secondary_input=right.step,
        expanded_strategy_id=saved.wdk_strategy_id if saved is not None else None,
        expanded_name=saved.name if saved is not None else None,
    )
    return _Operand(step=step, saved=None)
