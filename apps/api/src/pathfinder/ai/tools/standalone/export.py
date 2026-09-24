"""Standalone export tools for pydantic-ai agents.

Provides:
- ``export_gene_set`` -- export a gene set as a downloadable file
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.types import JSONObject
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import FileChunk

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.export_models import (
    ExportResultResponse,
    GeneSetSummaryItem,
)
from pathfinder.services.evidence.gene_sets import get_gene_set, list_stored_gene_sets
from pathfinder.services.export import get_export_service


async def _available_gene_sets(
    site_id: str,
    user_id: UUID | None,
) -> list[JSONObject]:
    """Return summary of available gene sets for error messages."""
    sets = await list_stored_gene_sets(site_id=site_id, user_id=user_id)
    return [
        GeneSetSummaryItem(
            id=gs.id, name=gs.name, gene_count=len(gs.gene_ids)
        ).model_dump(by_alias=True, exclude_none=True, mode="json")
        for gs in sets[:10]
    ]


async def export_gene_set(
    ctx: RunContext[AgentDeps],
    gene_set_id: str,
    output_format: str = "csv",
) -> ToolReturn[ExportResultResponse]:
    """Export a gene set as a downloadable CSV or TXT file.

    Returns a download URL that the user can click to download the file.
    The URL expires after 10 minutes.

    Args:
        gene_set_id: PathFinder gene set ID.
        output_format: Export format: csv or txt.
    """
    if output_format not in ("csv", "txt"):
        msg = f"VALIDATION_ERROR: format must be 'csv' or 'txt', got {output_format!r}."
        raise ModelRetry(msg)

    deps = ctx.deps
    gs = await get_gene_set(gene_set_id)
    if gs is None:
        available = await _available_gene_sets(deps.site_id, deps.user_id)
        msg = (
            f"NOT_FOUND: Gene set not found: {gene_set_id!r}. "
            f"Use one of the available gene sets: {available}."
        )
        raise ModelRetry(msg)

    svc = get_export_service()
    fmt: Literal["csv", "txt"] = "txt" if output_format == "txt" else "csv"
    result = await svc.export_gene_set(gs, fmt)
    media_type = "text/csv" if output_format == "csv" else "text/plain"
    return with_summary(
        ExportResultResponse(
            download_url=result.url,
            filename=result.filename,
            format=output_format,
            item_count=len(gs.gene_ids),
            expires_in_seconds=result.expires_in_seconds,
        ),
        f"{output_format.upper()} export ready",
        ctx=ctx,
        extra=[FileChunk(url=result.url, media_type=media_type)],
    )
