"""Exit-ramp tool for the constrained-toolset architecture.

Most planning/execution/verification tool args are constrained to the
universe discovery committed to. That keeps the model from hallucinating
identifiers — but it also means the model is **trapped** if it realises
mid-phase that it needs a search/parameter discovery missed. This tool is
the explicit out: an unconstrained ``search_name: str`` argument that
inspects the catalog inline AND logs a "constraint deviation" event so we
can see when downstream phases rely on it.

Usage from the model's POV: "the planner needs ``GenesByMicroarray`` but
discovery only selected ``GenesByGoTerm`` — call ``request_search_inspection
("GenesByMicroarray", "need microarray data for cross-condition check")``."

The tool runs the same ``get_search_overview`` flow discovery uses, so on
return ``discovered_searches`` is updated and downstream constrained tools
will accept the new search name on their next call.
"""

from __future__ import annotations

from assistant_core.platform.logging import get_logger
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp.catalog.overview_formatting import SearchOverviewResult

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.catalog_discovery import (
    AlreadyReadNotice,
    get_search_overview,
)
from pathfinder.platform.uuid_utils import format_uuid

logger = get_logger(__name__)


async def request_search_inspection(
    ctx: RunContext[AgentDeps],
    search_name: str,
    why: str,
    record_type: str | None = None,
) -> ToolReturn[SearchOverviewResult | AlreadyReadNotice]:
    """Request inline inspection of a search outside discovery's commit set.

    Use sparingly — discovery is meant to surface every search the
    investigation needs. If you find yourself reaching for this tool
    often during planning or execution, the discovery phase missed
    something and the supervisor should hand back to discovery.

    Args:
        search_name: WDK search urlSegment to inspect now. Logged as a
            constraint deviation regardless of whether it succeeds.
        why: One sentence explaining what the planner / executor /
            verifier needs that the existing discovered set can't
            provide. Required so post-mortem can identify the gap in
            discovery's instructions.
        record_type: Optional record type override (auto-resolved when
            omitted, same as ``get_search_overview``).
    """
    logger.warning(
        "constraint deviation: phase requested out-of-band search inspection",
        search_name=search_name,
        why=why,
        site_id=ctx.deps.site_id,
        conversation_id=format_uuid(ctx.deps.conversation_id),
    )
    return await get_search_overview(
        ctx,
        search_name=search_name,
        record_type=record_type,
    )
