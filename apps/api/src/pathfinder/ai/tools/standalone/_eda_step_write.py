"""Where an exported EDA step lands in the strategy, as graph operations."""

from __future__ import annotations

from typing import Literal, NamedTuple

from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    generate_step_id,
)
from veupathdb.model import CamelModel

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._eda_step_spec import criterion_note
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    GraphOperation,
)
from pathfinder.domain.strategy.operations.types import (
    AttachIntoSlot,
    AttachNewRoot,
    AttachPoint,
    ReplaceSubtreeOp,
    WireInputOp,
)
from pathfinder.domain.strategy.session import StrategyGraph


class AskedPlacement(NamedTuple):
    """The placement arguments one export call sent."""

    attach_to_step_id: str | None
    slot: Literal["primary", "secondary"] | None
    replace_step_id: str | None
    combine_with_root: CombineOp | None

    def named(self) -> list[str]:
        return [name for name, value in self._asdict().items() if value is not None]


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


def _attach_point(
    attach_to_step_id: str | None,
    slot: Literal["primary", "secondary"] | None,
) -> AttachPoint:
    if attach_to_step_id is None and slot is None:
        return AttachNewRoot()
    if attach_to_step_id is None:
        msg = (
            f"slot={slot!r} names an input of a combine step, so it needs "
            f"attach_to_step_id. Leave both unset to add the step as a new root."
        )
        raise ModelRetry(msg)
    if slot is None:
        msg = (
            f"attach_to_step_id={attach_to_step_id!r} needs a slot: 'primary' or "
            f"'secondary' names which input of that combine to fill."
        )
        raise ModelRetry(msg)
    return AttachIntoSlot(target_step_id=attach_to_step_id, slot=slot)


def _refuse_an_occupied_slot(
    ctx: RunContext[LeadDeps], graph: StrategyGraph, attach: AttachPoint
) -> None:
    """An export fills a free slot, never one that already holds a step.

    A new step holds nothing, so filling an occupied slot would take the step
    that slot holds off the strategy with no delete and no record of the loss.
    """
    if attach.mode != "into-slot":
        return
    target = graph.get_step(attach.target_step_id)
    if target is None:
        return
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


def _refuse_a_second_target(
    attach_to_step_id: str | None,
    slot: Literal["primary", "secondary"] | None,
    replace_step_id: str | None,
) -> None:
    """A join to the root is the whole placement, so nothing else names one."""
    named = [
        name
        for name, value in (
            ("attach_to_step_id", attach_to_step_id),
            ("slot", slot),
            ("replace_step_id", replace_step_id),
        )
        if value is not None
    ]
    if not named:
        return
    msg = (
        f"combine_with_root puts the export beside the strategy's root, so it "
        f"names the whole placement and {named} name a second one. Send "
        f"combine_with_root alone, or send one of {named} alone."
    )
    raise ModelRetry(msg)


def _root_join(graph: StrategyGraph, operator: CombineOp) -> StepJoin:
    roots = sorted(graph.roots)
    if len(roots) != 1:
        msg = (
            f"combine_with_root joins the export to one root, and this "
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
    inputs = (node.id, join.step_id) if join.export_first else (join.step_id, node.id)
    combine = AddCombineOp(
        step=StrategyStepNode(
            id=generate_step_id(),
            search_name=COMBINE_SEARCH_NAME,
            operator=join.operator,
        ),
        left_id=inputs[0],
        right_id=inputs[1],
    )
    ops: list[GraphOperation] = [
        AddLeafOp(step=node, attach=AttachNewRoot()),
        combine,
    ]
    consumer = graph.parent_of(join.step_id)
    if consumer is not None:
        parent, _ = consumer
        ops.append(
            WireInputOp(
                target_step_id=parent.id,
                slot="primary"
                if parent.primary_input_id == join.step_id
                else "secondary",
                source_step_id=combine.step.id,
            )
        )
    return ExportWrite(
        ops=ops,
        join=ExportJoin(
            combine_step_id=combine.step.id,
            operator=join.operator,
            joined_step_id=join.step_id,
            export_first=join.export_first,
        ),
    )


def export_write(
    ctx: RunContext[LeadDeps],
    graph: StrategyGraph,
    node: StrategyStepNode,
    *,
    asked: AskedPlacement,
    join: StepJoin | None,
) -> ExportWrite:
    """Add the export as a new step, join it to a step, or replace one.

    ``join`` is where the structure places the export, and ``asked`` names a
    place only when the structure places none.
    """
    attach_to_step_id, slot, replace_step_id, combine_with_root = asked
    if combine_with_root is not None:
        _refuse_a_second_target(attach_to_step_id, slot, replace_step_id)
        join = _root_join(graph, combine_with_root)
    if join is not None:
        return join_write(graph, node, join)
    if replace_step_id is None:
        attach = _attach_point(attach_to_step_id, slot)
        _refuse_an_occupied_slot(ctx, graph, attach)
        return ExportWrite(ops=[AddLeafOp(step=node, attach=attach)])
    if attach_to_step_id is not None or slot is not None:
        msg = (
            f"replace_step_id={replace_step_id!r} puts the export in that "
            f"step's place, so attach_to_step_id and slot name a second "
            f"target. Send replace_step_id alone, or attach_to_step_id with "
            f"slot alone."
        )
        raise ModelRetry(msg)
    if replace_step_id not in graph.steps:
        msg = (
            f"No step {replace_step_id!r} in the strategy. It holds "
            f"{sorted(graph.steps)}."
        )
        raise ModelRetry(msg)
    return ExportWrite(ops=[ReplaceSubtreeOp(step_id=replace_step_id, subtree=node)])
