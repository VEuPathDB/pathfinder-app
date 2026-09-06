"""Preprint site search client (bioRxiv, medRxiv)."""

import asyncio
import re
from typing import Literal

import httpx
from assistant_core.platform.logging import get_logger
from pydantic import JsonValue, ValidationError
from veupathdb.errors import ExternalServiceError

from pathfinder.domain.research.citations import (
    Citation,
    _new_citation_id,
    _now_iso,
)
from pathfinder.domain.research.papers import ParsedPaper, PreprintRawResult
from pathfinder.services.research.clients._base import (
    BaseClient,
    SearchResponse,
    build_response,
)
from pathfinder.services.research.utils import (
    BROWSER_USER_AGENT,
    decode_ddg_redirect,
    fetch_page_summary,
    strip_tags,
)

logger = get_logger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE_S = 2.0


async def _safe_fetch_summary(
    client: httpx.AsyncClient, url: str | None, max_chars: int
) -> str | None:
    """Fetch page summary, returning None on failure."""
    try:
        return await fetch_page_summary(client, url, max_chars=max_chars)
    except httpx.HTTPError, ValueError, TypeError, UnicodeDecodeError, OSError:
        return None


class PreprintClient(BaseClient):
    """Client for preprint site searches via DuckDuckGo.

    Preprint search has a unique signature (``site``, ``source``,
    ``include_abstract``) and a post-processing step that fetches page
    summaries, so it keeps a custom ``search`` method.  Per-item parsing
    still goes through ``_parse_item`` / ``_build_results``.
    """

    _current_source: Literal["biorxiv", "medrxiv"] = "biorxiv"

    async def search(
        self,
        query: str,
        *,
        site: str,
        source: Literal["biorxiv", "medrxiv"],
        limit: int,
        include_abstract: bool,
        abstract_max_chars: int,
    ) -> SearchResponse:
        """Search preprint sites using DuckDuckGo with retry on 429."""
        last_exc: Exception | None = None
        raw_items: list[JsonValue] = []
        for attempt in range(_MAX_RETRIES):
            try:
                raw_items = await self._fetch_raw(query, site=site, limit=limit)
                break
            except ExternalServiceError as exc:
                last_exc = exc
                if "429" in str(exc):
                    wait = _BACKOFF_BASE_S * (2**attempt)
                    logger.warning(
                        "DuckDuckGo 429, retrying",
                        attempt=attempt + 1,
                        wait_s=wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise
        else:
            service = "DuckDuckGo"
            raise ExternalServiceError(service, str(last_exc))
        self._current_source: Literal["biorxiv", "medrxiv"] = source
        results, citations = self._build_results(
            raw_items, abstract_max_chars=abstract_max_chars
        )

        if include_abstract and results:
            async with httpx.AsyncClient(
                timeout=min(self._timeout, 15.0),
                headers={
                    "User-Agent": BROWSER_USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.9",
                },
            ) as client:
                summaries = await asyncio.gather(
                    *[
                        _safe_fetch_summary(client, paper.url, abstract_max_chars)
                        for paper in results
                    ]
                )
            for paper, s in zip(results, summaries, strict=True):
                if s and s.strip():
                    paper.abstract = s.strip()
                    paper.snippet = s.strip()

        return build_response(
            query=query, source=source, results=results, citations=citations
        )

    # -- fetch -------------------------------------------------------------

    async def _fetch_raw(self, query: str, *, site: str, limit: int) -> list[JsonValue]:
        ddg_url = "https://duckduckgo.com/html/"
        params = {"q": f"site:{site} {query}"}
        headers = {"User-Agent": "pathfinder-planner/1.0"}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, headers=headers
            ) as client:
                resp = await client.get(ddg_url, params=params, follow_redirects=True)
                resp.raise_for_status()
                html = resp.text or ""
        except httpx.HTTPError as exc:
            service = "DuckDuckGo (preprint search)"
            raise ExternalServiceError(service, str(exc)) from exc

        items: list[JsonValue] = []
        for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            flags=re.IGNORECASE,
        ):
            if len(items) >= limit:
                break
            items.append(
                {
                    "_title": strip_tags(m.group(2)),
                    "_url": decode_ddg_redirect(m.group(1)),
                }
            )
        return items

    # -- parse -------------------------------------------------------------

    def _parse_item(
        self, raw: JsonValue, *, abstract_max_chars: int
    ) -> tuple[ParsedPaper, Citation] | None:
        try:
            result = PreprintRawResult.model_validate(raw)
        except ValidationError, TypeError:
            return None
        source = self._current_source

        parsed = ParsedPaper(title=result.title, url=result.url)
        citation = Citation(
            id=_new_citation_id(source),
            source=source,
            title=result.title or (result.url or f"{source} result"),
            url=result.url,
            accessed_at=_now_iso(),
        )
        return parsed, citation
