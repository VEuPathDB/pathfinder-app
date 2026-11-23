from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep, subtree_ids

from strategist.domain.strategy.operational_spec import (
    OperationalSpec,
    StructureNode,
    criteria_under,
)
from strategist.domain.strategy.session import StrategyGraph

__all__ = ["spec_with_the_regions_it_runs"]


def _stated(
    node: StructureNode, steps: Mapping[str, StrategyStep], criteria: frozenset[str]
) -> StructureNode:
    inputs = [_stated(child, steps, criteria) for child in node.inputs]
    region = None
    if node.operator is CombineOp.COLOCATE and node.colocation_params is None:
        under = criteria_under(node)
        held = next(
            (
                step.colocation_params
                for step in steps.values()
                if step.kind is StepKind.COMBINE
                and step.operator is CombineOp.COLOCATE
                and frozenset(subtree_ids(step.id, dict(steps))) & criteria == under
            ),
            None,
        )
        region = node.region(held)
    return node.model_copy(
        update={
            "inputs": inputs,
            "colocation_params": region or node.colocation_params,
        }
    )


def spec_with_the_regions_it_runs(
    spec: OperationalSpec, graph: StrategyGraph | None
) -> OperationalSpec:
    if spec.structure is None:
        return spec
    criteria = frozenset(c.id for c in spec.criteria)
    steps = {} if graph is None else graph.steps
    root = _stated(spec.structure.root, steps, criteria)
    return spec.model_copy(
        update={"structure": spec.structure.model_copy(update={"root": root})}
    )
