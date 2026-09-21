"""Taking a criterion out of the spec being framed."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._frame_saved import holds_open_saved_slot


class DropCriterionResult(CamelModel):
    """Result of dropping a criterion from the spec."""

    criterion_id: str
    reason: str


def drop_criterion(
    ctx: RunContext[AgentDeps], *, criterion_id: str, reason: str
) -> ToolReturn[DropCriterionResult]:
    """Remove a criterion (by the ``criterion_id`` you set in ``set_criterion``)
    from the spec, e.g. when its WDK search is unavailable or has no realizable
    binding. The criterion and its open params are removed (so it no longer
    blocks the build) and recorded in ``dropped`` to surface to the user."""
    state = ctx.deps.agent_state
    open_saved = next(
        (
            c
            for c in state.operational_spec_draft.criteria
            if c.id == criterion_id and holds_open_saved_slot(c)
        ),
        None,
    )
    if open_saved is not None:
        msg = (
            f"{criterion_id} is the strategy the request starts from, and it is "
            f"still unresolved. Ask the user which one they mean and re-call "
            f"set_criterion with it; do not drop it."
        )
        raise ModelRetry(msg)
    dropped = state.frame_drop_criterion(criterion_id, reason)
    if not dropped:
        ids = [c.id for c in state.operational_spec_draft.criteria]
        msg = (
            f"No criterion with id {criterion_id!r} to drop. Use the exact "
            f"criterion_id from set_criterion. Current criteria: {ids}."
        )
        raise ModelRetry(msg)
    return with_summary(
        DropCriterionResult(criterion_id=criterion_id, reason=reason),
        f"Dropped {criterion_id}",
        ctx=ctx,
    )
