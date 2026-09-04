"""Gene text lookup. Runs concurrent search strategies, then scores, deduplicates, and ranks results."""

import asyncio
from dataclasses import dataclass, field

from assistant_core.platform.logging import get_logger

from pathfinder.platform.errors import AppError
from pathfinder.services.search_rerank import (
    QueryIntent,
    ScoredResult,
    analyse_query,
    dedup_and_sort,
)

from .hydrate import hydrate_sparse_gene_results
from .organism import score_organism_match, suggest_organisms
from .result import GeneResult
from .scoring import score_gene_relevance
from .site_search import SITE_SEARCH_FETCH_LIMIT, fetch_site_search_genes
from .wdk import (
    WDK_TEXT_FIELDS_BROAD,
    WDK_TEXT_FIELDS_ID,
    WDK_WILDCARD_LIMIT,
    WdkTextResult,
    fetch_wdk_text_genes,
)

logger = get_logger(__name__)

_MIN_WORDS_FOR_MULTI_WORD = 2

_EMPTY_WDK = WdkTextResult(records=[], total_count=0)


@dataclass
class GeneSearchResult:
    """Typed result from gene text search."""

    records: list[GeneResult]
    total_count: int
    suggested_organisms: list[str] | None = field(default=None)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _run_primary_searches(
    site_id: str,
    query: str,
    *,
    is_multi_word: bool,
) -> tuple[list[GeneResult], list[str], int]:
    """Run the unrestricted and phrase-quoted site searches concurrently."""

    async def _strategy_a() -> tuple[list[GeneResult], list[str], int]:
        try:
            return await fetch_site_search_genes(
                site_id,
                query,
                limit=SITE_SEARCH_FETCH_LIMIT,
            )
        except AppError as exc:
            logger.warning(
                "Gene text lookup via site-search failed; falling back to WDK strategies",
                site_id=site_id,
                query=query,
                error=str(exc),
            )
            return [], [], 0

    async def _strategy_a_phrase() -> list[GeneResult]:
        if not is_multi_word:
            return []
        try:
            results, _, _ = await fetch_site_search_genes(
                site_id,
                f'"{query.strip()}"',
                limit=SITE_SEARCH_FETCH_LIMIT,
            )
        except AppError as exc:
            logger.warning(
                "Phrase-quoted gene search failed", query=query, error=str(exc)
            )
            return []
        else:
            return results

    (
        (primary_results, available_organisms, total_count),
        phrase_results,
    ) = await asyncio.gather(_strategy_a(), _strategy_a_phrase())

    # Phrase matches rank above unrestricted matches.
    if phrase_results:
        primary_results = phrase_results + primary_results

    return primary_results, available_organisms, total_count


async def _strategy_b(
    site_id: str,
    query: str,
    effective_organism: str | None,
) -> list[GeneResult]:
    """Run the organism-restricted site search."""
    if not effective_organism:
        return []
    try:
        results, _, _ = await fetch_site_search_genes(
            site_id,
            query,
            organisms=[effective_organism],
            limit=SITE_SEARCH_FETCH_LIMIT,
        )
    except AppError as exc:
        logger.debug(
            "Organism-restricted gene search failed (non-fatal)",
            site_id=site_id,
            organism=effective_organism,
            error=str(exc),
        )
        return []
    else:
        return results


async def _strategy_c(
    site_id: str,
    intent: QueryIntent,
    effective_organism: str | None,
    needed: int,
) -> WdkTextResult:
    """Run the WDK wildcard gene ID search."""
    if not intent.wildcard_ids or not effective_organism:
        return _EMPTY_WDK
    try:
        return await fetch_wdk_text_genes(
            site_id,
            list(intent.wildcard_ids),
            organism=effective_organism,
            text_fields=WDK_TEXT_FIELDS_ID,
            limit=max(WDK_WILDCARD_LIMIT, needed),
        )
    except AppError as exc:
        logger.debug(
            "WDK wildcard gene search failed (non-fatal)",
            site_id=site_id,
            wildcard_ids=intent.wildcard_ids,
            error=str(exc),
        )
        return _EMPTY_WDK


async def _strategy_d(
    site_id: str,
    query: str,
    explicit_organism: str | None,
    needed: int,
) -> WdkTextResult:
    """Run the WDK broad text search."""
    if not explicit_organism:
        return _EMPTY_WDK
    try:
        return await fetch_wdk_text_genes(
            site_id,
            [query],
            organism=explicit_organism,
            text_fields=WDK_TEXT_FIELDS_BROAD,
            limit=max(WDK_WILDCARD_LIMIT, needed),
        )
    except AppError as exc:
        logger.debug(
            "WDK broad text gene search failed (non-fatal)",
            site_id=site_id,
            query=query,
            organism=explicit_organism,
            error=str(exc),
        )
        return _EMPTY_WDK


