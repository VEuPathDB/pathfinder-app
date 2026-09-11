"""The two invariants every write to a strategy holds.

The steps that run a search are exactly the criteria that answer to a step:
none is adopted from outside, none is stranded, and no step carries a
placeholder name.
A write into an input slot never takes the step that slot holds off the tree.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from veupathdb.domain.strategy.graph_model import StepKind, StrategyStep
from veupathdb.domain.strategy.tree import subtree_ids, walk

from pathfinder.domain.strategy.operational_spec import SpecStructure, criteria_under
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph

__all__ = [
    "SlotWrite",
    "StatedShape",
    "criteria_with_steps",
    "evicted_by",
    "overwritten_slot",
    "placeholder_names",
    "shape_after",
    "stated_shape",
    "structure_criteria",
    "working_copy",
]

_SENTINEL_MARK = "__"
_SHORTEST_SENTINEL = 5


def criteria_with_steps(
    criteria: Collection[str],
    live_step_ids: Collection[str],
    *,
    minted: Collection[str] = (),
) -> frozenset[str]:
    """The criteria that answer to a step of their own after the edit.

    A criterion answers to a step the strategy already holds, or to one the
    edit mints for it. A criterion in neither set binds an option on another
    criterion's search, so the step carrying that search states it.
    """
    answered = set(live_step_ids) | set(minted)
    return frozenset(cid for cid in criteria if cid in answered)


def structure_criteria(structure: SpecStructure | None) -> frozenset[str]:
    """The criterion ids a structure states a step for."""
    if structure is None:
        return frozenset()
    return criteria_under(structure.root)


@dataclass(frozen=True)
class StatedShape:
    """How a graph departs from the criteria a spec states."""

    root_id: str
    live_root_id: str | None
    stated: tuple[str, ...]
    searches: tuple[str, ...]
    adopted: tuple[str, ...]
    lost: tuple[str, ...]
    unstated: tuple[str, ...]
    stranded: tuple[str, ...]

    @property
    def roots_elsewhere(self) -> bool:
        return self.root_id != self.live_root_id

    @property
    def holds(self) -> bool:
        return not (
            self.roots_elsewhere
            or self.adopted
            or self.lost
            or self.unstated
            or self.stranded
        )


def stated_shape(
    *,
    graph: StrategyGraph,
    root_id: str,
    criteria: Collection[str],
    outside: Collection[str],
) -> StatedShape:
    """Measure the graph under ``root_id`` against the criteria the spec states.

    ``outside`` are the steps the strategy did not reach before the change.
    They stay where they are: the change neither adopts nor strands them.
    """
    reachable = set(subtree_ids(root_id, graph.steps))
    stated = set(criteria)
    searches = _steps_a_criterion_answers(reachable, graph, stated)
    return StatedShape(
        root_id=root_id,
        live_root_id=graph.primary_root_id(),
        stated=tuple(sorted(stated)),
        searches=tuple(sorted(searches)),
        adopted=tuple(sorted(reachable & set(outside))),
        lost=tuple(sorted(stated - searches)),
        unstated=tuple(sorted(searches - stated)),
        stranded=tuple(sorted(set(graph.steps) - reachable - set(outside))),
    )


def _steps_a_criterion_answers(
    reachable: set[str], graph: StrategyGraph, stated: set[str]
) -> set[str]:
    """The reachable steps a criterion addresses.

    A criterion that states a step holding no other stated step addresses that
    whole subtree, which is how an expanded saved strategy answers for the one
    criterion that names it.
    """
    references = {
        sid
        for sid in reachable & stated
        if not (set(subtree_ids(sid, graph.steps)) - {sid}) & stated
    }
    inside = {
        sid
        for reference in references
        for sid in subtree_ids(reference, graph.steps)
        if sid != reference
    }
    return {
        sid
        for sid in reachable - inside
        if sid in references or graph.steps[sid].kind is not StepKind.COMBINE
    }


@dataclass(frozen=True)
class SlotWrite:
    """The step an operation overwrites in one input slot."""

    target_step_id: str
    slot: str
    occupant_step_id: str


def overwritten_slot(graph: StrategyGraph, op: GraphOperation) -> SlotWrite | None:
    """The step this operation is about to overwrite in an input slot."""
    if op.kind == "addLeaf":
        attach = op.attach
        if attach.mode == "into-slot":
            return _held(graph.get_step(attach.target_step_id), attach.slot)
        return None
    if op.kind == "wireInput":
        return _held(graph.get_step(op.target_step_id), op.slot)
    return None


def _held(target: StrategyStep | None, slot: str) -> SlotWrite | None:
    if target is None:
        return None
    occupant = (
        target.primary_input_id if slot == "primary" else target.secondary_input_id
    )
    if occupant is None:
        return None
    return SlotWrite(target_step_id=target.id, slot=slot, occupant_step_id=occupant)


def evicted_by(
    graph: StrategyGraph,
    writes: Sequence[SlotWrite],
    *,
    was_reachable: Collection[str],
) -> SlotWrite | None:
    """The first write whose overwritten step is now off the tree and undeleted.

    A step that leaves the tree without a delete is lost with no record of the
    loss, so the write that overwrote its slot is refused instead.
    """
    reachable = set(subtree_ids(graph.primary_root_id() or "", graph.steps))
    for write in writes:
        occupant = write.occupant_step_id
        if (
            occupant in was_reachable
            and occupant in graph.steps
            and occupant not in reachable
        ):
            return write
    return None


def shape_after(
    op: GraphOperation,
    *,
    graph: StrategyGraph,
    criteria: Collection[str],
) -> StatedShape:
    """The shape the graph takes once ``op`` applies, measured on a copy.

    The root is read after the operation, so re-rooting the tree at its own
    root is no departure. ``criteria`` is every criterion the spec states; the
    shape holds the ones that answer to a step once the operation applies.
    """
    entry_root = graph.primary_root_id() or ""
    outside = set(graph.steps) - set(subtree_ids(entry_root, graph.steps))
    planned = working_copy(graph)
    apply_operation(planned, op)
    return stated_shape(
        graph=planned,
        root_id=planned.primary_root_id() or "",
        criteria=criteria_with_steps(
            criteria, graph.steps, minted=set(planned.steps) - set(graph.steps)
        ),
        outside=outside,
    )


def working_copy(graph: StrategyGraph) -> StrategyGraph:
    """A graph an operation can apply to without touching the session's own."""
    clone = StrategyGraph(graph_id=graph.id, name=graph.name, site_id=graph.site_id)
    clone.record_type = graph.record_type
    clone.description = graph.description
    clone.steps = {sid: step.model_copy(deep=True) for sid, step in graph.steps.items()}
    clone.recompute_roots()
    clone.last_step_id = graph.last_step_id
    return clone


def placeholder_names(root: StrategyStepNode) -> tuple[str, ...]:
    """The sentinel search names a step tree carries, besides the combine one.

    A WDK search name never takes the ``__name__`` form, so a step that carries
    one holds a placeholder from the payload instead of a search.
    """
    found = {node.search_name for node in walk(root) if _is_sentinel(node.search_name)}
    return tuple(sorted(found))


def _is_sentinel(name: str) -> bool:
    if name == COMBINE_SEARCH_NAME:
        return False
    return (
        name.startswith(_SENTINEL_MARK)
        and name.endswith(_SENTINEL_MARK)
        and len(name) >= _SHORTEST_SENTINEL
    )
