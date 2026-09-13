"""Bring a framed spec back to the strategy the graph holds now.

A criterion that reached a step is addressed by that step's id, so a step the
graph lost takes its criterion out of the spec.
"""

from __future__ import annotations

import re
from collections.abc import Collection

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph

__all__ = ["spec_reconciled_with_graph", "spec_without_steps"]

_MINTED_STEP_ID = re.compile(r"^step_[0-9a-f]{8}$")


def spec_reconciled_with_graph(
    spec: OperationalSpec,
    graph: StrategyGraph,
    *,
    recorded_step_ids: Collection[str],
) -> OperationalSpec:
    """The spec without the criteria whose steps the graph no longer holds.

    ``recorded_step_ids`` are the steps the last recorded build held, which is
    every id that answered to a step whatever minted it. A spec derived from a
    strategy no build recorded has none, and there the minter's own id shape is
    the address of a step. A criterion in neither set never reached a step, and
    it stays.
    """
    departed = {
        criterion.id
        for criterion in spec.criteria
        if criterion.id not in graph.steps
        and (
            criterion.id in recorded_step_ids
            or _MINTED_STEP_ID.match(criterion.id) is not None
        )
    }
    return spec_without_steps(spec, departed)


def spec_without_steps(
    spec: OperationalSpec, departed: Collection[str]
) -> OperationalSpec:
    """The spec without these criteria, and without what their loss orphans.

    A combine left with one input is that input, and a transform whose own
    criterion left is its input. A criterion the pruned structure no longer
    names leaves the spec with it.
    """
    gone = set(departed)
    if not gone:
        return spec
    structure = _structure_without(spec.structure, gone)
    lost = gone | (structure_criteria(spec.structure) - structure_criteria(structure))
    reconciled = spec.model_copy(deep=True)
    reconciled.criteria = [c for c in reconciled.criteria if c.id not in lost]
    reconciled.open_slots = [
        slot for slot in reconciled.open_slots if slot.criterion_id not in lost
    ]
    reconciled.structure = structure
    return reconciled


def _structure_without(
    structure: SpecStructure | None, departed: set[str]
) -> SpecStructure | None:
    if structure is None:
        return None
    root = _node_without(structure.root, departed)
    return None if root is None else SpecStructure(root=root)


def _node_without(node: StructureNode, departed: set[str]) -> StructureNode | None:
    """The node with the departed criteria gone from it.

    A combine left with one input is that input, and a combine left with none
    is nothing. A transform is its input when its own criterion left, and
    nothing when the input left.
    """
    inputs = [
        kept
        for child in node.inputs
        if (kept := _node_without(child, departed)) is not None
    ]
    if node.kind == "combine":
        if len(inputs) > 1:
            return node.model_copy(update={"inputs": inputs})
        return inputs[0] if inputs else None
    if node.criterion_id in departed:
        return inputs[0] if inputs else None
    if node.kind == "transform" and not inputs:
        return None
    return node.model_copy(update={"inputs": inputs})
