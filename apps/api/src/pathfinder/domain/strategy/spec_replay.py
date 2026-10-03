"""Play an outside change onto the spec the strategy answered to.

A value the researcher set outside this thread is their statement, so the
criterion takes it and everything the criterion said about that name retires
with it. Only a name the search's sheet shows is replayed: the rest of a
step's parameters are WDK's own.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import NamedTuple

from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.ast_diff import StepChange, nodes_of
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    ValueSource,
)
from pathfinder.domain.strategy.outside_changes import OutsideChanges
from pathfinder.domain.strategy.spec_hydration import (
    Analyses,
    Sheets,
    criterion_analysing,
    sheet_bound,
    sheet_marked,
    spec_stating_the_live_tree,
)
from pathfinder.domain.strategy.spec_reconciliation import spec_without_steps
from pathfinder.domain.strategy.value_binding import bind_values

__all__ = ["criterion_rebound", "criterion_restated", "spec_replaying"]


def criterion_restated(
    criterion: Criterion,
    name: str,
    value: ParamValue | None,
    *,
    sheet: Sequence[ParameterInfo],
    source: ValueSource = "held",
    basis: str = "",
) -> Criterion:
    """The criterion stating this value, and saying nothing else about the name.

    A decided value takes the place of the slot that asked for it, the counts
    measured around the old value and the options it was chosen from. The
    value is the strategy's unless ``source`` names who set it. ``sheet`` is
    the search's published sheet, empty when none was read.
    """
    params = {n: v for n, v in criterion.resolved_params.items() if n != name}
    if value is not None:
        params |= bind_values({name: value}, source, sheet, basis)
    return criterion.model_copy(
        update={
            "resolved_params": params,
            "measurements": [m for m in criterion.measurements if m.param != name],
            "open_params": [s for s in criterion.open_params if s.param_name != name],
            "alternatives": [a for a in criterion.alternatives if a.param_name != name],
            "result_count": None,
        }
    )


def criterion_rebound(
    criterion: Criterion,
    node: StrategyStepNode,
    sheet: Sequence[ParameterInfo] | None,
) -> Criterion:
    """The criterion on the search its step now runs, stating its whole binding.

    A search shares no values with the one it replaces, so nothing the
    criterion said about the old binding survives it.
    """
    rebound = criterion.model_copy(
        update={
            "search_name": node.search_name,
            "saved_strategy_ref": None,
            "analysis": None,
            "resolved_params": bind_values(
                sheet_bound(node.parameters, sheet), "held", sheet or ()
            ),
            "measurements": [],
            "open_params": [],
            "alternatives": [],
            "result_count": None,
            "rationale": None,
        }
    )
    return rebound if sheet is None else sheet_marked(rebound, sheet)


def spec_replaying(
    spec: OperationalSpec,
    changes: OutsideChanges,
    live: StrategyAst | None,
    *,
    sheet_params: Sheets,
    analyses: Analyses,
    may_leave_out: Collection[str] = (),
) -> OperationalSpec:
    """The spec the strategy answers to once the outside change is played onto it.

    A criterion whose step the strategy lost leaves; a step it gained is
    stated; a value or a search moved outside is restated on the criterion
    that answers to that step. ``analyses`` are the live steps that read as
    an exported analysis. ``may_leave_out`` names the steps this spec is
    entitled to leave out, which is how a plan carries a drop it has not
    pushed.
    """
    replayed = spec_without_steps(spec, changes.removed_ids)
    if live is None:
        return replayed
    reading = _StepReading(sheet_params=sheet_params, analyses=analyses)
    replayed = _the_values_the_steps_now_hold(replayed, changes, live, reading)
    return spec_stating_the_live_tree(
        replayed,
        live,
        sheet_params=sheet_params,
        analyses=analyses,
        shape_moved=changes.structure_moved,
        may_leave_out=may_leave_out,
    )


class _StepReading(NamedTuple):
    """How a replay reads a live step: its sheet, or the analysis it exports."""

    sheet_params: Sheets
    analyses: Analyses


def _the_values_the_steps_now_hold(
    spec: OperationalSpec,
    changes: OutsideChanges,
    live: StrategyAst,
    reading: _StepReading,
) -> OperationalSpec:
    """The spec restating every value and search that moved on a live step."""
    moved = {change.step_id: change for change in changes.changed}
    if not moved:
        return spec
    nodes = nodes_of(live)
    restated = spec.model_copy(deep=True)
    closed: set[tuple[str, str]] = set()
    restated.criteria = [
        criterion
        if criterion.id not in moved or criterion.id not in nodes
        else _criterion_the_step_states(
            criterion,
            moved[criterion.id],
            nodes[criterion.id],
            reading,
            closed,
        )
        for criterion in restated.criteria
    ]
    restated.open_slots = [
        slot
        for slot in restated.open_slots
        if (slot.criterion_id, slot.param_name) not in closed
    ]
    return restated


def _criterion_the_step_states(
    criterion: Criterion,
    change: StepChange,
    node: StrategyStepNode,
    reading: _StepReading,
    closed: set[tuple[str, str]],
) -> Criterion:
    """The criterion holding what its step now says, and the slots that closes.

    A step that exports an analysis is read by the binding it now carries,
    never by its document.
    """
    binding = reading.analyses.get(node.id)
    if binding is not None:
        closed.update((criterion.id, slot.param_name) for slot in criterion.open_params)
        return criterion_analysing(criterion, node.search_name, binding)
    sheet = reading.sheet_params.get(node.search_name)
    if change.search_after is not None:
        closed.update((criterion.id, slot.param_name) for slot in criterion.open_params)
        return criterion_rebound(criterion, node, sheet)
    shown = sheet_bound({p.name: p for p in change.params}, sheet)
    restated = criterion
    for name in shown:
        restated = criterion_restated(
            restated, name, node.parameters.get(name), sheet=sheet or ()
        )
        closed.add((criterion.id, name))
    return restated
