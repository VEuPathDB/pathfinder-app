from __future__ import annotations

import asyncio

import pytest
from veupathdb_mcp import records
from veupathdb_mcp.record_fields import ColumnInfo
from veupathdb_mcp.records import LinkReading, SearchTable, TableRow

from pathfinder.ai.lead import linked_pages
from pathfinder.ai.lead.linked_pages import pinned_linked_pages, read_linked_pages
from pathfinder.tests._support.run_context import lead_run_context

PORTAL_APP = "https://qa.veupathdb.org/veupathdb.qa/app"
GENOMES = f"{PORTAL_APP}/search/organism/GenomeDataTypes/result"


def _genome_reading(url: str) -> LinkReading:
    return LinkReading(
        url=url,
        site_id="veupathdb",
        kind="search_result",
        summary="The link runs GenomeDataTypes on veupathdb.",
        table=SearchTable(
            site_id="veupathdb",
            record_type="organism",
            search_name="GenomeDataTypes",
            search_display_name="Organisms: Genome Info and Stats",
            table=None,
            columns=[
                ColumnInfo(name="genecount", display_name="Genes"),
                ColumnInfo(name="busco_genome", display_name="BUSCO Genomic"),
            ],
            total_records=831,
            matched_rows=1,
            rows=[
                TableRow(
                    record="Edhazardia aedis USNM 41457",
                    values={
                        "genecount": "4262",
                        "busco_genome": "C: 97.4%[S: 96.5%,D: 0.9%],F: 0.5%,M: 2.1%,n:425",
                    },
                )
            ],
            note="Showing all 1 rows.",
        ),
    )


@pytest.fixture
def read_urls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    async def read(url: str) -> LinkReading:
        asked.append(url)
        return _genome_reading(url)

    monkeypatch.setattr(records, "read_site_link", read)
    return asked


async def test_each_site_link_in_the_message_is_read_once(read_urls: list[str]) -> None:
    prompt = f"can you read this web page {GENOMES} and again ({GENOMES})."

    readings = await read_linked_pages(prompt)

    assert read_urls == [GENOMES]
    assert [reading.url for reading in readings] == [GENOMES]


async def test_a_message_reads_three_links_at_most(read_urls: list[str]) -> None:
    links = [f"{PORTAL_APP}/record/gene/PF3D7_{n}" for n in range(5)]

    await read_linked_pages(" ".join(links))

    assert read_urls == links[:3]


async def test_a_message_without_a_site_link_reads_nothing(
    read_urls: list[str],
) -> None:
    assert await read_linked_pages("list P. falciparum genomes and BUSCO") == []
    assert read_urls == []


async def test_a_link_that_does_not_answer_in_time_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow(url: str) -> LinkReading:
        await asyncio.sleep(1)
        return _genome_reading(url)

    monkeypatch.setattr(records, "read_site_link", slow)
    monkeypatch.setattr(linked_pages, "LINK_SECONDS", 0.01)

    [reading] = await read_linked_pages(GENOMES)

    assert (reading.url, reading.site_id, reading.table) == (GENOMES, "veupathdb", None)
    assert reading.summary == (
        "The link was not read: veupathdb did not answer within 0.01 seconds."
    )


def test_the_pin_carries_each_reading_and_its_rows() -> None:
    ctx = lead_run_context()
    ctx.deps.linked_pages = [_genome_reading(GENOMES)]

    pinned = pinned_linked_pages(ctx)

    assert pinned == (
        "## Pages the message links to\n"
        "Strategist read each VEuPathDB link in the message before this turn. "
        "Answer from these readings; a link is never searched on the web.\n"
        f"- {GENOMES}\n"
        "  The link runs GenomeDataTypes on veupathdb.\n"
        "  Columns: Genes | BUSCO Genomic\n"
        "  Edhazardia aedis USNM 41457: 4262 | "
        "C: 97.4%[S: 96.5%,D: 0.9%],F: 0.5%,M: 2.1%,n:425"
    )


def test_a_turn_with_no_link_pins_nothing() -> None:
    assert [pinned_linked_pages(lead_run_context())] == [None]