async def _run_supplementary_searches(
    site_id: str,
    query: str,
    intent: QueryIntent,
    *,
    effective_organism: str | None,
    explicit_organism: str | None,
    needed: int,
) -> tuple[list[GeneResult], WdkTextResult, WdkTextResult]:
    """Run the organism, wildcard, and broad searches concurrently."""
    return await asyncio.gather(
        _strategy_b(site_id, query, effective_organism),
        _strategy_c(site_id, intent, effective_organism, needed),
        _strategy_d(site_id, query, explicit_organism, needed),
    )


async def _merge_and_rank(
    site_id: str,
    query: str,
    all_raw: list[GeneResult],
) -> list[GeneResult]:
    """Hydrate sparse results, score, deduplicate, and sort by relevance."""
    hydrated = await hydrate_sparse_gene_results(site_id, all_raw, len(all_raw))

    scored: list[ScoredResult[GeneResult]] = [
        ScoredResult(
            result=r,
            score=score_gene_relevance(query, r),
            source="site-search",
        )
        for r in hydrated
    ]
    ranked = dedup_and_sort(
        scored,
        key_fn=lambda r: r.gene_id.strip(),
    )
    return [sr.result for sr in ranked]


def _apply_organism_filter(
    results: list[GeneResult],
    *,
    organism: str | None,
    explicit_organism: str | None,
    available_organisms: list[str],
) -> tuple[list[GeneResult], list[str] | None]:
    """Filter results by organism and suggest organisms when the filter is unknown."""
    if not organism:
        return results, None

    organism_input = organism.strip()
    ol = organism_input.lower()

    if explicit_organism:
        filtered = [r for r in results if r.organism.strip().lower() == ol]
        return filtered, None

    suggested = suggest_organisms(organism_input, available_organisms)
    if not suggested:
        return [], available_organisms[:10]
    return results, suggested


def _build_response(
    *,
    paginated: list[GeneResult],
    total_count: int,
    wdk_totals: tuple[int, int],
    suggested_organisms: list[str] | None,
) -> GeneSearchResult:
    """Build the final typed response."""
    authoritative_total = max(total_count, *wdk_totals)

    return GeneSearchResult(
        records=paginated,
        total_count=authoritative_total,
        suggested_organisms=suggested_organisms,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def lookup_genes_by_text(
    site_id: str,
    query: str,
    *,
    organism: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> GeneSearchResult:
    """Search for gene records with several concurrent strategies."""
    needed = offset + limit
    is_multi_word = len(query.strip().split()) >= _MIN_WORDS_FOR_MULTI_WORD

    primary_results, available_organisms, _total_count = await _run_primary_searches(
        site_id,
        query,
        is_multi_word=is_multi_word,
    )

    intent = analyse_query(
        query, available_organisms, organism_scorer=score_organism_match
    )

    explicit_organism: str | None = None
    if organism:
        organism_lower = organism.strip().lower()
        for avail in available_organisms:
            if avail.lower() == organism_lower:
                explicit_organism = avail
                break

    effective_organism = explicit_organism or intent.implied_organism

    logger.debug(
        "Gene search intent",
        query=query,
        is_gene_id_like=intent.is_gene_id_like,
        implied_organism=intent.implied_organism,
        explicit_organism=explicit_organism,
        wildcard_ids=intent.wildcard_ids,
    )

    (
        organism_results,
        wdk_id_result,
        wdk_broad_result,
    ) = await _run_supplementary_searches(
        site_id,
        query,
        intent,
        effective_organism=effective_organism,
        explicit_organism=explicit_organism,
        needed=needed,
    )

    all_raw = (
        primary_results
        + organism_results
        + wdk_id_result.records
        + wdk_broad_result.records
    )
    results = await _merge_and_rank(site_id, query, all_raw)

    results, suggested_organisms = _apply_organism_filter(
        results,
        organism=organism,
        explicit_organism=explicit_organism,
        available_organisms=available_organisms,
    )

    paginated = results[offset : offset + limit]

    return _build_response(
        paginated=paginated,
        total_count=len(results),
        wdk_totals=(wdk_id_result.total_count, wdk_broad_result.total_count),
        suggested_organisms=suggested_organisms,
    )
