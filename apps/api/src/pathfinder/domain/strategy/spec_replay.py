"""Play an outside change onto the spec the strategy answered to.

A value the researcher set outside this thread is their statement, so the
criterion takes it and everything the criterion said about that name retires
with it. Only a name the search's sheet shows is replayed: the rest of a
step's parameters are WDK's own.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.ast_diff import StepChange, nodes_of
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.outside_changes import OutsideChanges
from pathfinder.domain.strategy.spec_hydration import (
    sheet_bound,
    spec_stating_the_live_tree,
)
from pathfinder.domain.strategy.spec_reconciliation import spec_without_steps

__all__ = ["criterion_rebound", "criterion_restated", "spec_replaying"]


def criterion_restated(
    criterion: Criterion, name: str, value: ParamValue | None
) -> Criterion:
    """The criterion stating this value, and saying nothing else about the name.

    A value the strategy holds is decided, so the slot that asked for it, the
    default it stood in for, the assumption that explained it and the options
    it was chosen from all go with the old value.
    """
    params = {n: v for n, v in criterion.resolved_params.items() if n != name}
    if value is not None:
        params[name] = value
    return criterion.model_copy(
        update={
            "resolved_params": params,
            "defaulted_params": [p for p in criterion.defaulted_params if p != name],
            "open_params": [s for s in criterion.open_params if s.param_name != name],
            "assumptions": [a for a in criterion.assumptions if a.param_name != name],
            "alternatives": [a for a in criterion.alternatives if a.param_name != name],
        }
    )


def criterion_rebound(
    criterion: Criterion,
    node: StrategyStepNode,
    sheet: Collection[str] | None,
) -> Criterion:
    """The criterion on the search its step now runs, stating its whole binding.

    A search shares no values with the one it replaces, so nothing the
    criterion said about the old binding survives it.
    """
    return criterion.model_copy(
        update={
            "search_name": node.search_name,
            "saved_strategy_ref": None,
            "resolved_params": sheet_bound(node.parameters, sheet),
            "defaulted_params": [],
            "open_params": [],
            "assumptions": [],
            "alternatives": [],
        }
    )


def spec_replaying(
    spec: OperationalSpec,
    changes: OutsideChanges,
    live: StrategyAst | None,
    *,
    sheet_params: Mapping[str, Collection[str]],
    may_leave_out: Collection[str] = (),
) -> OperationalSpec:
    """The spec the strategy answers to once the outside change is played onto it.

    A criterion whose step the strategy lost leaves; a step it gained is
    stated; a value or a search moved outside is restated on the criterion
    that answers to that step. ``may_leave_out`` names the steps this spec is
    entitled to leave out, which is how a plan carries a drop it has not
    pushed.
    """
    replayed = spec_without_steps(spec, changes.removed_ids)
    if live is None:
        return replayed
    replayed = _the_values_the_steps_now_hold(replayed, changes, live, sheet_params)
    return spec_stating_the_live_tree(
        replayed,
        live,
        sheet_params=sheet_params,
        shape_moved=changes.structure_moved,
        may_leave_out=may_leave_out,
    )


def _the_values_the_steps_now_hold(
    spec: OperationalSpec,
    changes: OutsideChanges,
    live: StrategyAst,
    sheet_params: Mapping[str, Collection[str]],
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
            sheet_params,
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
    sheet_params: Mapping[str, Collection[str]],
    closed: set[tuple[str, str]],
) -> Criterion:
    """The criterion holding what its step now says, and the slots that closes."""
    sheet = sheet_params.get(node.search_name)
    if change.search_after is not None:
        closed.update((criterion.id, slot.param_name) for slot in criterion.open_params)
        return criterion_rebound(criterion, node, sheet)
    restated = criterion
    for param in change.params:
        if sheet is not None and param.name not in sheet:
            continue
        restated = criterion_restated(
            restated, param.name, node.parameters.get(param.name)
        )
        closed.add((criterion.id, param.name))
    return restated
