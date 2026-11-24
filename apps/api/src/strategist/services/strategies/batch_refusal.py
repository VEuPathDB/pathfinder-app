"""Why the tree a batch leaves behind departs from the spec, or nothing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from veupathdb.domain.strategy import subtree_ids

from strategist.domain.refusal import Check, Problems, RefusalKey
from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.spec_edit_guard import (
    JoinContradiction,
    ValueContradiction,
    contradicted_joins,
    contradicted_values,
    new_join_contradictions,
    new_value_contradictions,
)
from strategist.domain.strategy.stated_shape import (
    SlotWrite,
    criteria_with_steps,
    evicted_by,
    stated_shape,
)
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.stated_sides import CanonicalSides


@dataclass(frozen=True)
class EntryState:
    """What the graph held before the batch applied."""

    step_ids: set[str]
    reachable: set[str]
    joins: Mapping[frozenset[str], JoinContradiction]
    values: Mapping[tuple[str, str], ValueContradiction]


def entry_state(
    deps: StrategyMutationContext, graph: StrategyGraph, sides: CanonicalSides
) -> EntryState:
    return EntryState(
        step_ids=set(graph.steps),
        reachable=set(subtree_ids(graph.primary_root_id() or "", graph.steps)),
        joins=contradicted_joins(deps.stated_structure, graph, deps.stated_criteria),
        values=contradicted_values(sides.stated, graph, sides.entry),
    )


def _departure_from_the_spec(
    *,
    graph: StrategyGraph,
    stated: frozenset[str],
    outside: set[str],
) -> str | None:
    """How the graph departs from the criteria the spec states, or nothing."""
    shape = stated_shape(
        graph=graph,
        root_id=graph.primary_root_id() or "",
        criteria=stated,
        outside=outside,
    )
    if shape.holds:
        return None
    return (
        f"a replaced subtree would leave the strategy holding "
        f"{list(shape.searches)} where the spec states {list(shape.stated)}"
    )


def _eviction_message(write: SlotWrite, *, stated: frozenset[str]) -> str:
    """Why a slot write is refused, naming the step it would take off the tree."""
    answers = (
        " and answers a criterion the spec states"
        if write.occupant_step_id in stated
        else ""
    )
    return (
        f"the {write.slot} input of {write.target_step_id} holds "
        f"{write.occupant_step_id}{answers}, and this batch overwrites it, so "
        f"{write.occupant_step_id} would leave the strategy without being "
        f"deleted. Delete that step first, or keep it wired into the tree"
    )


def refusal_after_the_batch(
    *,
    deps: StrategyMutationContext,
    graph: StrategyGraph,
    entry: EntryState,
    sides: CanonicalSides,
    slot_writes: Sequence[SlotWrite],
    replaces_a_subtree: bool,
) -> Problems:
    """Every way the tree the batch leaves behind departs from the spec."""
    # The spec addresses this graph by step id, so a criterion answers to a
    # step the graph held before the batch or to one the batch mints.
    stated = criteria_with_steps(
        deps.stated_criteria,
        entry.step_ids,
        minted=set(graph.steps) - entry.step_ids,
    )
    problems = Problems()
    eviction = evicted_by(graph, slot_writes, was_reachable=entry.reachable)
    if eviction is not None:
        occupant = graph.get_step(eviction.occupant_step_id)
        problems = Problems.one(
            RefusalKey(check=Check.THE_SLOT_TO_ITS_STEP),
            _eviction_message(eviction, stated=stated),
        ).under(
            criterion=eviction.occupant_step_id,
            search="" if occupant is None else occupant.search_name or "",
        )
    if replaces_a_subtree and stated:
        departure = _departure_from_the_spec(
            graph=graph, stated=stated, outside=entry.step_ids - entry.reachable
        )
        if departure is not None:
            problems = problems.plus(
                Problems.one(
                    RefusalKey(check=Check.THE_SUBTREE_TO_THE_SPEC), departure
                ).under(criterion=graph.primary_root_id() or "", search="")
            )
    return problems.plus(
        new_join_contradictions(
            structure=deps.stated_structure,
            graph=graph,
            criteria=deps.stated_criteria,
            before=entry.joins,
        )
    ).plus(
        new_value_contradictions(
            stated=sides.stated, graph=graph, before=entry.values, after=sides.written
        )
    )
