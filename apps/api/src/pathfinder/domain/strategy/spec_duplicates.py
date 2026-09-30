"""The duplicate fold: an INTERSECT input identical to a sibling input of its
chain returns the sibling's records, so it leaves the structure."""

from __future__ import annotations

import json
from collections.abc import Collection, Iterator

from pydantic import ConfigDict
from veupathdb.domain.parameters import to_wire
from veupathdb.domain.strategy import CombineOp
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
    criteria_under,
)


class DuplicateDrop(CamelModel):
    """An INTERSECT input the duplicate fold removed; the sibling that runs the
    same search with the same values meets its text."""

    model_config = ConfigDict(frozen=True)

    criterion_id: str
    text: str
    search_name: str
    sibling_id: str

    @property
    def met(self) -> bool:
        return True

    @property
    def requirement(self) -> None:
        """The sibling meets the text, so the drop holds no requirement open."""

    @property
    def fate(self) -> str:
        return (
            f"{self.criterion_id} ('{self.text}') is dropped: it runs "
            f"{self.search_name} with the values {self.sibling_id} runs beside it "
            f"under INTERSECT, so {self.sibling_id} meets it."
        )


class DeduplicatedStructure(CamelModel):
    """The structure the duplicate fold left, and the inputs it dropped."""

    model_config = ConfigDict(frozen=True)

    structure: SpecStructure
    dropped: tuple[DuplicateDrop, ...] = ()


def _intersects(node: StructureNode) -> bool:
    return node.kind == "combine" and node.operator is CombineOp.INTERSECT


def _operands(node: StructureNode) -> Iterator[StructureNode]:
    """The inputs one INTERSECT chain joins, however its combines nest."""
    if not _intersects(node):
        yield node
        return
    for child in node.inputs:
        yield from _operands(child)


def _named_in_order(node: StructureNode) -> list[str]:
    """The criteria of a subtree in tree order, copies included."""
    own = [node.criterion_id] if node.kind != "combine" and node.criterion_id else []
    return own + [cid for child in node.inputs for cid in _named_in_order(child)]


class _DuplicateReading:
    """What the duplicate fold compares each INTERSECT input by."""

    def __init__(self, spec: OperationalSpec, live_step_ids: Collection[str]) -> None:
        self.by_id = {c.id: c for c in spec.criteria}
        self.live = frozenset(live_step_ids)
        self.dropped: list[DuplicateDrop] = []

    def shape(self, node: StructureNode) -> list[object]:
        """The subtree as its operators, searches and wire values, never its ids.

        A criterion whose values are not all decided answers only for itself.
        """
        if node.kind == "copy":
            return self.shape(node.inputs[0]) if node.inputs else ["copy"]
        below = [self.shape(child) for child in node.inputs]
        if node.kind == "combine":
            return ["combine", node.operator.value if node.operator else "", below]
        c = self.by_id.get(node.criterion_id or "")
        if c is None or not c.search_name or c.open_params or c.analysis is not None:
            return ["criterion", node.criterion_id or ""]
        values = {name: to_wire(value) for name, value in c.param_values.items()}
        return [node.kind, c.search_name, values, below]

    def folded(self, node: StructureNode) -> StructureNode:
        if not _intersects(node):
            inputs = [self.folded(child) for child in node.inputs]
            return node.model_copy(update={"inputs": inputs})
        groups: dict[str, list[StructureNode]] = {}
        for operand in _operands(node):
            key = json.dumps(self.shape(operand), sort_keys=True)
            groups.setdefault(key, []).append(operand)
        redundant: set[int] = set()
        for same in groups.values():
            keeper = next((o for o in same if self._live(o)), same[0])
            for other in same:
                if other is not keeper:
                    redundant.add(id(other))
                    self._record(other, keeper)
        kept = self._without(node, redundant)
        if kept is None:
            msg = "an INTERSECT chain keeps the input its duplicates fold into"
            raise ValueError(msg)
        return kept

    def _live(self, node: StructureNode) -> bool:
        named = _named_in_order(node)
        return bool(named) and self.live.issuperset(named)

    def _record(self, dropped: StructureNode, keeper: StructureNode) -> None:
        pairs = zip(_named_in_order(dropped), _named_in_order(keeper), strict=True)
        for criterion_id, sibling_id in pairs:
            c = self.by_id[criterion_id]
            self.dropped.append(
                DuplicateDrop(
                    criterion_id=criterion_id,
                    text=c.text,
                    search_name=c.search_name,
                    sibling_id=sibling_id,
                )
            )

    def _without(
        self, node: StructureNode, redundant: set[int]
    ) -> StructureNode | None:
        if not _intersects(node):
            return None if id(node) in redundant else self.folded(node)
        kept = [
            joined
            for child in node.inputs
            if (joined := self._without(child, redundant)) is not None
        ]
        if len(kept) <= 1:
            return kept[0] if kept else None
        return node.model_copy(update={"inputs": kept})


def fold_duplicate_inputs(
    spec: OperationalSpec, tree: SpecStructure, *, live_step_ids: Collection[str]
) -> DeduplicatedStructure:
    """Drop each INTERSECT input identical to a sibling input of its chain.

    Identical is the same shape, operators, searches and values. The input
    kept is the first whose criteria are all live steps, else the first.
    """
    reading = _DuplicateReading(spec, live_step_ids)
    root = reading.folded(tree.root)
    if not reading.dropped and root == tree.root:
        return DeduplicatedStructure(structure=tree)
    remaining = criteria_under(root)
    return DeduplicatedStructure(
        structure=SpecStructure(root=root),
        dropped=tuple(d for d in reading.dropped if d.criterion_id not in remaining),
    )
