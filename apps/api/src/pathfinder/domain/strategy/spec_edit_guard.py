"""Whether a write contradicts the operational spec the strategy realizes.

The spec declares the operator its criteria meet at and holds the parameter
values the user stated. A write that changes either one is measured here.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from typing import NamedTuple

from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.domain.strategy import CombineOp, StepKind

from pathfinder.domain.strategy.combination_check import meeting_operator
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import ConstraintSource
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.session import StrategyGraph

__all__ = [
    "JoinContradiction",
    "contradicted_joins",
    "edit_contradiction",
    "new_join_contradiction",
    "stated_values",
    "value_contradiction",
]

_THROUGH_THE_SPEC = (
    "Stop here and report it, so the framing pass restates the spec and the "
    "build writes it."
)


class _Brought(NamedTuple):
    """What a subtree carries into the combine above it."""

    named: frozenset[str]
    unnamed: bool


def _brought(graph: StrategyGraph, step_id: str, stated: frozenset[str]) -> _Brought:
    """The criteria this subtree brings, and whether it brings anything else.

    A criterion stands for its whole input, which is how a transform stands for
    the branch it reads. A step no criterion states is brought unnamed.
    """
    if step_id in stated:
        return _Brought(named=frozenset({step_id}), unnamed=False)
    step = graph.get_step(step_id)
    inputs = [] if step is None else step.input_ids()
    if not inputs:
        return _Brought(named=frozenset(), unnamed=True)
    parts = [_brought(graph, sid, stated) for sid in inputs]
    return _Brought(
        named=frozenset[str]().union(*(part.named for part in parts)),
        unnamed=any(part.unnamed for part in parts),
    )


class JoinContradiction(NamedTuple):
    """The operator a combine carries where the spec declares another."""

    declared: CombineOp
    written: CombineOp


def contradicted_joins(
    structure: SpecStructure | None,
    graph: StrategyGraph,
    criteria: Collection[str],
) -> dict[frozenset[str], JoinContradiction]:
    """Every combine of this graph the spec declares another operator for.

    Keyed by the criteria the combine joins, so a rewritten subtree that mints
    fresh step ids states the same join. A combine the spec says nothing about
    is absent: no structure, criteria that meet at no combine of it, or a
    combine that also brings a step no criterion states, which asks a question
    of its own and carries any operator.
    """
    if structure is None:
        return {}
    stated = frozenset(criteria)
    found: dict[frozenset[str], JoinContradiction] = {}
    for step_id, step in graph.steps.items():
        operator = step.operator
        if step.kind is not StepKind.COMBINE or operator is None:
            continue
        brought = _brought(graph, step_id, stated)
        if brought.unnamed:
            continue
        declared = meeting_operator(structure, brought.named)
        if declared is not None and declared is not operator:
            found[brought.named] = JoinContradiction(
                declared=declared, written=operator
            )
    return found


def new_join_contradiction(
    *,
    structure: SpecStructure | None,
    graph: StrategyGraph,
    criteria: Collection[str],
    before: Mapping[frozenset[str], JoinContradiction],
) -> str | None:
    """Why this write joins the spec's criteria against the spec, or None.

    Only a join the write introduces is refused. A tree that already
    contradicted the spec keeps its answer until something restates one of them.
    """
    for joined, join in contradicted_joins(structure, graph, criteria).items():
        if before.get(joined) == join:
            continue
        return (
            f"the spec joins {sorted(joined)} at {join.declared.value}, and this "
            f"write joins them at {join.written.value}, so the strategy would "
            f"answer a different question. A structure the spec states changes "
            f"in the spec first (set_structure, in the framing pass). "
            f"{_THROUGH_THE_SPEC}"
        )
    return None


def _states_the_wire_form(text: str, wire: str) -> bool:
    """Whether these words carry this value, on its own and not inside a word."""
    return re.search(rf"(?<!\w){re.escape(wire)}(?!\w)", text) is not None


def stated_values(spec: OperationalSpec, criterion: Criterion) -> dict[str, str]:
    """The parameter values this criterion holds because the user stated them.

    A value is stated when the criterion's own words carry it, or when a
    requirement the user stated grounds onto it. Every other value is the
    model's or the search's own, and an edit may change it.
    """
    grounded = {
        (g.realized_param, g.realized_value)
        for g in ground_against_spec(
            [c for c in spec.constraints if c.source is ConstraintSource.USER_EXPLICIT],
            spec,
        )
        if g.realized_param and g.realized_value
    }
    found: dict[str, str] = {}
    for name, value in criterion.resolved_params.items():
        wire = to_wire(value)
        if (name, wire) in grounded or _states_the_wire_form(criterion.text, wire):
            found[name] = wire
    return found


def value_contradiction(
    spec: OperationalSpec,
    *,
    step_id: str,
    parameters: Mapping[str, ParamValue],
) -> str | None:
    """Why the spec's criterion refuses these values on this step, or None."""
    criterion = next((c for c in spec.criteria if c.id == step_id), None)
    if criterion is None:
        return None
    stated = stated_values(spec, criterion)
    contradicted = [
        f"{name} states {stated[name]!r} and this edit sends {to_wire(value)!r}"
        for name, value in parameters.items()
        if name in stated and to_wire(value) != stated[name]
    ]
    if not contradicted:
        return None
    return (
        f"VALIDATION_ERROR: nothing was applied and the strategy is unchanged. "
        f"The criterion {criterion.text!r} states the values this edit changes: "
        f"{'; '.join(contradicted)}. A value the spec states changes in the spec "
        f"first (set_criterion, in the framing pass). {_THROUGH_THE_SPEC}"
    )


def edit_contradiction(spec: OperationalSpec, op: GraphOperation) -> str | None:
    """Why the spec refuses this operation, or None.

    Only the values one operation restates are read here. What a written tree
    joins is measured on the tree the batch leaves behind.
    """
    if op.kind == "updateStepParams":
        return value_contradiction(spec, step_id=op.step_id, parameters=op.parameters)
    return None
