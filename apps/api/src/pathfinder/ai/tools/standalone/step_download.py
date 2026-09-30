"""The tool that answers a download link for a built step's results."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp import ToolErrorPayload, tool_error
from veupathdb_mcp.tool_payloads import StepDownloadUrl
from veupathdb_mcp.wdk import step_download_url

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._result_models import (
    _validate_download_url_inputs,
)
from pathfinder.platform.errors import ErrorCode


async def get_download_url(
    ctx: RunContext[AgentDeps],
    wdk_step_id: int,
    output_format: str = "csv",
    attributes: list[str] | None = None,
) -> ToolReturn[StepDownloadUrl | ToolErrorPayload]:
    """Get a download URL for step results.

    The step must already be built in WDK. The returned URL is
    temporary and will expire after the WDK session ends.

    Args:
        wdk_step_id: WDK step ID. The step must be built in WDK first.
        output_format: Download format: csv, tab, or json.
        attributes: Specific attributes to include in the download.
    """
    _validate_download_url_inputs(wdk_step_id, output_format)

    site_id = ctx.deps.strategy_session.site_id
    try:
        url = await step_download_url(
            site_id,
            wdk_step_id,
            output_format=output_format,
            attributes=attributes,
        )
    except (VEuPathDBError, OSError) as exc:
        return _no_download(
            ctx,
            tool_error(ErrorCode.WDK_ERROR, str(exc)),
            output_format,
        )
    if not url:
        return _no_download(
            ctx,
            tool_error(
                ErrorCode.WDK_ERROR,
                "VEuPathDB did not provide a usable download URL for this step. "
                "This usually means the temporary result is still being prepared "
                "or the upstream payload shape changed.",
                wdk_step_id=wdk_step_id,
                output_format=output_format,
            ),
            output_format,
        )
    return with_summary(
        StepDownloadUrl(
            step_id=wdk_step_id,
            format=output_format,
            download_url=url,
        ),
        f"{output_format.upper()} download ready",
        ctx=ctx,
    )


def _no_download(
    ctx: RunContext[AgentDeps],
    payload: ToolErrorPayload,
    output_format: str,
) -> ToolReturn[StepDownloadUrl | ToolErrorPayload]:
    """VEuPathDB refused the download this call asked for."""
    return with_summary(
        payload,
        f"No {output_format.upper()} download for this step",
        ctx=ctx,
        status="warn",
    )
