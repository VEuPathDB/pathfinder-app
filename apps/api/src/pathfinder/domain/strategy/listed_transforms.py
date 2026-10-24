from __future__ import annotations

from collections.abc import Iterator, Mapping

from pathfinder.domain.strategy.operational_spec import OperationalSpec, StructureNode
from pathfinder.domain.strategy.record_class_check import SearchRecordClasses
from pathfinder.domain.strategy.structure_reading import record_class_at


def _nodes(node: StructureNode) -> Iterator[StructureNode]:
    yield node
    for child in node.inputs:
        yield from _nodes(child)


def listed_transform_ids(
    spec: OperationalSpec, transforms: Mapping[str, SearchRecordClasses]
) -> frozenset[str]:
    if spec.structure is None:
        return frozenset()
    by_id = {criterion.id: criterion for criterion in spec.criteria}
    classes = {criterion.id: criterion.record_class for criterion in spec.criteria}
    return frozenset(
        node.named_criterion
        for node in _nodes(spec.structure.root)
        if node.kind == "transform"
        and node.named_criterion in by_id
        and (listed := transforms.get(by_id[node.named_criterion].search_name))
        is not None
        and record_class_at(node.inputs, classes) in listed.takes
    )


__all__ = ["listed_transform_ids"]
