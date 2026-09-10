"""Standalone gene record lookup tools for pydantic-ai migration."""

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb_mcp.gene_lookup import (
    MAX_GENE_IDS,
    GeneResolveResult,
    GeneSearchResult,
    lookup_genes_by_text,
    normalize_gene_ids,
    resolve_gene_ids,
)
from veupathdb_mcp.tool_errors import ToolErrorPayload, tool_error
from veupathdb_mcp.wdk.ai_expression import (
    GeneExpressionSummary,
    get_gene_expression_summary,
)

from pathfinder.ai.graph.runtime import AgentDeps


async def lookup_gene_records(
    ctx: RunContext[AgentDeps],
    query: str,
    organism: str | None = None,
    limit: int = 10,
) -> ToolReturn[GeneSearchResult]:
    """Look up gene records by name, symbol, or description using VEuPathDB site-search.

    Use this to resolve human-readable gene names (from literature or user input)
    to VEuPathDB gene IDs.  The returned IDs can then be used as positive/negative
    controls in `run_control_tests_on_step`, `run_control_tests_on_search` or
    `optimize_search_parameters`.

    Args:
        ctx: Agent run context.
        query: Free-text query to search for gene records -- gene name, symbol,
            locus tag, product description, or keyword (e.g. 'PfAP2-G',
            'gametocyte surface antigen', 'Pfs25').
        organism: Organism filter (e.g. 'Plasmodium falciparum 3D7').
            Omit to search across all organisms on the site.
        limit: Max results to return (default 10).
    """
    found = await lookup_genes_by_text(
        ctx.deps.site_id,
        query,
        organism=organism,
        limit=max(1, min(limit, 50)),
    )
    return with_summary(
        found,
        f"{found.total_count} genes matched {query}",
        ctx=ctx,
        status="ok" if found.total_count else "empty",
    )


async def resolve_gene_ids_to_records(
    ctx: RunContext[AgentDeps],
    gene_ids: list[str],
    record_type: str = "transcript",
    search_name: str = "GeneByLocusTag",
    param_name: str = "ds_gene_ids",
) -> ToolReturn[GeneResolveResult]:
    """Resolve known gene IDs to full records (product name, organism, gene type).

    Use this to validate gene IDs or fetch metadata for IDs you already have
    (e.g. from literature).  For discovering genes by name, use `lookup_gene_records` instead.

    Args:
        ctx: Agent run context.
        gene_ids: List of gene/locus tag IDs to resolve (e.g.
            ['PF3D7_1222600', 'PF3D7_1031000']).
        record_type: WDK record type (default 'transcript').
        search_name: WDK search that accepts ID lists (default 'GeneByLocusTag').
        param_name: Parameter name for the ID list (default 'ds_gene_ids').
    """
    ids = normalize_gene_ids(gene_ids or [])
    if not ids:
        return with_summary(
            GeneResolveResult(records=[], total_count=0, error="No gene IDs provided."),
            "0 of 0 ids resolved",
            ctx=ctx,
            status="warn",
        )
    if len(ids) > MAX_GENE_IDS:
        return with_summary(
            GeneResolveResult(
                records=[],
                total_count=0,
                error=f"Too many IDs (max {MAX_GENE_IDS}). Reduce the list.",
            ),
            f"0 of {len(ids)} ids resolved",
            ctx=ctx,
            status="warn",
        )
    resolved = await resolve_gene_ids(
        ctx.deps.site_id,
        ids,
        record_type=record_type,
        search_name=search_name,
        param_name=param_name,
    )
    found = len(resolved.records)
    return with_summary(
        resolved,
        f"{found} of {len(ids)} ids resolved",
        ctx=ctx,
        status="ok" if found == len(ids) else "warn",
    )


async def get_ai_expression_summary(
    ctx: RunContext[AgentDeps],
    gene_id: str,
) -> ToolReturn[GeneExpressionSummary | ToolErrorPayload]:
    """Read the VEuPathDB site's own AI summary of one gene's expression data.

    The site generates and caches these summaries itself; this tool only reads
    what is already there. A gene the site has not summarized returns
    `unavailable_reason`, which is the answer to relay.

    Args:
        ctx: Agent run context.
        gene_id: A gene source id on this site, for example 'PF3D7_1133400'.
    """
    try:
        found = await get_gene_expression_summary(ctx.deps.site_id, gene_id)
    except (VEuPathDBError, OSError) as exc:
        return with_summary(
            tool_error(VEuPathDBErrorCode.WDK_ERROR, str(exc)),
            f"No expression summary for {gene_id}",
            ctx=ctx,
            status="warn",
        )
    if found.summary is None:
        return with_summary(
            found,
            f"No expression summary for {found.gene_id}",
            ctx=ctx,
            status="empty",
        )
    # The site states what its summary covers. The caveat goes before the
    # headline, which the summary line's length limit may cut.
    covers = " (part of the experiment set)" if found.based_on_incomplete_data else ""
    return with_summary(
        found,
        f"Expression summary for {found.gene_id}{covers}: {found.summary.headline}",
        ctx=ctx,
    )
