"""The criterion id ``set_criterion`` accepts."""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.spec_reconciliation import reads_as_a_step_id


def refuse_a_step_shaped_id(ctx: RunContext[AgentDeps], criterion_id: str) -> None:
    """A new criterion is named outside the address space of built steps.

    An id of the built-step shape that no step answers to is read as a step the
    strategy lost, and the criterion leaves the spec before it can be built.
    """
    if not reads_as_a_step_id(criterion_id):
        return
    graph = ctx.deps.strategy_session.get_graph(None)
    if graph is not None and criterion_id in graph.steps:
        return
    msg = (
        f"{criterion_id!r} has the id shape of a step this strategy built, and "
        f"it holds no such step, so a criterion named that way is read as a "
        f"deleted step and leaves the spec. Name the criterion after what it "
        f"asks for instead, such as 'c_secreted'."
    )
    raise ModelRetry(msg)
