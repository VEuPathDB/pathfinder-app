"""Which criterion an export binds, and where the structure puts its step."""

from __future__ import annotations

from typing import Literal, NamedTuple

from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    pending_analyses,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_hydration import root_join_operator


class WaitingPlacement(NamedTuple):
    """The spec that holds the waiting criterion, and the join its step takes.

    ``operator`` is None when the export becomes the strategy's first step.
    """

    spec: OperationalSpec
    criterion_id: str
    operator: CombineOp | None


class AskedPlacement(NamedTuple):
    """The placement arguments one export call sent."""

    attach_to_step_id: str | None
    slot: Literal["primary", "secondary"] | None
    replace_step_id: str | None
    combine_with_root: CombineOp | None

    def named(self) -> list[str]:
        return [name for name, value in self._asdict().items() if value is not None]


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
    operator = root_join_operator(spec.structure, criterion_id)
    if operator is None:
        msg = (
            f"{criterion_id} is not an input of the structure's root combine, or "
            f"it stands first under an operator that reads its inputs in order, "
            f"and an export joins the strategy's root as its last input. Nothing "
            f"was written. Dispatch edit_strategy to place {criterion_id} under "
            f"the root combine, then export again."
        )
        raise ModelRetry(msg)
    return WaitingPlacement(spec, criterion_id, operator)


def _refuse_a_first_step_beside_unbuilt_searches(
    spec: OperationalSpec, criterion_id: str
) -> None:
    """The export roots an empty strategy only when no search is left to build."""
    unbuilt = [c.id for c in spec.criteria if not c.pending_analysis]
    if unbuilt:
        msg = (
            f"The strategy holds no step, and the spec states {unbuilt} beside "
            f"{criterion_id}. Call build_strategy for them first; this export "
            f"then joins the strategy's root."
        )
        raise ModelRetry(msg)
