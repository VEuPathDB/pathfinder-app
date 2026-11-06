from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from typing import Annotated, Any

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.types import JSONObject
from pydantic import Field, TypeAdapter
from pydantic_ai import RunContext, Tool
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp.catalog import GetParameterOptionsResult, SearchOverviewResult

from pathfinder.ai.lead.dispatch_context import inner_context
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import catalog, catalog_discovery
from pathfinder.ai.tools.standalone.search_reads import count_search
from pathfinder.services.experiment.search_reads import SearchCount
from pathfinder.services.experiment.variant_comparison import VariantInput

_ARGUMENT = re.compile(r"^ {4}(\w+):")
_CONTINUED = " " * 8
_COUNT: TypeAdapter[SearchCount] = TypeAdapter(SearchCount)


async def propose_readings(
    ctx: RunContext[LeadDeps],
    readings: Annotated[list[VariantInput], Field(min_length=2)],
) -> ToolReturn[list[SearchCount]]:
    """Count the genes each reading the site can build returns. Read-only.

    A reading is one catalog search with its parameter values and a short
    ``label``, one way the site can state what the researcher asks. Each
    search runs as an anonymous WDK report, so no step is added and the
    strategy keeps its root and its count. Offer the counted readings on one
    ``consult_user`` card, each option labelled exactly as counted here, so
    the researcher picks the reading the strategy builds.

    A search name the catalog does not list is refused with the searches the
    catalog lookup finds for it.

    Args:
        readings: Two readings at least, each a search, its parameter values
            and a short ``label`` the card shows.
    """
    counted = [
        _COUNT.validate_python((await count_search(ctx, reading)).return_value)
        for reading in readings
    ]
    return with_summary(
        counted, f"{count_noun(len(counted), 'reading')} counted", ctx=ctx
    )


async def search_for_searches(
    ctx: RunContext[LeadDeps],
    query: str,
    record_type: str,
    keywords: list[str] | None = None,
    category: str | None = None,
    limit: int = 20,
) -> ToolReturn[list[JSONObject]]:
    return await catalog.search_for_searches(
        inner_context(ctx), query, record_type, keywords, category, limit
    )


async def get_search_overview(
    ctx: RunContext[LeadDeps],
    search_name: str,
    record_type: str | None = None,
) -> ToolReturn[SearchOverviewResult | catalog_discovery.AlreadyReadNotice]:
    return await catalog_discovery.get_search_overview(
        inner_context(ctx), search_name, record_type
    )


async def get_parameter_options(
    ctx: RunContext[LeadDeps],
    search_name: str,
    parameter_id: str,
    record_type: str | None = None,
    context_values: dict[str, Any] | None = None,
    query: str | list[str] | None = None,
) -> ToolReturn[GetParameterOptionsResult | catalog_discovery.AlreadyReadNotice]:
    return await catalog_discovery.get_parameter_options(
        inner_context(ctx),
        search_name,
        parameter_id,
        record_type,
        context_values,
        query,
    )


def _described_for(
    original: Callable[..., object], wrapper: Callable[..., object]
) -> str:
    taken = set(inspect.signature(wrapper).parameters) - {"ctx"}
    kept: list[str] = []
    keep = True
    for line in (inspect.getdoc(original) or "").splitlines():
        argument = _ARGUMENT.match(line)
        if argument is not None:
            keep = argument.group(1) in taken
        elif not line.startswith(_CONTINUED):
            keep = True
        if keep:
            kept.append(line)
    return "\n".join(kept)


def catalog_reads() -> list[Tool[LeadDeps]]:
    return [
        Tool(
            search_for_searches,
            description=_described_for(
                catalog.search_for_searches, search_for_searches
            ),
        ),
        Tool(
            get_search_overview,
            description=_described_for(
                catalog_discovery.get_search_overview, get_search_overview
            ),
        ),
        Tool(
            get_parameter_options,
            description=_described_for(
                catalog_discovery.get_parameter_options, get_parameter_options
            ),
        ),
    ]
