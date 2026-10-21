"""Standalone strategy attachment tool (filter) for pydantic-ai migration.

Each function takes ``RunContext[AgentDeps]`` and mirrors the original
:class:`StrategyAttachmentOps` methods exactly.
"""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic import JsonValue
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.strategy import (
    StepFilter,
    StrategyStep,
)
from veupathdb_mcp import ToolErrorPayload

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._validation_helpers import (
    StepOkResponse,
    get_graph_and_step,
)
from pathfinder.ai.tools.standalone.graph_helpers import step_ok_response
from pathfinder.ai.tools.standalone.stream_parts import graph_snapshot_chunk
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession


def _step_updated_return(
    ctx: RunContext[AgentDeps],
    session: StrategySession,
    graph: StrategyGraph,
    step: StrategyStep,
    summary: str,
) -> ToolReturn[StepOkResponse | ToolErrorPayload]:
    """Wrap an attachment-mutation success in a ToolReturn with one snapshot."""
    return with_summary(
        step_ok_response(session, graph, step),
        summary,
        ctx=ctx,
        extra=[graph_snapshot_chunk(session, graph)],
    )


def _step_missing(
    ctx: RunContext[AgentDeps],
    payload: ToolErrorPayload,
    step_id: str,
) -> ToolReturn[StepOkResponse | ToolErrorPayload]:
    """The attachment named a step the graph does not hold."""
    return with_summary(
        payload,
        f"No step {step_id} in the strategy",
        ctx=ctx,
        status="warn",
    )


async def add_step_filter(
    ctx: RunContext[AgentDeps],
    step_id: str,
    filter_name: str,
    value: JsonValue,
    *,
    disabled: bool = False,
    graph_id: str | None = None,
) -> ToolReturn[StepOkResponse | ToolErrorPayload]:
    """Attach or update a WDK filter on a step.

    Filters narrow a step's results without changing its search.
    If a filter with the same name already exists it is replaced.

    Args:
        step_id: ID of the step to filter.
        filter_name: WDK filter name (e.g. 'gene_boolean_filter_array').
        value: Filter value (shape depends on the filter type).
        disabled: If True the filter is stored but not applied.
        graph_id: Target graph. Uses the active graph if omitted.
    """
    deps = ctx.deps
    session = deps.strategy_session

    result = get_graph_and_step(session, graph_id, step_id)
    if isinstance(result, ToolErrorPayload):
        return _step_missing(ctx, result, step_id)
    graph, step = result

    existing = [f for f in step.filters if f.name != filter_name]
    existing.append(StepFilter(name=filter_name, value=value, disabled=disabled))
    step.filters = existing

    return _step_updated_return(
        ctx, session, graph, step, f"{filter_name} added to {step_id}"
    )
