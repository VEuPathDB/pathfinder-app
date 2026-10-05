"""Lead tools that read one catalog search without a step: how many genes it
returns, and which of a list of gene ids it holds."""

from __future__ import annotations

import re

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import VagueSearchQueryError

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.ai.tools.standalone._variant_targets import (
    reject_combine_variants,
    resolved_variants,
)
from pathfinder.domain.membership_facts import MembershipFact
from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.strategy.text_expression import unquoted_phrase_refusal
from pathfinder.services.evidence.comparisons import (
    run_search_count,
    run_search_membership,
)
from pathfinder.services.experiment.search_reads import SearchCount, SearchMembership
from pathfinder.services.experiment.variant_comparison import (
    VariantInput,
    VariantSpec,
)
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.services.strategies.record_classes import search_record_types

_LOOKUP_LIMIT = 5
_WORD_START = re.compile(r"(?<=[a-z])(?=[A-Z])")


async def _refuse_an_unlisted_search(
    ctx: RunContext[LeadDeps], search: VariantInput
) -> None:
    """Raises ModelRetry for a search the catalog does not list, with the
    searches the catalog lookup finds for its name."""
    site_id = ctx.deps.site_id
    name = search.search_name
    if name in await search_record_types(site_id, [name]):
        return
    query = _WORD_START.sub(" ", name)
    try:
        found = await catalog.search_for_searches(
            site_id, "transcript", query, keywords=[name], limit=_LOOKUP_LIMIT
        )
    except VagueSearchQueryError:
        found = []
    ctx.deps.state.turn_markers.catalog_looked_up = True
    unlisted = f"{site_id} lists no search {name} ({search.label})."
    if not found:
        msg = (
            f"{unlisted} The catalog lookup for '{query}' finds no search, so "
            f"{site_id} has no search of that name."
        )
        raise ModelRetry(msg)
    named = ", ".join(f"{m.name} ({m.display_name})" for m in found)
    msg = (
        f"{unlisted} The catalog lookup for '{query}' finds: {named}. Call again "
        f"with one of these names. A search is absent from {site_id} only when "
        "this lookup finds none."
    )
    raise ModelRetry(msg)


def _refuse_an_unquoted_phrase(ctx: RunContext[LeadDeps], search: VariantInput) -> None:
    """Raises ModelRetry for a text term of several words sent unquoted when
    this turn's message asks for the phrase."""
    for name, value in search.parameters.items():
        match value:
            case StringValue(value=text):
                refusal = unquoted_phrase_refusal(
                    name, search.search_name, text, [ctx.deps.state.user_prompt]
                )
                if refusal is not None:
                    raise ModelRetry(refusal)
            case _:
                continue


async def _resolved(ctx: RunContext[LeadDeps], search: VariantInput) -> VariantSpec:
    """The search under the record type the catalog lists it under, with each
    value as the entry its vocabulary names."""
    reject_combine_variants([search])
    _refuse_an_unquoted_phrase(ctx, search)
    await _refuse_an_unlisted_search(ctx, search)
    specs = await resolved_variants(ctx.deps.runtime.strategy_session, [search])
    return specs[0]


async def count_search(
    ctx: RunContext[LeadDeps], search: VariantInput
) -> ToolReturn[SearchCount]:
    """Count the genes one catalog search returns. Read-only.

    This answers "how many genes would this search find" for a search the
    strategy runs or not. The search runs as an anonymous WDK report, so no
    step is added and the strategy keeps its root and its count. The answer
    names the wire value of each parameter it ran; a pick left out runs at
    the site's default. The count renders as ``[compare:<label>]``.

    A search name the catalog does not list is refused with the searches the
    catalog lookup finds for it. A search is absent only when that lookup
    finds none.

    Args:
        search: The search, its parameter values and a short ``label``.
    """
    spec = await _resolved(ctx, search)
    counted = await run_search_count(ctx.deps.site_id, spec)
    ctx.deps.state.turn_markers.record_comparison(counted.fact())
    return with_summary(
        counted, f"{counted.label}: {counted.gene_count:,} genes", ctx=ctx
    )


def _shown_record_ids(deps: LeadDeps) -> list[str]:
    """The records this turn's facts list, else those the conversation last showed."""
    facts = turn_facts(deps)
    return facts.record_ids() or [s.record_id for s in facts.shown_before]


async def genes_in_search(
    ctx: RunContext[LeadDeps],
    search: VariantInput,
    gene_ids: list[str] | None = None,
) -> ToolReturn[SearchMembership]:
    """Say which of a list of gene ids one catalog search holds. Read-only.

    This answers "which of these genes also have <property>": the search runs
    as an anonymous WDK report over its whole result, and no step is added.
    A gene record does not show every search's attribute, so a record read
    does not answer it. ``held`` and ``notHeld`` keep the asked order;
    ``unread`` holds ids past the capped read, which the search may hold.
    Each gene renders as ``[record:<id>]``, the asked genes as
    ``[compare:asked genes]`` and the genes held as
    ``[compare:asked genes,<label>:shared]``.

    Args:
        search: The search, its parameter values and a short ``label``.
        gene_ids: The gene ids to check. Leave it out for the records this
            conversation showed last.
    """
    asked = list(dict.fromkeys(gene_ids or _shown_record_ids(ctx.deps)))
    if not asked:
        msg = (
            "No gene ids were given, and this conversation has shown no record. "
            "Name the gene ids to check."
        )
        raise ModelRetry(msg)
    spec = await _resolved(ctx, search)
    site_id = ctx.deps.site_id
    membership = await run_search_membership(site_id, spec, asked)
    markers = ctx.deps.state.turn_markers
    markers.record_membership(
        MembershipFact(
            search_label=spec.label,
            records=[
                ListedRecord(record_id=g, url=gene_record_url(site_id, g))
                for g in asked
            ],
            held=membership.held,
            unread=membership.unread,
        )
    )
    markers.record_comparison(membership.fact())
    return with_summary(
        membership,
        f"{spec.label}: {len(membership.held)} of {len(asked)} genes held",
        ctx=ctx,
    )
