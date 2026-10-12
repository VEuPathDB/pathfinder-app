"""Which criterion an export binds, and where the structure puts its step."""

from __future__ import annotations

from typing import NamedTuple

from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.tools.standalone._eda_step_write import AskedPlacement, StepJoin
from pathfinder.domain.strategy.join_point import branch_step, join_point
from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    pending_analyses,
    structure_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph


class WaitingPlacement(NamedTuple):
    """The spec that holds the waiting criterion, and the join its step takes.

    ``join`` is None when the export becomes the strategy's first step.
    """

    spec: OperationalSpec
    criterion_id: str
    join: StepJoin | None


def export_placement(
    spec: OperationalSpec | None,
    graph: StrategyGraph,
    criterion_id: str | None,
    *,
    dataset_id: str,
    asked: AskedPlacement,
) -> WaitingPlacement | None:
    """The waiting criterion this export binds and where, or None for none."""
    if criterion_id is None:
        refuse_an_export_that_names_no_waiting_criterion(spec, dataset_id)
        return None
    return waiting_placement(
        spec, graph, criterion_id, dataset_id=dataset_id, named=asked.named()
    )


def refuse_an_export_that_names_no_waiting_criterion(
    spec: OperationalSpec | None, dataset_id: str
) -> None:
    """An export on a dataset a criterion waits on takes that criterion's place.

    The handoff is by the criterion's id, so an export that names none would
    state the same comparison twice.
    """
    waiting = [
        c.id for c in pending_analyses(spec) if c.needs_analysis_on == dataset_id
    ]
    if not waiting:
        return
    msg = (
        f"The spec holds {waiting} waiting for an analysis on dataset "
        f'{dataset_id}, and this export names none of them. Pass criterion_id="'
        f"{waiting[0]}\" so the export takes that criterion's place in the "
        f"structure."
    )
    raise ModelRetry(msg)


def waiting_placement(
    spec: OperationalSpec | None,
    graph: StrategyGraph,
    criterion_id: str,
    *,
    dataset_id: str,
    named: list[str],
) -> WaitingPlacement:
    """Where the export for this waiting criterion goes, or why it cannot.

    ``named`` are the placement arguments the call also sent. The structure
    places the step, so a call that names another place is refused.
    """
    if named:
        msg = (
            f"criterion_id={criterion_id!r} puts the export where the structure "
            f"places that criterion, so {named} name a second place. Send "
            f"criterion_id alone."
        )
        raise ModelRetry(msg)
    waiting = next((c for c in pending_analyses(spec) if c.id == criterion_id), None)
    if spec is None or waiting is None:
        held = [c.id for c in pending_analyses(spec)]
        msg = (
            f"The spec holds no criterion {criterion_id!r} waiting for an "
            f"analysis; it holds {held}."
        )
        raise ModelRetry(msg)
    if waiting.needs_analysis_on != dataset_id:
        msg = (
            f"{criterion_id} waits on dataset {waiting.needs_analysis_on}, and the "
            f"open analysis is on {dataset_id}. Open an analysis on "
            f"{waiting.needs_analysis_on} and export it from there."
        )
        raise ModelRetry(msg)
    if graph.primary_root_id() is None:
        _refuse_a_first_step_beside_unbuilt_searches(spec, criterion_id)
        return WaitingPlacement(spec, criterion_id, None)
    return WaitingPlacement(spec, criterion_id, _join(spec, graph, criterion_id))


def _join(spec: OperationalSpec, graph: StrategyGraph, criterion_id: str) -> StepJoin:
    """The step the structure joins this criterion to, or why none is held."""
    point = join_point(spec.structure, graph.steps, criterion_id)
    if point is None:
        msg = (
            f"The structure joins {criterion_id} to no step the strategy holds: "
            f"it names {sorted(structure_criteria(spec.structure))} and the "
            f"strategy holds {sorted(graph.steps)}. Nothing was written. Dispatch "
            f"edit_strategy so the structure places {criterion_id} beside a step "
            f"the strategy holds, then export again."
        )
        raise ModelRetry(msg)
    step_id = branch_step(graph, spec.structure, point.anchor)
    if step_id is None:
        msg = (
            f"The structure joins {criterion_id} to {sorted(point.anchor)} as one "
            f"branch, and the strategy holds no step that joins exactly those. "
            f"Nothing was written. Dispatch edit_strategy so the strategy holds "
            f"the structure's branches, then export again."
        )
        raise ModelRetry(msg)
    return StepJoin(step_id, point.operator, export_first=point.comes_first)


def _refuse_a_first_step_beside_unbuilt_searches(
    spec: OperationalSpec, criterion_id: str
) -> None:
    """The export roots an empty strategy only when no search is left to build."""
    unbuilt = [c.id for c in spec.criteria if not c.pending_analysis]
    if unbuilt:
        msg = (
            f"The strategy holds no step, and the spec states {unbuilt} beside "
            f"{criterion_id}. Call build_strategy for them first; this export "
            f"then joins them where the structure places it."
        )
        raise ModelRetry(msg)
