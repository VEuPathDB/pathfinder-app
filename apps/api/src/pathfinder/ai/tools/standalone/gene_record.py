"""The tool that reads one gene's record, for the Lead and for a check."""

from __future__ import annotations

from typing import Protocol

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.services.gene_records import read
from pathfinder.services.gene_records.read import GeneRecordSummary


class GeneRecordReader(Protocol):
    """What a record read needs of its caller: the site and the turn's reads."""

    @property
    def site_id(self) -> str: ...

    @property
    def turn_markers(self) -> TurnMarkers: ...


async def read_gene_record(
    ctx: RunContext[GeneRecordReader],
    gene_id: str,
) -> ToolReturn[GeneRecordSummary]:
    """Read one gene's record on this site.

    The record is where a fact about a named gene comes from: its product, its
    organism, its exon and transcript counts, its chromosome, the orthologs the
    site lists for it, and the site's own expression summary. Call it before you
    state any of those, and cite it among the sources your answer lists. A web
    page is not a record.

    Args:
        gene_id: A gene source id on this site, for example 'PF3D7_1133400'.
    """
    found = await read.read_gene_record(ctx.deps.site_id, gene_id)
    ctx.deps.turn_markers.record_retrieved_source(found.record_url)
    return with_summary(found, found.summary_line(), ctx=ctx)
