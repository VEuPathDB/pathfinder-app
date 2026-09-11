"""The refusals the strategy tools return instead of raising."""

from __future__ import annotations

from typing import cast

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.types import JSONObject
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp import ToolErrorPayload

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._validation_helpers import (
    StepOkResponse,
    graph_not_found,
)


def _refused(
    ctx: RunContext[AgentDeps],
    payload: ToolErrorPayload,
    summary: str,
) -> ToolReturn[JSONObject]:
    """An error payload the model reads, with the line that names the refusal."""
    return with_summary(
        cast("JSONObject", payload.model_dump(by_alias=True, mode="json")),
        summary,
        ctx=ctx,
        status="warn",
    )


def _no_graph(
    ctx: RunContext[AgentDeps],
    graph_id: str | None,
) -> ToolReturn[JSONObject]:
    """The call named a graph the session does not hold."""
    return _refused(
        ctx,
        graph_not_found(graph_id),
        "No strategy graph on this thread",
    )


def _step_not_found(
    ctx: RunContext[AgentDeps],
    payload: ToolErrorPayload,
    step_id: str,
) -> ToolReturn[StepOkResponse | ToolErrorPayload]:
    """The edit named a step the graph does not hold."""
    return with_summary(
        payload,
        f"No step {step_id} in the strategy",
        ctx=ctx,
        status="warn",
    )
