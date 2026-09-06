"""Literature search service orchestrating multiple API clients."""

import asyncio
import collections.abc
from typing import ClassVar, Literal

import httpx
from veupathdb.errors import ExternalServiceError

from pathfinder.domain.research.citations import (
    LiteratureFilters,
    LiteratureOutputOptions,
    LiteratureSort,
    LiteratureSource,
)
from pathfinder.services.research.clients import (
    ArxivClient,
    CrossrefClient,
    EuropePmcClient,
    OpenAlexClient,
    PreprintClient,
    PubmedClient,
    SemanticScholarClient,
)
from pathfinder.services.research.clients._base import SearchResponse
from pathfinder.services.research.processing import (
    LiteratureResultData,
    LiteratureSearchResponse,
    SourcePayload,
    build_response,
    deduplicate_and_filter,
    sort_results,
)


class LiteratureSearchService:
    """Service for searching scientific literature across multiple sources."""

    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        self._timeout = timeout_seconds
        self._europepmc = EuropePmcClient(timeout_seconds=timeout_seconds)
        self._crossref = CrossrefClient(timeout_seconds=timeout_seconds)
        self._openalex = OpenAlexClient(timeout_seconds=timeout_seconds)
        self._semanticscholar = SemanticScholarClient(timeout_seconds=timeout_seconds)
        self._pubmed = PubmedClient(timeout_seconds=timeout_seconds)
        self._arxiv = ArxivClient(timeout_seconds=timeout_seconds)
        self._preprint = PreprintClient(timeout_seconds=timeout_seconds)

    async def search(
        self,
        query: str,
        *,
        source: LiteratureSource = "all",
        limit: int = 5,
        sort: LiteratureSort = "relevance",
        options: LiteratureOutputOptions | None = None,
        filters: LiteratureFilters | None = None,
    ) -> LiteratureSearchResponse:
        """Search scientific literature across multiple sources."""
        if options is None:
            options = LiteratureOutputOptions()
        if filters is None:
            filters = LiteratureFilters()

        error = self._validate_inputs(
            query,
            limit=limit,
            abstract_max_chars=options.abstract_max_chars,
            max_authors=options.max_authors,
        )
        if error is not None:
            return error

        q = query.strip()
        limit = max(1, min(int(limit or 5), 25))
        abstract_max_chars = max(
            200, min(int(options.abstract_max_chars or 2000), 10000)
        )
        max_authors = options.max_authors
        if max_authors != -1:
            max_authors = max(0, min(int(max_authors or 2), 50))
        options = LiteratureOutputOptions(
            include_abstract=options.include_abstract,
            abstract_max_chars=abstract_max_chars,
            max_authors=max_authors,
        )

        by_source = await self._dispatch_sources(
            query=q,
            source=source,
            limit=limit,
            include_abstract=options.include_abstract,
            abstract_max_chars=options.abstract_max_chars,
        )

        filtered, citations_by_key = deduplicate_and_filter(
            by_source=by_source,
            options=options,
            filters=filters,
        )

        sorted_results = sort_results(filtered, sort=sort, source=source, query=q)

        return build_response(
            query=q,
            source=source,
            sort=sort,
            options=options,
            filters=filters,
            result_data=LiteratureResultData(
                results=sorted_results,
                citations_by_key=citations_by_key,
                by_source=by_source,
                limit=limit,
            ),
        )

    def _validate_inputs(
        self,
        query: str,
        *,
        limit: int,
        abstract_max_chars: int,
        max_authors: int,
    ) -> LiteratureSearchResponse | None:
        """Return an error response if the query is empty, else None."""
        q = (query or "").strip()
        if not q:
            return LiteratureSearchResponse(
                query=q,
                source="all",
                sort="relevance",
                include_abstract=False,
                abstract_max_chars=abstract_max_chars,
                max_authors=max_authors,
                filters=LiteratureFilters(),
                results=[],
                citations=[],
            )
        return None

    _ALL_SOURCE_NAMES: ClassVar[list[str]] = [
        "europepmc",
        "crossref",
        "openalex",
        "semanticscholar",
        "pubmed",
        "arxiv",
        "biorxiv",
        "medrxiv",
    ]

    def _build_source_tasks(
        self,
        *,
        query: str,
        source: LiteratureSource,
        limit: int,
        include_abstract: bool,
        abstract_max_chars: int,
    ) -> list[tuple[str, collections.abc.Awaitable[SearchResponse]]]:
        """Build (name, coroutine) pairs for the requested sources.

        Only creates coroutines for sources that will actually be dispatched,
        avoiding unawaited-coroutine warnings when a single source is selected.
        """
        names = self._ALL_SOURCE_NAMES if source == "all" else [source]
        return [
            self._make_source_task(
                name=name,
                query=query,
                limit=limit,
                include_abstract=include_abstract,
                abstract_max_chars=abstract_max_chars,
            )
            for name in names
        ]

    def _make_source_task(
        self,
        *,
        name: str,
        query: str,
        limit: int,
        include_abstract: bool,
        abstract_max_chars: int,
    ) -> tuple[str, collections.abc.Awaitable[SearchResponse]]:
        """Create a (name, coroutine) pair for a single source."""
        standard_sources = {
            "europepmc": self._europepmc,
            "crossref": self._crossref,
            "openalex": self._openalex,
            "semanticscholar": self._semanticscholar,
            "arxiv": self._arxiv,
        }
        if name in standard_sources:
            coro = standard_sources[name].search(
                query, limit=limit, abstract_max_chars=abstract_max_chars
            )
        elif name == "pubmed":
            coro = self._pubmed.search(
                query,
                limit=limit,
                include_abstract=include_abstract,
                abstract_max_chars=abstract_max_chars,
            )
        else:
            site = "biorxiv.org" if name == "biorxiv" else "medrxiv.org"
            preprint_source: Literal["biorxiv", "medrxiv"] = (
                "biorxiv" if name == "biorxiv" else "medrxiv"
            )
            coro = self._preprint.search(
                query,
                site=site,
                source=preprint_source,
                limit=limit,
                include_abstract=include_abstract,
                abstract_max_chars=abstract_max_chars,
            )
        return (name, coro)

    async def _dispatch_sources(
        self,
        *,
        query: str,
        source: LiteratureSource,
        limit: int,
        include_abstract: bool,
        abstract_max_chars: int,
    ) -> dict[str, SourcePayload]:
        """Dispatch searches to all requested sources in parallel."""
        tasks = self._build_source_tasks(
            query=query,
            source=source,
            limit=limit,
            include_abstract=include_abstract,
            abstract_max_chars=abstract_max_chars,
        )

        async def _safe(
            name: str,
            coro: collections.abc.Awaitable[SearchResponse],
        ) -> tuple[str, SourcePayload]:
            try:
                res = await coro
                return (
                    name,
                    SourcePayload(
                        results=res.results,
                        citations=res.citations,
                    ),
                )
            except (
                httpx.HTTPError,
                ExternalServiceError,
                ValueError,
                TypeError,
                KeyError,
            ) as exc:
                return (name, SourcePayload(error=str(exc)))

        pairs = await asyncio.gather(*(_safe(name, coro) for name, coro in tasks))
        return dict(pairs)
