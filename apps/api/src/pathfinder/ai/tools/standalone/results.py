"""Standalone result tools for pydantic-ai agents.

Provides:
- ``get_sample_records`` -- get a sample of records from an executed step
- ``get_download_url`` -- get a download URL for step results
"""

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.tool_errors import ToolErrorPayload, tool_error
from veupathdb_mcp.tool_payloads import StepDownloadUrl, gene_sample_attributes
from veupathdb_mcp.wdk.step_preview import step_download_url, step_sample_records
from veupathdb_mcp.wdk.step_results_models import SampleRecordsResult

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._result_models import (
    _validate_download_url_inputs,
    _validate_sample_inputs,
)
from pathfinder.platform.errors import AppError, ErrorCode


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
    except (AppError, VEuPathDBError, OSError) as exc:
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


async def get_sample_records(
    ctx: RunContext[AgentDeps],
    wdk_step_id: int,
    limit: int = 5,
) -> ToolReturn[SampleRecordsResult | ToolErrorPayload]:
    """Get a sample of records from an executed step.

    The step must already be built in WDK. Returns the first N records - each
    with its id plus, for gene/transcript steps, the product description, gene
    symbol, and organism - to show the user what data is available.

    Args:
        wdk_step_id: WDK step ID. The step must be built in WDK first.
        limit: Number of records to return.
    """
    _validate_sample_inputs(wdk_step_id, limit)

    session = ctx.deps.strategy_session
    graph = session.get_graph(None)
    record_type = graph.record_type if graph is not None else None
    try:
        sample = await step_sample_records(
            session.site_id,
            wdk_step_id,
            limit=limit,
            attributes=gene_sample_attributes(record_type),
        )
    except (AppError, VEuPathDBError, OSError) as exc:
        return with_summary(
            tool_error(ErrorCode.WDK_ERROR, str(exc)),
            f"No sample records from step {wdk_step_id}",
            ctx=ctx,
            status="warn",
        )
    return with_summary(
        sample,
        f"{len(sample.records)} sample records from step {wdk_step_id}",
        ctx=ctx,
    )
