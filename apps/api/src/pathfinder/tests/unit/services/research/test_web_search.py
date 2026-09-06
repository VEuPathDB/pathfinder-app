"""Web search should only fetch a result's page for a summary when its snippet is
weak — fetching every page (403-prone, slow) when the snippet is already good is
wasted latency."""

from __future__ import annotations

import pytest

from pathfinder.services.research import web_search
from pathfinder.services.research.web_search import WebSearchService


@pytest.mark.asyncio
async def test_only_fetches_summaries_for_weak_snippets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = WebSearchService()
    raw = [
        {
            "title": "Good",
            "href": "http://good",
            "body": "A nicely informative snippet, comfortably over the length threshold.",
        },
        {"title": "Weak", "href": "http://weak", "body": "short"},
    ]
    monkeypatch.setattr(
        WebSearchService, "_ddgs_text", staticmethod(lambda _q, _limit: raw)
    )
    fetched: list[str] = []

    async def fake_fetch(_client: object, url: str, *, max_chars: int) -> str:
        fetched.append(url)
        return "enriched summary"

    monkeypatch.setattr(web_search, "fetch_page_summary", fake_fetch)

    resp = await svc.search("q", limit=5, include_summary=True)

    assert fetched == ["http://weak"]
    weak = next(r for r in resp.results if r.title == "Weak")
    good = next(r for r in resp.results if r.title == "Good")
    assert weak.snippet == "enriched summary"
    assert good.summary is None
