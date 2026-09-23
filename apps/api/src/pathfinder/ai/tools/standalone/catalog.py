"""Agent tools for catalog discovery: record types, searches, categories,
transforms, phyletic codes, and example public strategies."""

from typing import cast

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import ConfigDict, model_validator
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp import ToolErrorPayload, catalog, tool_payloads
from veupathdb_mcp.catalog import UNIVERSAL_SEARCHES, SearchMatch, VagueSearchQueryError

from pathfinder.ai.graph.runtime import AgentDeps

logger = get_logger(__name__)

# Mirrors the tool server's _MIN_SEMANTIC_SIM (0.35) and moves with it. A result
# whose closest scored hit is under it says so; the number changes that
# sentence and never refuses a search.
_FAINT_MATCH = 0.35


class _PhyleticLookup(CamelModel):
    """How many codes a phyletic lookup matched."""

    model_config = ConfigDict(extra="ignore")

    total: int = 0

    @model_validator(mode="before")
    @classmethod
    def _mapping_only(cls, raw: object) -> object:
        """An error payload carries no matches, so it counts as none."""
        return raw if isinstance(raw, dict) else {}


async def get_record_types(
    ctx: RunContext[AgentDeps],
) -> ToolReturn[list[dict[str, str]]]:
    """List available record types for this site."""
    record_types = await catalog.get_record_types(ctx.deps.site_id)
    return with_summary(
        [
            {
                "name": rt.name,
                "displayName": rt.display_name,
                "description": rt.description,
            }
            for rt in record_types
        ],
        f"{len(record_types)} record types",
        ctx=ctx,
    )


async def search_for_searches(
    ctx: RunContext[AgentDeps],
    query: str,
    record_type: str = "transcript",
    keywords: list[str] | None = None,
    category: str | None = None,
    limit: int = 20,
) -> ToolReturn[list[JSONObject]]:
    """Find WDK searches by description and/or keywords.

    Returns a ranked list with name, displayName, description, category and
    what the search returns. ``relevance`` is relative to the best hit, so the
    top hit reads 1.0 however weak it is. ``semanticSimilarity`` is the
    absolute cosine of the query against the search: read it to tell a match
    from the best of nothing. When no search states the query closely, when
    nothing matched, or when the ranking is by keyword only, the first entry
    is a note that says which.

    Args:
        ctx: Agent run context.
        query: Descriptive natural language query about what you're looking for.
            Be as descriptive as possible for better results.
            Example: 'gametocyte RNA-Seq differential expression DESeq analysis'
        record_type: Record type to search. Defaults to 'transcript' (gene searches).
            Use 'snp', 'pathway', 'compound', etc. for non-gene searches.
        keywords: Optional exact identifiers to match against search names (urlSegment).
            These get massive score boost. Extract from dataset names, search
            name fragments, or organism codes mentioned in the user's request.
            Example: ['Su_strand_specific', 'Percentile', 'pfal3D7']
        category: Filter to a specific search subcategory from the site ontology.
        limit: Max results to return.
    """
    try:
        matches = await catalog.search_for_searches(
            ctx.deps.site_id,
            record_type=record_type,
            query=query,
            keywords=keywords or [],
            category=category,
            limit=limit,
        )
    except VagueSearchQueryError as exc:
        return with_summary(
            [cast("JSONObject", exc.rejection.model_dump(exclude_none=True))],
            f"The query {query} is too vague to rank searches",
            ctx=ctx,
            status="warn",
        )
    results: list[JSONObject] = cast("list[JSONObject]", [m.to_dict() for m in matches])
    note = _ranking_note(matches, ctx.deps.site_id, query)

    # The reader's number is what the query ranked, not the universal searches
    # every result list carries.
    found = len(results)

    seen = {str(r["name"]) for r in results}
    results.extend(
        cast("JSONObject", u.to_dict())
        for u in UNIVERSAL_SEARCHES
        if u.name not in seen
    )

    ctx.deps.agent_state.record_catalog_searches(
        [str(r["name"]) for r in results if "name" in r]
    )
    if note is not None:
        results.insert(0, {"note": note})

    return with_summary(
        results,
        f"{found} searches",
        ctx=ctx,
        status="ok" if found else "empty",
    )


def _ranking_note(matches: list[SearchMatch], site_id: str, query: str) -> str | None:
    """The sentence that states how close the ranking came, or None when close.

    A hit the index did not score says nothing about closeness, so only the
    scored hits are measured against the floor.
    """
    scored = [
        m.semantic_similarity for m in matches if m.semantic_similarity is not None
    ]
    best = max(scored, default=None)
    logger.info(
        "Searches ranked",
        query=query,
        hits=len(matches),
        scored=len(scored),
        best_similarity=best,
    )
    if not matches:
        return (
            f"No search on {site_id} matched '{query}'; only the searches every "
            f"site offers are listed."
        )
    if best is None:
        return (
            "The semantic index scored none of these results; the ranking is by "
            "keyword only."
        )
    if best < _FAINT_MATCH:
        return (
            f"No search on {site_id} states '{query}' closely; the nearest are listed."
        )
    return None


