"""How a per-step edit is measured against the spec the strategy realizes."""

from __future__ import annotations

from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.operations import ReplaceSubtreeOp
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.stated_shape import StatedShape, shape_after


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
