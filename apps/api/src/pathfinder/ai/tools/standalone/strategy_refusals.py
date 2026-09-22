"""What the strategy tools say when a write does not happen.

Each refusal names what refused the write, so a caller never reports a local
check as an answer from VEuPathDB.
"""

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


def build_departs_from_the_plan_message(detail: str) -> str:
    """Why a build whose tree would answer another question is refused.

    The check reads the local tree, so VEuPathDB is never asked and the site
    refuses nothing.
    """
    stated = detail if detail.rstrip().endswith((".", "!", "?")) else f"{detail}."
    return (
        f"This build would leave a tree that departs from the plan: {stated} "
        f"Nothing was built and the strategy is unchanged, and VEuPathDB was "
        f"not asked."
    )


def operation_refused_message(detail: str, *, wrote: str) -> str:
    """Why a write was refused before it reached VEuPathDB.

    The write rolls back whole, so the strategy holds what it held. ``wrote``
    names what the call would have done, in the caller's own words.
    """
    return (
        f'One operation this {wrote} writes was refused: "{detail}". Nothing '
        f"was applied: the strategy still holds every step and every value it "
        f"held, and VEuPathDB was not asked. Change the operation the message "
        f"names and send it again, or report what could not be written and "
        f"stop. Do not offer to rebuild the strategy from scratch."
    )


def wdk_refused_the_edit(result: CommitResult) -> ToolErrorPayload | None:
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
            f"WDK_REJECTED: VEuPathDB refused the values written on {step_ids}, "
            f"so those steps still run the search and values they held, and "
            f"every other step of the strategy is untouched and was not "
            f"refused. {answers}. Bind those criteria again with values "
            f"VEuPathDB accepts, or tell the user exactly what VEuPathDB "
            f"refused and stop. Do not offer to rebuild the strategy from "
            f"scratch, and do not drop the steps it holds."
        )
        raise ModelRetry(msg)
    return tool_error(ErrorCode.WDK_ERROR, answers, stepIds=step_ids)
