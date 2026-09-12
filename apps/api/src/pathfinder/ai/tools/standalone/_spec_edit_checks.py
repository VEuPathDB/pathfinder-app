"""How a per-step edit is measured against the spec the strategy realizes."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.domain.strategy import StrategyStep
from veupathdb_mcp.catalog import ValidationCallbacks, validate_parameters

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.operations import ReplaceSubtreeOp
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import (
    StatedCriterion,
    spec_stated_values,
)
from pathfinder.domain.strategy.stated_shape import StatedShape, shape_after


def _needs_a_second_look(
    criterion: StatedCriterion,
    *,
    step: StrategyStep,
    patch: Mapping[str, ParamValue],
) -> bool:
    """Whether the stated values need a canonicalization of their own.

    The write's own call already canonicalizes every stated value the step
    holds and the patch leaves alone, so only a name the patch sends or a
    value the step does not already hold has to be asked for.
    """
    for name, value in criterion.values.items():
        held = step.parameters.get(name)
        if name in patch or (held is not None and to_wire(held) != to_wire(value)):
            return True
    return False


async def canonical_stated_values(
    deps: AgentDeps,
    *,
    step: StrategyStep,
    patch: Mapping[str, ParamValue],
    written: Mapping[str, ParamValue],
    search: SearchContext,
    callbacks: ValidationCallbacks,
) -> Mapping[str, StatedCriterion]:
    """The spec's stated values in the form the catalog writes them.

    A patch reaches the graph canonicalized, so a value it is compared with
    passes through the same canonicalizer. Without this a catalog that
    rewrites a parameter the write never sent reads as a departure.
    """
    stated = spec_stated_values(deps.agent_state.operational_spec_draft)
    criterion = stated.get(step.id)
    if criterion is None:
        return stated
    canonical = written
    if _needs_a_second_look(criterion, step=step, patch=patch):
        overlay = await validate_parameters(
            search,
            parameters={**step.parameters, **criterion.values},
            callbacks=callbacks,
        )
        canonical = overlay.params
    return {
        **stated,
        step.id: StatedCriterion(
            text=criterion.text,
            values={
                name: canonical[name] for name in criterion.values if name in canonical
            },
        ),
    }


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
