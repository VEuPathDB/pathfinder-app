"""The two sides the stated-value guard compares, in the catalog's own form.

Every write of a step passes here before the guard reads it, so a value the
catalog rewrites is one string on both sides of the batch.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import NamedTuple

from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    StepValidation,
    StrategyStepNode,
    leaves,
    wdk_search_name,
)
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import (
    ValidationCallbacks,
    make_validation_callbacks,
    validate_parameters,
)

from strategist.domain.strategy.operations import (
    AddLeafOp,
    AddTransformOp,
    GraphOperation,
    ReplaceStrategyOp,
    ReplaceSubtreeOp,
    UpdateStepParamsOp,
)
from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.spec_edit_guard import StatedCriterion
from strategist.services.strategies.record_classes import search_record_types
from strategist.services.strategies.step_search import (
    names_a_wdk_question,
    states_a_question,
)

NO_VERDICTS: Mapping[str, StepValidation] = MappingProxyType({})


class WrittenStep(NamedTuple):
    """A step a batch writes, and the search that canonicalizes its values."""

    step_id: str
    search: SearchContext
    names_sent: frozenset[str]
    written: Mapping[str, ParamValue]


class CanonicalSides(NamedTuple):
    """The two sides the stated-value guard compares, in the catalog's form.

    ``stated`` holds the spec's values, ``entry`` what a step held before the
    batch and ``written`` what the catalog makes of each step the batch writes,
    all keyed by step id.
    """

    stated: Mapping[str, StatedCriterion]
    entry: Mapping[str, Mapping[str, ParamValue]]
    written: Mapping[str, Mapping[str, ParamValue]]


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
        if name in names_sent or (carried is not None and carried != value):
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
        if before != after:
            return True
    return False


async def _canonical_stated(
    criterion: StatedCriterion,
    *,
    write: WrittenStep,
    held: Mapping[str, ParamValue],
    callbacks: ValidationCallbacks,
) -> StatedCriterion:
    """The stated values in the catalog's form, read under the whole binding.

    A step the batch adds holds nothing before it, so the binding the batch
    writes is the only context a dependent parameter can be read under. A value
    the catalog refuses keeps its own form: only the edit's statement refuses.
    """
    if not _needs_a_second_look(criterion, held=held, names_sent=write.names_sent):
        return criterion
    try:
        overlay = await validate_parameters(
            write.search,
            stated=dict(criterion.values),
            context=write.written,
            callbacks=callbacks,
            about=None,
        )
    except ValidationError:
        return criterion
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
    entry = {name: held[name] for name in criterion.values if name in held}
    if not _moves_a_stated_value(criterion, held=held, written=write.written):
        return entry
    try:
        overlay = await validate_parameters(
            write.search, stated=entry, context=held, callbacks=callbacks, about=None
        )
    except ValidationError:
        return entry
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
    return CanonicalSides(
        stated=canonical,
        entry=entry,
        written={write.step_id: write.written for write in writes},
    )


async def canonicalize_stated_leaves(
    *,
    graph: StrategyGraph,
    root: StrategyStepNode,
    stated: Mapping[str, StatedCriterion],
    site_id: str,
    callbacks: ValidationCallbacks,
) -> list[WrittenStep]:
    """Put every leaf the spec states a value for in the catalog's own form.

    A written leaf reaches the graph the way a patched step does, so the guard
    reads one form on both sides of the batch.
    """
    writes: list[WrittenStep] = []
    stated_leaves = [node for node in leaves(root) if node.id in stated]
    listed = await search_record_types(site_id, [n.search_name for n in stated_leaves])
    for node in stated_leaves:
        if not states_a_question(node.search_name):
            continue
        held = graph.get_step(node.id)
        context = unmoved(node.parameters, {} if held is None else held.parameters)
        stated_now = {
            name: value
            for name, value in node.parameters.items()
            if name not in context
        }
        node.parameters = {**node.parameters, **context}
        if not stated_now:
            continue
        search = SearchContext(
            site_id, listed.get(node.search_name, ""), node.search_name
        )
        validated = await validate_parameters(
            search, stated=stated_now, context=context, callbacks=callbacks, about=None
        )
        node.parameters = {**context, **validated.params}
        writes.append(
            WrittenStep(
                step_id=node.id,
                search=search,
                names_sent=frozenset(stated_now),
                written=node.parameters,
            )
        )
    return writes


def unmoved(
    values: Mapping[str, ParamValue], held: Mapping[str, ParamValue]
) -> dict[str, ParamValue]:
    """The values a node carries that the step already holds, in the held form."""
    return {
        name: held[name]
        for name, value in values.items()
        if name in held and held[name] == value
    }


class _CanonicalOp(NamedTuple):
    op: GraphOperation
    writes: list[WrittenStep]


async def _canonical_params_op(
    op: UpdateStepParamsOp,
    *,
    graph: StrategyGraph,
    validations: Mapping[str, StepValidation],
    site_id: str,
    callbacks: ValidationCallbacks,
) -> _CanonicalOp:
    step = graph.get_step(op.step_id)
    if step is None or not names_a_wdk_question(step):
        return _CanonicalOp(op=op, writes=[])
    name = wdk_search_name(step)
    listed = await search_record_types(site_id, [name])
    search = SearchContext(site_id, step.record_class or listed.get(name, ""), name)
    validated = await validate_parameters(
        search,
        stated=dict(op.parameters),
        context=step.parameters,
        held_validation=validations.get(step.id),
        callbacks=callbacks,
        about=None,
    )
    return _CanonicalOp(
        op=op.model_copy(
            update={
                "parameters": {
                    name: validated.params[name]
                    for name in op.parameters
                    if name in validated.params
                }
            }
        ),
        writes=[
            WrittenStep(
                step_id=step.id,
                search=search,
                names_sent=frozenset(op.parameters),
                written={**step.parameters, **validated.params},
            )
        ],
    )


async def _canonical_tree_op(
    op: AddLeafOp | AddTransformOp | ReplaceSubtreeOp | ReplaceStrategyOp,
    *,
    graph: StrategyGraph,
    stated: Mapping[str, StatedCriterion],
    site_id: str,
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
        graph=graph,
        root=root,
        stated=stated,
        site_id=site_id,
        callbacks=callbacks,
    )
    return _CanonicalOp(op=written, writes=writes)


async def canonical_batch(
    *,
    graph: StrategyGraph,
    stated: Mapping[str, StatedCriterion],
    site_id: str,
    ops: Sequence[GraphOperation],
    validations: Mapping[str, StepValidation] = NO_VERDICTS,
) -> CanonicalBatch:
    """The batch in the catalog's form, with the sides the guard reads.

    A step this batch writes carries the values the catalog answers with, so a
    value the batch never moved reads the same before and after it.
    """
    callbacks = make_validation_callbacks(site_id)
    canonical: list[GraphOperation] = []
    writes: list[WrittenStep] = []
    for op in ops:
        match op:
            case UpdateStepParamsOp():
                found = await _canonical_params_op(
                    op,
                    graph=graph,
                    validations=validations,
                    site_id=site_id,
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
                    graph=graph,
                    stated=stated,
                    site_id=site_id,
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
