"""How a per-step edit is measured against the spec the strategy realizes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.domain.strategy import StrategyStepNode, leaves
from veupathdb_mcp.catalog import ValidationCallbacks, validate_parameters

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.operations import ReplaceSubtreeOp
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import (
    StatedCriterion,
    spec_stated_values,
)
from pathfinder.domain.strategy.stated_shape import StatedShape, shape_after


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
    deps: AgentDeps,
    *,
    graph: StrategyGraph,
    writes: Sequence[WrittenStep],
    callbacks: ValidationCallbacks,
) -> CanonicalSides:
    """Both sides of the stated-value guard, in the form the catalog writes.

    A value the batch leaves where it found it needs no catalog read: both
    sides carry the same string. A value the batch writes over is read on the
    entry side too, so a rewritten wire form is not a departure and a
    dependent vocabulary that moves a stated value is one.
    """
    stated = spec_stated_values(deps.agent_state.operational_spec_draft)
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
    deps: AgentDeps,
    *,
    subtree: StrategyStepNode,
    record_type: str,
    callbacks: ValidationCallbacks,
) -> list[WrittenStep]:
    """Put every leaf the spec states a value for in the catalog's own form.

    A written leaf reaches the graph the way a patched step does, so the guard
    reads one form on both sides of the batch.
    """
    stated = spec_stated_values(deps.agent_state.operational_spec_draft)
    writes: list[WrittenStep] = []
    for node in leaves(subtree):
        if node.id not in stated:
            continue
        search = SearchContext(deps.site_id, record_type, node.search_name)
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


def refuse_a_write_the_spec_did_not_state(
    deps: AgentDeps, graph: StrategyGraph, op: ReplaceSubtreeOp
) -> None:
    """The write leaves the strategy holding the criteria the spec states.

    The spec addresses this graph by step id, so a criterion that answers to no
    step of it, before or after the write, states nothing about it.
    """
    spec = deps.agent_state.operational_spec_draft
    shape = shape_after(op, graph=graph, criteria=[c.id for c in spec.criteria])
    if not shape.stated or shape.holds:
        return
    criteria = {c.id: c for c in spec.criteria if c.id in shape.stated}
    raise ModelRetry(_write_refusal(shape, criteria))


def _write_refusal(shape: StatedShape, criteria: dict[str, Criterion]) -> str:
    parts = ["VALIDATION_ERROR: nothing was applied and the strategy is unchanged."]
    if shape.lost:
        named = ", ".join(f"{cid} ({criteria[cid].text})" for cid in shape.lost)
        parts.append(
            f"This subtree would drop {len(shape.lost)} of the criteria the "
            f"strategy states: {named}."
        )
    if shape.unstated:
        parts.append(f"It would add {list(shape.unstated)}, which no criterion states.")
    if shape.adopted:
        parts.append(f"It would adopt {list(shape.adopted)} from outside the strategy.")
    if shape.stranded:
        parts.append(f"It would strand {list(shape.stranded)}.")
    parts.append(
        "Send a subtree that keeps every step id the spec names, or change the "
        "criteria first."
    )
    return " ".join(parts)
