"""Agent tools for catalog discovery: record types, searches, categories,
transforms, phyletic codes, the OrthoMCL expressions built from them, and
example public strategies."""

from collections.abc import Sequence
from typing import Literal, cast

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import ConfigDict, model_validator
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb_mcp import ToolErrorPayload, catalog, tool_payloads
from veupathdb_mcp.catalog import (
    UNIVERSAL_SEARCHES,
    CladeOnlyExpression,
    ProteinCountComparison,
    SearchMatch,
    VagueSearchQueryError,
)
from veupathdb_mcp.tool_payloads import SearchListing, TransformListing

from pathfinder.ai.agents.state import CatalogHit, CatalogRead
from pathfinder.ai.capabilities.site_reads import read_in_time
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._catalog_elsewhere import (
    joined,
    own_search_names,
    rank_other_sites,
    with_other_sites,
)

logger = get_logger(__name__)

# Mirrors the tool server's _MIN_SEMANTIC_SIM (0.35) and moves with it. A result
# whose closest scored hit is under it says so; the number changes that
# sentence and never refuses a search.
_FAINT_MATCH = 0.35

PROTEIN_COMPARISON_MAX_CALL_SECONDS = 120


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
    is a note that says which. An ``otherSites`` entry, when present, is last:
    experiments on other VEuPathDB sites, each labelled with its site. None of
    them can be bound here; read_experiment reads one.

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
    note = _ranking_note(matches, ctx.deps.site_id, query)
    # The reader's number is what the query ranked, not the universal searches
    # every result list carries.
    found = len(matches)
    seen = {m.name for m in matches}
    answered = [*matches, *(u for u in UNIVERSAL_SEARCHES if u.name not in seen)]
    results: list[JSONObject] = cast(
        "list[JSONObject]", [m.to_dict() for m in answered]
    )
    ctx.deps.record_catalog_read(
        CatalogRead(
            tool_call_id=ctx.tool_call_id or "",
            tool="search_for_searches",
            query=query,
            record_type=record_type,
            hits=[
                CatalogHit(
                    name=m.name,
                    display_name=m.display_name,
                    description=m.description,
                    record_type=m.record_type,
                    similarity=m.semantic_similarity,
                )
                for m in answered
            ],
        )
    )
    if note is not None:
        results.insert(0, {"note": note})
    # Other sites' experiments follow the own-site answer and bind nothing.
    state = ctx.deps.agent_state
    elsewhere = await rank_other_sites(ctx, query)
    results = with_other_sites(results, elsewhere, state.elsewhere, ctx.deps.site_id)
    shown = state.record_elsewhere(
        (match.card for match in elsewhere),
        await own_search_names(ctx.deps.site_id) if elsewhere else frozenset(),
    )
    summary = f"{found} searches"
    if shown:
        summary += f", experiments on {joined([s.site_id for s in shown])}"
    return with_summary(
        results,
        summary,
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


def record_a_listing(
    ctx: RunContext[AgentDeps],
    tool: Literal["list_searches", "list_transforms"],
    record_type: str,
    listed: Sequence[SearchListing | TransformListing],
) -> None:
    """Record a listing the model was shown, in its order and with no scores."""
    ctx.deps.record_catalog_read(
        CatalogRead(
            tool_call_id=ctx.tool_call_id or "",
            tool=tool,
            record_type=record_type,
            hits=[
                CatalogHit.model_validate(
                    listing.model_dump() | {"record_type": record_type}
                )
                for listing in listed
            ],
        )
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
    shown = [listing for listing in listings if listing.name]
    record_a_listing(ctx, "list_searches", record_type, shown)
    names = [listing.name for listing in shown]
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
    record_a_listing(ctx, "list_transforms", record_type, transforms)
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
    """Look up phyletic genome and clade codes by name.

    On a genomics site the codes are for GenesByOrthologPattern: put a code or
    its label in included_species or excluded_species; profile_pattern is
    derived from those two lists and is never written by hand. On OrthoMCL the
    codes are for phyletic_expression: each match carries its code, label,
    leaf and genomes, the number of genomes under a clade, and species groups
    the matched genomes by species, so the strains of one species are several
    genomes.

    Args:
        ctx: Agent run context.
        query: Species or clade name to search for (e.g., 'falciparum', 'human',
            'Apicomplexa'). A code with leaf=false is a clade and selects every
            genome under it.
        record_type: Record type. Defaults to 'transcript'. record_type is read
            only on the genomics sites.
    """
    codes = await catalog.lookup_phyletic_codes(ctx.deps.site_id, record_type, query)
    return with_summary(
        codes,
        f"{_PhyleticLookup.model_validate(codes).total} phyletic codes for {query}",
        ctx=ctx,
    )


async def build_protein_count_comparison(
    ctx: RunContext[AgentDeps],
    genome_a: str,
    genome_b: str,
    reverse: bool = False,
) -> ToolReturn[ProteinCountComparison]:
    """Build the OrthoMCL phyletic_expression for the groups in which genome A
    holds more proteins than genome B, and count the groups it returns.

    The expression is B=0 AND A>=1 OR B=1 AND A>=2 OR ... OR B=K AND A>=K+1,
    where K is the smallest count for which B>=K+1 returns no group. K is read
    from the site with at most 15 count reports. Each ladder gives its
    expression, the groups it returns, and length, its characters; the
    parameter has no length limit, so bind the expression whole. A group with
    as many proteins in both genomes is in neither ladder. A genome B with 1024
    or more proteins in one group is refused.

    Args:
        ctx: Agent run context.
        genome_a: Genome A, one genome code (leaf=true in lookup_phyletic_codes).
        genome_b: Genome B, one genome code (leaf=true in lookup_phyletic_codes).
        reverse: Also build the ladder of the groups in which genome B holds
            more proteins than genome A.
    """
    try:
        comparison = await read_in_time(
            "build_protein_count_comparison",
            f"the protein counts of {genome_a} and {genome_b}",
            catalog.compare_protein_counts(
                ctx.deps.site_id, genome_a, genome_b, reverse=reverse
            ),
            deadline=PROTEIN_COMPARISON_MAX_CALL_SECONDS,
        )
    except ValidationError as exc:
        raise ModelRetry(exc.detail or exc.title) from exc
    return with_summary(
        comparison,
        "; ".join(
            f"{ladder.groups} groups with more proteins in {ladder.more} than "
            f"{ladder.fewer}"
            for ladder in comparison.ladders
        ),
        ctx=ctx,
    )


async def build_clade_only_expression(
    ctx: RunContext[AgentDeps],
    clade: list[str],
    within: list[str] | None = None,
) -> ToolReturn[CladeOnlyExpression]:
    """Build the OrthoMCL phyletic_expression for the groups present in a clade
    L and in no genome outside it, and count the groups it returns.

    The expression is L>=1T AND C=0T, with C every genome outside L, written
    from the site's taxonomy: a clade code for each whole clade outside L and a
    genome code for the rest. With within, a clade M that holds every genome of
    L, C is every genome outside M, so the groups may also hold proteins
    elsewhere in M. The result gives expression, groups, length, its
    characters, genomes, the genome codes of L, and outside, the number of
    genomes C covers; the parameter has no length limit, so bind the expression
    whole. For a clade X whose genomes must hold no protein, write L>=1T AND
    X=0T instead.

    Args:
        ctx: Agent run context.
        clade: L, one clade code, or the genome codes of a group with no clade
            code of its own, such as a genus, from lookup_phyletic_codes.
        within: M, the codes of a clade that holds every genome of L; every
            genome outside M must hold no protein.
    """
    try:
        built = await catalog.clade_only_expression(ctx.deps.site_id, clade, within)
    except ValidationError as exc:
        raise ModelRetry(exc.detail or exc.title) from exc
    return with_summary(
        built,
        f"{built.groups} groups with a protein in {len(built.genomes)} genomes and "
        f"none in {built.outside} others",
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
