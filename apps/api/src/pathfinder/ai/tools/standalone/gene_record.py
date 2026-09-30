"""The tool that reads one gene's record, for the Lead and for a check."""

from __future__ import annotations

from typing import Protocol

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext, ToolFailed
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.turn_records import ReadRecord, TurnMarkers
from pathfinder.domain.evidence import SAMPLED_GENE_LIMIT
from pathfinder.services.gene_records import read
from pathfinder.services.gene_records.read import GeneRecordSummary


def _read_record(found: GeneRecordSummary) -> ReadRecord:
    """The record as the turn keeps it: its page, the values a researcher checks,
    and the orthologs of the organism the read asked for."""
    asked = [] if found.ortholog_organism is None else found.orthologs
    return ReadRecord(
        record_id=found.gene_id,
        url=found.record_url,
        product=found.product,
        organism=found.organism,
        gene_name=found.gene_name or "",
        chromosome=found.chromosome or "",
        asked_orthologs=[t for row in asked for t in (row.gene_id, row.organism)],
    )


class GeneRecordReader(Protocol):
    """What a record read needs of its caller: the site and the turn's reads."""

    @property
    def site_id(self) -> str: ...

    @property
    def turn_markers(self) -> TurnMarkers: ...


async def read_gene_record(
    ctx: RunContext[GeneRecordReader],
    gene_id: str,
    ortholog_organism: str | None = None,
) -> ToolReturn[GeneRecordSummary]:
    """Read one gene's record on this site.

    The record is where a fact about a named gene comes from: its product, its
    organism, its exon and transcript counts, its chromosome, the orthologs the
    site lists for it, and the site's own expression summary. Call it before you
    state any of those; the facts beside the reply show the record it read. A
    web page is not a record. ``orthologsShown`` says which rows of the ortholog
    table the answer holds; a gene's ortholog in one organism is read with
    ``ortholog_organism``, never from the first rows.

    Args:
        gene_id: A gene source id on this site, for example 'PF3D7_1133400'.
        ortholog_organism: An organism whose every ortholog row to read, for
            example 'Anopheles gambiae PEST'.
    """
    found = await read.read_gene_record(
        ctx.deps.site_id, gene_id, ortholog_organism=ortholog_organism
    )
    ctx.deps.turn_markers.record_read(_read_record(found))
    return with_summary(found, found.summary_line(), ctx=ctx)


def _unsampled_message(gene_id: str, sampled: list[str]) -> str:
    """Why a gene no sample returned is not read, naming the id it was sampled as."""
    versions = [g for g in sampled if g.startswith(f"{gene_id}.")]
    if versions:
        return (
            f"{gene_id} is not a gene a sample of this turn returned; the sample "
            f"returned {', '.join(versions)}. Read it by that id."
        )
    return (
        f"{gene_id} is not a gene a sample of this turn returned. A check reads "
        f"the records of its sampled genes only: {', '.join(sampled) or 'none yet'}."
    )


async def read_sampled_gene_record(
    ctx: RunContext[AgentDeps],
    gene_id: str,
    ortholog_organism: str | None = None,
) -> ToolReturn[GeneRecordSummary]:
    """Read the record of one gene this check's sample returned.

    A check reads a record only for a gene ``get_sample_records`` returned this
    turn, for a criterion no column shows. A control's record is never read:
    the control test states whether the strategy returned it. A criterion on an
    ortholog in one organism passes that organism as ``ortholog_organism``, so
    the answer holds every row of it.

    Args:
        gene_id: A gene id the sample returned, for example 'PF3D7_1133400'.
        ortholog_organism: An organism whose every ortholog row to read.
    """
    markers = ctx.deps.turn_markers
    adopted = ctx.deps.verification_scope.controls
    controls = markers.control_gene_ids() | frozenset(
        [] if adopted is None else [*adopted.positives, *adopted.negatives]
    )
    if gene_id in controls:
        msg = (
            f"{gene_id} is a control. A control's record is not read; the control "
            "test states whether the strategy returned it."
        )
        raise ToolFailed(msg)
    if gene_id not in markers.sampled_gene_ids:
        raise ToolFailed(_unsampled_message(gene_id, markers.sampled_gene_ids))
    held = markers.records_read.setdefault(ctx.deps.verification_scope.check_id, [])
    if gene_id in held:
        msg = (
            f"This check already read the record of {gene_id}; its answer is "
            f"above. The records this check read: {', '.join(held)}. Judge the "
            "sampled genes from those records."
        )
        raise ToolFailed(msg)
    if len(held) >= SAMPLED_GENE_LIMIT:
        msg = (
            f"This check read {len(held)} records, the most one check reads: "
            f"{', '.join(held)}. Judge the sampled genes from those records, and "
            "read a criterion over the whole step with read_step_columns."
        )
        raise ToolFailed(msg)
    # The read is held before it runs so a parallel batch keeps the budget.
    held.append(gene_id)
    try:
        found = await read.read_gene_record(
            ctx.deps.site_id, gene_id, ortholog_organism=ortholog_organism
        )
    except Exception:
        held.remove(gene_id)
        raise
    markers.record_read(_read_record(found))
    return with_summary(found, found.summary_line(), ctx=ctx)
