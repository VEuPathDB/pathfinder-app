from __future__ import annotations

from typing import NamedTuple

from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

from pathfinder.domain.strategy.operations import (
    GraphOperation,
    UpdateCombineOperatorOp,
    WireInputOp,
)
from pathfinder.domain.strategy.session import StrategyGraph

__all__ = ["MIRRORED_OPERATORS", "Join", "flat_join", "wired_in_place"]

MIRRORED_OPERATORS = {
    CombineOp.INTERSECT: CombineOp.INTERSECT,
    CombineOp.UNION: CombineOp.UNION,
    CombineOp.MINUS: CombineOp.RMINUS,
    CombineOp.RMINUS: CombineOp.MINUS,
    CombineOp.LONLY: CombineOp.RONLY,
    CombineOp.RONLY: CombineOp.LONLY,
}


class Join[T](NamedTuple):
    primary: T
    secondary: T
    operator: CombineOp


def flat_join[T](
    left: T,
    right: T,
    operator: CombineOp,
    *,
    left_nests: bool,
    right_nests: bool,
) -> Join[T]:
    mirrored = MIRRORED_OPERATORS.get(operator)
    if left_nests or not right_nests or mirrored is None:
        return Join(left, right, operator)
    return Join(right, left, mirrored)


def wired_in_place(
    graph: StrategyGraph,
    consumer: tuple[StrategyStep, str] | None,
    group_id: str,
) -> list[GraphOperation]:
    if consumer is None:
        return []
    parent, slot = consumer
    wire = WireInputOp(
        target_step_id=parent.id,
        slot="primary" if slot == "primary" else "secondary",
        source_step_id=group_id,
    )
    beside = parent.primary_input_id
    if (
        wire.slot == "primary"
        or beside is None
        or parent.kind is not StepKind.COMBINE
        or parent.operator is None
        or parent.expanded_strategy_id is not None
        or parent.filters
    ):
        return [wire]
    join = flat_join(
        beside,
        group_id,
        parent.operator,
        left_nests=graph.steps[beside].primary_input_id is not None,
        right_nests=True,
    )
    if join.primary == beside:
        return [wire]
    ops: list[GraphOperation] = [
        WireInputOp(target_step_id=parent.id, slot="primary", source_step_id=group_id),
        WireInputOp(target_step_id=parent.id, slot="secondary", source_step_id=beside),
    ]
    if join.operator is not parent.operator:
        ops.append(UpdateCombineOperatorOp(step_id=parent.id, operator=join.operator))
    return ops
