"""The two sides the stated-value guard compares, in the catalog's own form.

Every write of a step passes here before the guard reads it, so a value the
catalog rewrites is one string on both sides of the batch.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    StrategyStepNode,
    leaves,
    wdk_search_name,
)
from veupathdb_mcp.catalog import (
    ValidationCallbacks,
    make_validation_callbacks,
    validate_parameters,
)

from pathfinder.domain.strategy.operations import (
    AddLeafOp,
    AddTransformOp,
    GraphOperation,
    ReplaceStrategyOp,
    ReplaceSubtreeOp,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import StatedCriterion


class WrittenStep(NamedTuple):
    """A step a batch writes, and the search that canonicalizes its values."""

    step_id: str
    search: SearchContext
    names_sent: frozenset[str]
    written: Mapping[str, ParamValue]


class CanonicalSides(NamedTuple):
    """The two sides the stated-value guard compares, in the catalog's form.

    ``stated`` holds the spec's values and ``entry`` what a step held before
    the batch, both keyed by step id.
    """

    stated: Mapping[str, StatedCriterion]
    entry: Mapping[str, Mapping[str, ParamValue]]


class CanonicalBatch(NamedTuple):
    """The operations to apply, and the two sides they are measured against."""

    ops: list[GraphOperation]
    sides: CanonicalSides


def _needs_a_second_look(
    criterion: StatedCriterion,
    *,
    held: Mapping[str, ParamValue],
    names_sent: frozenset[str],
) -> bool:
    """Whether the stated values need a canonicalization of their own.

    A step that already holds the stated form needs none, because both sides
    then read the same string.
    """
    for name, value in criterion.values.items():
        carried = held.get(name)
        if name in names_sent or (
            carried is not None and to_wire(carried) != to_wire(value)
        ):
            return True
    return False


def _moves_a_stated_value(
    criterion: StatedCriterion,
    *,
    held: Mapping[str, ParamValue],
    written: Mapping[str, ParamValue],
) -> bool:
    """Whether the batch writes another value where the criterion states one."""
    for name in criterion.values:
        before = held.get(name)
        after = written.get(name)
        if before is None or after is None:
            continue
        if to_wire(before) != to_wire(after):
            return True
    return False


async def _canonical_stated(
    criterion: StatedCriterion,
    *,
    write: WrittenStep,
    held: Mapping[str, ParamValue],
    callbacks: ValidationCallbacks,
) -> StatedCriterion:
    if not _needs_a_second_look(criterion, held=held, names_sent=write.names_sent):
        return criterion
    overlay = await validate_parameters(
        write.search,
        parameters={**held, **criterion.values},
        callbacks=callbacks,
    )
    return StatedCriterion(
        text=criterion.text,
        values={
            name: overlay.params[name]
            for name in criterion.values
            if name in overlay.params
        },
    )


async def _canonical_entry(
    criterion: StatedCriterion,
    *,
    write: WrittenStep,
    held: Mapping[str, ParamValue],
    callbacks: ValidationCallbacks,
) -> Mapping[str, ParamValue]:
    if not _moves_a_stated_value(criterion, held=held, written=write.written):
        return {name: held[name] for name in criterion.values if name in held}
    overlay = await validate_parameters(
        write.search, parameters=dict(held), callbacks=callbacks
    )
    return {
        name: overlay.params[name]
        for name in criterion.values
        if name in overlay.params
    }


async def canonical_sides(
    *,
    graph: StrategyGraph,
    stated: Mapping[str, StatedCriterion],
    writes: Sequence[WrittenStep],
    callbacks: ValidationCallbacks,
) -> CanonicalSides:
    """Both sides of the stated-value guard, in the form the catalog writes.

    A value the batch leaves where it found it needs no catalog read: both
    sides carry the same string. A value the batch writes over is read on the
    entry side too, so a rewritten wire form is not a departure and a
    dependent vocabulary that moves a stated value is one.
    """
    canonical: dict[str, StatedCriterion] = dict(stated)
    entry: dict[str, Mapping[str, ParamValue]] = {}
    for write in writes:
        criterion = stated.get(write.step_id)
        if criterion is None:
            continue
        step = graph.get_step(write.step_id)
        held: Mapping[str, ParamValue] = {} if step is None else step.parameters
        canonical[write.step_id] = await _canonical_stated(
            criterion, write=write, held=held, callbacks=callbacks
        )
        entry[write.step_id] = await _canonical_entry(
            criterion, write=write, held=held, callbacks=callbacks
        )
    return CanonicalSides(stated=canonical, entry=entry)


async def canonicalize_stated_leaves(
    *,
    root: StrategyStepNode,
    stated: Mapping[str, StatedCriterion],
    site_id: str,
    record_type: str,
    callbacks: ValidationCallbacks,
) -> list[WrittenStep]:
    """Put every leaf the spec states a value for in the catalog's own form.

    A written leaf reaches the graph the way a patched step does, so the guard
    reads one form on both sides of the batch.
    """
    writes: list[WrittenStep] = []
    for node in leaves(root):
        if node.id not in stated or node.search_name in ("", COMBINE_SEARCH_NAME):
            continue
        # A leaf that carries no value has none to put in the catalog's form.
        if not node.parameters:
            continue
        search = SearchContext(site_id, record_type, node.search_name)
        validated = await validate_parameters(
            search, parameters=dict(node.parameters), callbacks=callbacks
        )
        node.parameters = dict(validated.params)
        writes.append(
            WrittenStep(
                step_id=node.id,
                search=search,
                names_sent=frozenset(node.parameters),
                written=node.parameters,
            )
        )
    return writes


class _CanonicalOp(NamedTuple):
    op: GraphOperation
    writes: list[WrittenStep]


async def _canonical_params_op(
    op: UpdateStepParamsOp,
    *,
    graph: StrategyGraph,
    site_id: str,
    record_type: str,
    callbacks: ValidationCallbacks,
) -> _CanonicalOp:
    step = graph.get_step(op.step_id)
    if step is None or wdk_search_name(step) in ("", COMBINE_SEARCH_NAME):
        return _CanonicalOp(op=op, writes=[])
    search = SearchContext(site_id, record_type, wdk_search_name(step))
    validated = await validate_parameters(
        search,
        parameters={**step.parameters, **op.parameters},
        callbacks=callbacks,
    )
    return _CanonicalOp(
        op=op.model_copy(update={"parameters": dict(validated.params)}),
        writes=[
            WrittenStep(
                step_id=step.id,
                search=search,
                names_sent=frozenset(op.parameters),
                written=validated.params,
            )
        ],
    )


async def _canonical_tree_op(
    op: AddLeafOp | AddTransformOp | ReplaceSubtreeOp | ReplaceStrategyOp,
    *,
    stated: Mapping[str, StatedCriterion],
    site_id: str,
    record_type: str,
    callbacks: ValidationCallbacks,
) -> _CanonicalOp:
    written = op.model_copy(deep=True)
    match written:
        case ReplaceSubtreeOp():
            root = written.subtree
        case ReplaceStrategyOp():
            root = written.root
        case _:
            root = written.step
    writes = await canonicalize_stated_leaves(
        root=root,
        stated=stated,
        site_id=site_id,
        record_type=record_type,
        callbacks=callbacks,
    )
    return _CanonicalOp(op=written, writes=writes)


async def canonical_batch(
    *,
    graph: StrategyGraph,
    stated: Mapping[str, StatedCriterion],
    site_id: str,
    ops: Sequence[GraphOperation],
) -> CanonicalBatch:
    """The batch in the catalog's form, with the sides the guard reads.

    A step this batch writes carries the values the catalog answers with, so a
    value the batch never moved reads the same before and after it.
    """
    callbacks = make_validation_callbacks(site_id)
    record_type = graph.record_type or "transcript"
    canonical: list[GraphOperation] = []
    writes: list[WrittenStep] = []
    for op in ops:
        match op:
            case UpdateStepParamsOp():
                found = await _canonical_params_op(
                    op,
                    graph=graph,
                    site_id=site_id,
                    record_type=record_type,
                    callbacks=callbacks,
                )
            case (
                AddLeafOp()
                | AddTransformOp()
                | ReplaceSubtreeOp()
                | ReplaceStrategyOp()
            ):
                found = await _canonical_tree_op(
                    op,
                    stated=stated,
                    site_id=site_id,
                    record_type=record_type,
                    callbacks=callbacks,
                )
            case _:
                found = _CanonicalOp(op=op, writes=[])
        canonical.append(found.op)
        writes.extend(found.writes)
    sides = await canonical_sides(
        graph=graph, stated=stated, writes=writes, callbacks=callbacks
    )
    return CanonicalBatch(ops=canonical, sides=sides)
