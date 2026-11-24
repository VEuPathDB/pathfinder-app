"""Where an exported EDA step lands in the strategy, as graph operations."""

from __future__ import annotations

from typing import NamedTuple

from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStep,
    StrategyStepNode,
    generate_step_id,
)
from veupathdb.model import CamelModel

from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.tools.standalone._eda_step_arguments import (
    BesideRoot,
    ExportPlacement,
    InPlaceOf,
    IntoSlot,
)
from strategist.ai.tools.standalone._eda_step_spec import criterion_note
from strategist.ai.tools.standalone._step_read import held_step
from strategist.domain.strategy.combine_order import flat_join, wired_in_place
from strategist.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    GraphOperation,
)
from strategist.domain.strategy.operations.types import (
    AttachIntoSlot,
    AttachNewRoot,
    ReplaceSubtreeOp,
)
from strategist.domain.strategy.session import StrategyGraph


class StepJoin(NamedTuple):
    """The step an export combines with, the operator, and whether the export
    is the combine's first input."""

    step_id: str
    operator: CombineOp
    export_first: bool = False


class ExportJoin(CamelModel):
    """The combine that joined an export to a step the strategy held."""

    combine_step_id: str
    operator: CombineOp
    joined_step_id: str
    export_first: bool


class ExportWrite(NamedTuple):
    """The operations the export lands as, and the join they may make."""

    ops: list[GraphOperation]
    join: ExportJoin | None = None


def _refuse_an_occupied_slot(
    ctx: RunContext[LeadDeps], target: StrategyStep, attach: AttachIntoSlot
) -> None:
    """An export fills a free slot, never one that already holds a step.

    A new step holds nothing, so filling an occupied slot would take the step
    that slot holds off the strategy with no delete and no record of the loss.
    """
    occupant = (
        target.primary_input_id
        if attach.slot == "primary"
        else target.secondary_input_id
    )
    if occupant is None:
        return
    msg = (
        f"The {attach.slot} input of {attach.target_step_id} already holds "
        f"{occupant}{criterion_note(ctx, occupant)}. Exporting into it would "
        f"take {occupant} off the strategy, so nothing was added. Delete "
        f"{occupant} first, or name a slot that is free."
    )
    raise ModelRetry(msg)


def _root_join(graph: StrategyGraph, operator: CombineOp) -> StepJoin:
    roots = sorted(graph.roots)
    if len(roots) != 1:
        msg = (
            f'A "beside_root" placement joins the export to one root, and this '
            f"strategy has {len(roots)}: {roots}. Build the strategy first, "
            f"or name the step to replace or the free slot to fill."
        )
        raise ModelRetry(msg)
    return StepJoin(roots[0], operator)


def join_write(
    graph: StrategyGraph, node: StrategyStepNode, join: StepJoin
) -> ExportWrite:
    """Add the export, combine it with the joined step, and give the combine
    the place that step held."""
    left, right = (
        (node.id, join.step_id) if join.export_first else (join.step_id, node.id)
    )
    nests = graph.steps[join.step_id].primary_input_id is not None
    placed = flat_join(
        left,
        right,
        join.operator,
        left_nests=nests and not join.export_first,
        right_nests=nests and join.export_first,
    )
    combine = AddCombineOp(
        step=StrategyStepNode(
            id=generate_step_id(),
            search_name=COMBINE_SEARCH_NAME,
            operator=placed.operator,
        ),
        left_id=placed.primary,
        right_id=placed.secondary,
    )
    ops: list[GraphOperation] = [
        AddLeafOp(step=node, attach=AttachNewRoot()),
        combine,
        *wired_in_place(graph, graph.parent_of(join.step_id), combine.step.id),
    ]
    return ExportWrite(
        ops=ops,
        join=ExportJoin(
            combine_step_id=combine.step.id,
            operator=placed.operator,
            joined_step_id=join.step_id,
            export_first=placed.primary == node.id,
        ),
    )


def export_write(
    ctx: RunContext[LeadDeps],
    graph: StrategyGraph,
    node: StrategyStepNode,
    *,
    placement: ExportPlacement | None,
    join: StepJoin | None,
) -> ExportWrite:
    """Add the export as a new step, join it to a step, or replace one.

    ``join`` is where the structure places the export, and ``placement`` names
    a place only when the structure places none.
    """
    if join is not None:
        return join_write(graph, node, join)
    match placement:
        case BesideRoot(operator=operator):
            return join_write(graph, node, _root_join(graph, operator))
        case IntoSlot(attach_to_step_id=target, slot=slot):
            attach = AttachIntoSlot(target_step_id=target, slot=slot)
            _refuse_an_occupied_slot(ctx, held_step(graph, target), attach)
            return ExportWrite(ops=[AddLeafOp(step=node, attach=attach)])
        case InPlaceOf(replace_step_id=replaced):
            held_step(graph, replaced)
            return ExportWrite(ops=[ReplaceSubtreeOp(step_id=replaced, subtree=node)])
        case _:
            return ExportWrite(ops=[AddLeafOp(step=node, attach=AttachNewRoot())])
