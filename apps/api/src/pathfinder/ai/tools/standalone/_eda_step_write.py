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
)
from pathfinder.domain.strategy.session import StrategyGraph


class ExportWrite(NamedTuple):
    """The operations the export lands as, and the combine they may create."""

    ops: list[GraphOperation]
    combine: AddCombineOp | None = None


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


def _joined_with_the_root(
    graph: StrategyGraph, node: StrategyStepNode, operator: CombineOp
) -> ExportWrite:
    """Add the export, then combine it with the strategy's one root."""
    roots = sorted(graph.roots)
    if len(roots) != 1:
        msg = (
            f"combine_with_root joins the export to one root, and this "
            f"strategy has {len(roots)}: {roots}. Build the strategy first, "
            f"or name the step to replace or the free slot to fill."
        )
        raise ModelRetry(msg)
    combine = AddCombineOp(
        step=StrategyStepNode(
            id=generate_step_id(),
            search_name=COMBINE_SEARCH_NAME,
            operator=operator,
        ),
        left_id=roots[0],
        right_id=node.id,
    )
    return ExportWrite(
        ops=[AddLeafOp(step=node, attach=AttachNewRoot()), combine], combine=combine
    )


def export_write(
    ctx: RunContext[LeadDeps],
    graph: StrategyGraph,
    node: StrategyStepNode,
    *,
    attach_to_step_id: str | None,
    slot: Literal["primary", "secondary"] | None,
    replace_step_id: str | None,
    combine_with_root: CombineOp | None,
) -> ExportWrite:
    """Add the export as a new step, join it to the root, or replace one."""
    if combine_with_root is not None:
        _refuse_a_second_target(attach_to_step_id, slot, replace_step_id)
        return _joined_with_the_root(graph, node, combine_with_root)
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
