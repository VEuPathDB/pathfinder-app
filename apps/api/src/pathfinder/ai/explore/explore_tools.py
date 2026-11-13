from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from dataclasses import replace
from typing import Annotated, Any

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import Field, TypeAdapter
from pydantic_ai import ModelRetry, RunContext, Tool
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp.catalog import GetParameterOptionsResult, SearchOverviewResult

from pathfinder.ai.lead.dispatch_context import inner_context
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import catalog, catalog_discovery
from pathfinder.ai.tools.standalone.record_reads import record_columns_block
from pathfinder.ai.tools.standalone.search_reads import resolved_search
from pathfinder.domain.comparison_facts import ComparedVariant, ComparisonFact
from pathfinder.domain.strategy.reading_plan import OfferedReading
from pathfinder.services.evidence.comparisons import run_reading_count
from pathfinder.services.experiment.reading_count import ProposedReading

_GENES = "transcript"
_ARGUMENT = re.compile(r"^ {4}(\w+):")
_CONTINUED = " " * 8


class ProposedCount(CamelModel):
    label: str
    plan: str
    gene_count: int | None
    not_counted: str = ""
    also: str = ""


async def _offered(
    ctx: RunContext[LeadDeps], proposal: ProposedReading
) -> OfferedReading:
    specs = [
        await resolved_search(ctx, search, record_type=_GENES)
        for search in proposal.searches
    ]
    counted = await run_reading_count(ctx.deps.site_id, specs, proposal.root)
    return OfferedReading(
        label=proposal.title,
        plan=counted.label,
        gene_count=counted.gene_count,
        spec=counted.spec,
        not_counted=counted.not_counted,
        also=proposal.also,
    )


def _fact(offered: OfferedReading, gene_count: int) -> ComparisonFact:
    counted = ComparedVariant(label=offered.label, gene_count=gene_count)
    return ComparisonFact(variants=[counted], on_its_card=False)


async def propose_readings(
    ctx: RunContext[LeadDeps],
    readings: Annotated[list[ProposedReading], Field(min_length=1)],
) -> ToolReturn[list[ProposedCount]]:
    """Propose plans Build can build, each counted when it can be. Read-only.

    A proposal is the catalog searches of one plan and how they combine, so a
    request of two criteria is one proposal of two searches. Give each a short
    title; Strategist writes its plan from its searches, values and operators
    and shows it under the title. A
    plan of searches joined by INTERSECT, UNION or MINUS is counted from each
    search's gene ids, and no step is added. A plan it cannot count is
    proposed as not counted yet. A later call replaces this turn's proposals,
    so propose alternatives together. Offer two or more proposals on one
    ``consult_user`` card, each option labelled exactly as returned here. One
    proposal takes no card.

    Args:
        readings: One proposal at least, each one plan.
    """
    offered = [await _offered(ctx, proposal) for proposal in readings]
    labels = [reading.label for reading in offered]
    plans = [reading.plan for reading in offered]
    if len(set(labels)) < len(labels):
        msg = f"Two proposals carry the same title: {labels}. Give each plan its own."
        raise ModelRetry(msg)
    if len(set(plans)) < len(plans):
        msg = f"Two proposals state the same plan: {plans}. Propose each plan once."
        raise ModelRetry(msg)
    state = ctx.deps.state
    state.turn_markers.proposed_readings = labels
    for reading in offered:
        state.domain.offer_reading(reading)
        if reading.gene_count is not None:
            state.turn_markers.record_comparison(_fact(reading, reading.gene_count))
    proposed = [
        ProposedCount(
            label=reading.label,
            plan=reading.plan,
            gene_count=reading.gene_count,
            not_counted=reading.not_counted,
            also=reading.also,
        )
        for reading in offered
    ]
    return with_summary(
        proposed, f"{count_noun(len(proposed), 'reading')} proposed", ctx=ctx
    )


async def search_for_searches(
    ctx: RunContext[LeadDeps],
    query: str,
    record_type: str,
    keywords: list[str] | None = None,
    category: str | None = None,
    limit: int = 20,
) -> ToolReturn[list[JSONObject]]:
    found = await catalog.search_for_searches(
        inner_context(ctx), query, record_type, keywords, category, limit
    )
    block = await record_columns_block(ctx.deps.site_id, query)
    if block is None:
        return found
    rows = TypeAdapter(list[JSONObject]).validate_python(found.return_value)
    return replace(found, return_value=[*rows, block])


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
