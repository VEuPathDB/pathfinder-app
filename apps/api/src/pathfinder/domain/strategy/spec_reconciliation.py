"""Take out of a framed spec the criteria whose steps the strategy lost.

A criterion that reached a step is addressed by that step's id, so a step the
graph lost takes its criterion out of the spec.
"""

from __future__ import annotations

from collections.abc import Collection

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)

__all__ = ["spec_the_strategy_holds", "spec_without_steps"]


def spec_the_strategy_holds(
    spec: OperationalSpec, live_step_ids: Collection[str]
) -> OperationalSpec:
    """The spec without the criteria its structure names and the strategy lacks.

    A criterion the structure leaves out binds an option on another criterion's
    step, so it answers to the strategy like any other.
    """
    return spec_without_steps(
        spec, structure_criteria(spec.structure) - set(live_step_ids)
    )


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
