"""The site-search stream against plasmodb, and the page it makes reachable.

A failure in the first three checks is the signal to re-record
``site_search_stream_genes.json`` with the request this module builds.
Site-search takes no credential; the gene lookup check needs one, because it
describes the streamed identifiers through WDK.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import httpx
import pytest
from veupathdb.testing.summary import DriftLog
from veupathdb.testing.wdk_fixtures import (
    FIXTURE_DIR,
    FixtureProvenance,
    RecordedWDKResponse,
)
from veupathdb.wdk.site_search_client import STREAM_MEDIA_TYPE
from veupathdb_mcp.gene_lookup import lookup_genes_by_text
from veupathdb_mcp.gene_lookup.site_search import (
    SITE_SEARCH_PAGE_LIMIT,
    fetch_site_search_genes,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

FIXTURE = FIXTURE_DIR / "site_search_stream_genes.json"
URL = "https://plasmodb.org/site-search"
BODY = {
    "searchText": "kinase",
    "restrictToProject": "PlasmoDB",
    "restrictSearchToOrganisms": ["Plasmodium falciparum 3D7"],
    "documentTypeFilter": {"documentType": "gene"},
}
COLUMNS_PER_LINE = 3
ORGANISM = "Plasmodium falciparum 3D7"
DEEP_PAGE = 300
PAGE_SIZE = 30


def _recorded() -> RecordedWDKResponse:
    return RecordedWDKResponse.model_validate_json(
        Path(FIXTURE).read_text(encoding="utf-8")
    )


async def _live() -> RecordedWDKResponse:
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0)) as client:
        response = await client.post(
            URL, json=BODY, headers={"Accept": STREAM_MEDIA_TYPE}
        )
    return RecordedWDKResponse(
        provenance=FixtureProvenance(
            site="plasmodb",
            method="POST",
            url=URL,
            status=response.status_code,
            content_type=response.headers.get("content-type", ""),
            recorded_at=datetime.datetime.now(tz=datetime.UTC).date().isoformat(),
            reads=_recorded().provenance.reads,
        ),
        text=response.text,
    )


async def test_the_stream_still_answers_in_the_recorded_media_type(
    drift_log: DriftLog,
) -> None:
    recorded = _recorded()
    live = await _live()

    drift_log.record(
        site="plasmodb",
        check="site-search-stream-content-type",
        subject="site_search_stream_genes",
        expected=f"{recorded.provenance.status} {recorded.provenance.content_type}",
        observed=f"{live.provenance.status} {live.provenance.content_type}",
    )
    assert (live.provenance.status, live.provenance.content_type) == (
        recorded.provenance.status,
        recorded.provenance.content_type,
    )


async def test_every_streamed_line_still_carries_three_columns(
    drift_log: DriftLog,
) -> None:
    """The declared media type is ND_JSON and the payload is tab separated."""
    live = await _live()
    widths = {
        len(line.split("\t")) for line in live.raw_text().splitlines() if line.strip()
    }

    drift_log.record(
        site="plasmodb",
        check="site-search-stream-columns",
        subject="site_search_stream_genes",
        expected=COLUMNS_PER_LINE,
        observed=max(widths),
    )
    assert widths == {COLUMNS_PER_LINE}


async def test_the_stream_still_reaches_the_whole_match_set(
    drift_log: DriftLog,
) -> None:
    """The paged form stops at fifty; this query matches many more than that."""
    recorded = _recorded()
    live = await _live()
    expected = [line.split("\t")[0] for line in recorded.raw_text().splitlines()]
    observed = [line.split("\t")[0] for line in live.raw_text().splitlines()]

    drift_log.record(
        site="plasmodb",
        check="site-search-stream-record-count",
        subject="site_search_stream_genes",
        expected=len(expected),
        observed=len(observed),
    )
    assert observed == expected


async def test_a_page_past_the_paged_ceiling_returns_described_records(
    wdk_identity: str, drift_log: DriftLog
) -> None:
    """The paged form stops at fifty, so record 300 needs the stream."""
    del wdk_identity
    _, _, matched = await fetch_site_search_genes(
        "plasmodb", "kinase", organisms=[ORGANISM], limit=1
    )
    first = await lookup_genes_by_text(
        "plasmodb", "kinase", organism=ORGANISM, offset=0, limit=PAGE_SIZE
    )
    deep = await lookup_genes_by_text(
        "plasmodb", "kinase", organism=ORGANISM, offset=DEEP_PAGE, limit=PAGE_SIZE
    )
    deep_ids = [record.gene_id for record in deep.records]

    drift_log.record(
        site="plasmodb",
        check="gene-lookup-deep-page",
        subject=f"kinase offset={DEEP_PAGE}",
        expected=PAGE_SIZE,
        observed=len(deep_ids),
    )
    assert DEEP_PAGE > SITE_SEARCH_PAGE_LIMIT
    assert len(set(deep_ids)) == PAGE_SIZE
    assert set(deep_ids).isdisjoint({r.gene_id for r in first.records})
    assert {record.organism for record in deep.records} == {ORGANISM}
    assert first.total_count == deep.total_count == matched
