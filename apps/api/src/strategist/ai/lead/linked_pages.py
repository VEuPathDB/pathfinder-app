from __future__ import annotations

import asyncio

from pydantic_ai import RunContext
from veupathdb.wdk import find_site_links, parse_site_link
from veupathdb_mcp import records
from veupathdb_mcp.records import LinkReading, SearchTable

from strategist.ai.lead.sub_agent_tools import LeadDeps

MAX_LINKS = 3
LINK_SECONDS = 30.0

_HEADING = (
    "## Pages the message links to\n"
    "Strategist read each VEuPathDB link in the message before this turn. "
    "Answer from these readings; a link is never searched on the web."
)


async def _read(url: str) -> LinkReading:
    try:
        async with asyncio.timeout(LINK_SECONDS):
            return await records.read_site_link(url)
    except TimeoutError:
        link = parse_site_link(url)
        site = link.site_id if link else None
        return LinkReading(
            url=url,
            site_id=site,
            kind=link.kind if link else "outside",
            summary=(
                f"The link was not read: {site} did not answer within "
                f"{LINK_SECONDS:g} seconds."
            ),
        )


async def read_linked_pages(prompt: str) -> list[LinkReading]:
    return [await _read(url) for url in find_site_links(prompt)[:MAX_LINKS]]


def _table_lines(table: SearchTable) -> list[str]:
    lines = ["  Columns: " + " | ".join(c.display_name for c in table.columns)]
    lines.extend(
        f"  {row.record}: " + " | ".join(row.values[c.name] for c in table.columns)
        for row in table.rows
    )
    return lines


def pinned_linked_pages(ctx: RunContext[LeadDeps]) -> str | None:
    readings = ctx.deps.linked_pages
    if not readings:
        return None
    lines = [_HEADING]
    for reading in readings:
        lines.extend([f"- {reading.url}", f"  {reading.summary}"])
        if reading.table is not None:
            lines.extend(_table_lines(reading.table))
    return "\n".join(lines)
