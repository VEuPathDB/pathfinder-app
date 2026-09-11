"""Standalone execution tools for pydantic-ai agents.

Provides:
- ``get_estimated_size`` -- get result count for a built step
"""

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp import ToolErrorPayload, tool_error
from veupathdb_mcp.wdk import get_estimated_size_for_site

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._result_models import EstimatedSizeResult
from pathfinder.platform.errors import ErrorCode


async def get_estimated_size(
    ctx: RunContext[AgentDeps],
    wdk_step_id: int,
    wdk_strategy_id: int | None = None,
) -> ToolReturn[EstimatedSizeResult | ToolErrorPayload]:
    """Get the result count for a built step.

    The step must already be built in WDK (via auto-build or import).
    For imported WDK strategies, provide wdk_strategy_id.

    Args:
        wdk_step_id: WDK step ID. The step must be built in WDK first.
        wdk_strategy_id: WDK strategy ID (required for imported strategies).
    """
    try:
        result = await get_estimated_size_for_site(
            ctx.deps.strategy_session.site_id, wdk_step_id, wdk_strategy_id
        )
    except (VEuPathDBError, OSError) as e:
        message = str(e)
        if wdk_strategy_id is None:
            message = f"{message} (try providing wdk_strategy_id)"
        return with_summary(
            tool_error(ErrorCode.WDK_ERROR, message),
            f"Step {wdk_step_id} has no readable size",
            ctx=ctx,
            status="warn",
        )
    return with_summary(
        EstimatedSizeResult(step_id=result.step_id, count=result.count),
        f"Step {wdk_step_id}: {result.count:,} records",
        ctx=ctx,
        status="ok" if result.count else "empty",
    )