async def browse_search_categories(
    ctx: RunContext[AgentDeps],
    record_type: str = "transcript",
) -> ToolReturn[list[JSONObject]]:
    """Browse available search categories and their example searches.

    Call this BEFORE search_for_searches to see what categories and search
    names exist on this site.  Returns categories grouped by the site's
    ontology, each with a count and up to 5 example display names.
    Use the category key as the 'category' parameter in search_for_searches.
    Use the example display names to formulate better search queries.

    Args:
        ctx: Agent run context.
        record_type: Record type. Defaults to 'transcript' (gene searches).
            Use 'snp', 'pathway', etc. for non-gene searches.
    """
    categories = await tool_payloads.list_search_categories(
        ctx.deps.site_id, record_type
    )
    return with_summary(
        [category.model_dump(by_alias=True) for category in categories],
        f"{len(categories)} categories",
        ctx=ctx,
    )


async def list_searches(
    ctx: RunContext[AgentDeps],
    record_type: str = "transcript",
) -> ToolReturn[list[str]]:
    """List the search names of a record type, and nothing else.

    A site publishes thousands of searches, so the listing carries names only
    and stays inside one agent's history. Use search_for_searches for the
    display name, the description and the ranking.

    Args:
        ctx: Agent run context.
        record_type: Record type. Defaults to 'transcript' (gene searches).
    """
    listings = await tool_payloads.list_search_listings(ctx.deps.site_id, record_type)
    names = [listing.name for listing in listings if listing.name]
    ctx.deps.agent_state.record_catalog_searches(names)
    return with_summary(
        names,
        f"{len(names)} searches on {record_type}",
        ctx=ctx,
    )


async def list_transforms(
    ctx: RunContext[AgentDeps],
    record_type: str = "transcript",
) -> ToolReturn[list[JSONObject]]:
    """List available transform and combine operations (with descriptions).

    Returns searches that chain onto a previous step's results -- such as
    ortholog transforms, weight filters, span logic, and boolean combines.

    Args:
        ctx: Agent run context.
        record_type: Record type. Defaults to 'transcript'.
    """
    transforms = await tool_payloads.list_transform_listings(
        ctx.deps.site_id, record_type
    )
    ctx.deps.agent_state.record_catalog_searches(
        [transform.name for transform in transforms]
    )
    return with_summary(
        [transform.model_dump(by_alias=True) for transform in transforms],
        f"{len(transforms)} transforms on {record_type}",
        ctx=ctx,
    )


async def lookup_phyletic_codes(
    ctx: RunContext[AgentDeps],
    query: str,
    record_type: str = "transcript",
) -> ToolReturn[JSONObject | ToolErrorPayload]:
    """Look up phyletic species/clade codes by name for GenesByOrthologPattern.

    Returns {code, label, leaf} triples. Put a code or its label in
    included_species or excluded_species; profile_pattern is derived from those
    two lists and is never written by hand.

    Args:
        ctx: Agent run context.
        query: Species or clade name to search for (e.g., 'falciparum', 'human',
            'Apicomplexa'). A code with leaf=false is a clade and selects every
            species under it.
        record_type: Record type. Defaults to 'transcript'.
    """
    codes = await catalog.lookup_phyletic_codes(ctx.deps.site_id, record_type, query)
    return with_summary(
        codes,
        f"{_PhyleticLookup.model_validate(codes).total} phyletic codes for {query}",
        ctx=ctx,
    )


async def search_example_plans(
    ctx: RunContext[AgentDeps],
    query: str,
    limit: int = 3,
) -> ToolReturn[list[JSONObject]]:
    """Retrieve relevant public strategies from WDK, ranked by semantic
    similarity to the query (falls back to lexical token overlap when the
    embedding API is unreachable).

    Args:
        ctx: Agent run context.
        query: User goal / query to match against public strategies.
        limit: Max number of results to return.
    """
    try:
        plans = await tool_payloads.rank_example_plans(ctx.deps.site_id, query, limit)
    except (VEuPathDBError, OSError) as exc:
        logger.warning("Failed to fetch public strategies", error=str(exc))
        return with_summary([], "0 example plans", ctx=ctx, status="warn")
    return with_summary(plans, f"{len(plans)} example plans", ctx=ctx)
