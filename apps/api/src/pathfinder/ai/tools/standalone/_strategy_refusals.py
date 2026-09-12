"""The refusals the strategy tools return instead of raising."""

from __future__ import annotations

from typing import cast

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.types import JSONObject
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp import ToolErrorPayload, tool_error

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._validation_helpers import (
    StepOkResponse,
    graph_not_found,
)
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.strategies.commit import CommitResult


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


def _step_edit_refused(
    ctx: RunContext[AgentDeps],
    payload: ToolErrorPayload,
    step_id: str,
) -> ToolReturn[StepOkResponse | ToolErrorPayload]:
    """A step edit VEuPathDB did not take."""
    return with_summary(
        payload,
        f"VEuPathDB refused the edit of {step_id}",
        ctx=ctx,
        status="warn",
    )


def _wdk_refused_the_edit(result: CommitResult) -> ToolErrorPayload | None:
    """WDK's answer for every step of the edit that did not reach it.

    A refusal of the values is a retry, because other values can pass. Any
    other answer is the tool's own, because a retry cannot mend it.
    """
    if not result.failures:
        return None
    answers = "; ".join(
        f"{failure.step_id} ({failure.search_name}): {failure.error}"
        for failure in result.failures
    )
    step_ids = ", ".join(sorted(result.failed_step_ids))
    if all(failure.wdk_refused_the_values for failure in result.failures):
        msg = (
            f"WDK_REJECTED: VEuPathDB refused this edit, so the strategy it "
            f"holds still runs the previous search and values for {step_ids}. "
            f"{answers}"
        )
        raise ModelRetry(msg)
    return tool_error(ErrorCode.WDK_ERROR, answers, stepIds=step_ids)
