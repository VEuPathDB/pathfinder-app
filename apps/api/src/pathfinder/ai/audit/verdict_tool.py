"""The tool that stores a model's verdict on a gene model, citing only reads its turn made."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from assistant_core.graph.tool_summary import with_summary
from pydantic import Field
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.audit.deps import FINDINGS_PER_CALL, AuditDeps
from pathfinder.domain.audit.verdicts import GeneModelVerdict
from pathfinder.services.audit.verdicts import record_verdict


def unheld_cites_message(unheld: Sequence[str]) -> str:
    return (
        f"These cites name no read of this turn: {', '.join(unheld)}. Cite only "
        "the reads the tools of this turn made, or run the read first. Nothing "
        "was stored."
    )


async def record_gene_model_verdicts(
    ctx: RunContext[AuditDeps],
    verdicts: Annotated[
        list[GeneModelVerdict], Field(min_length=1, max_length=FINDINGS_PER_CALL)
    ],
) -> ToolReturn[list[int]]:
    """Store your verdicts on gene models, each with the reads of this turn it rests on.

    Give one verdict for each gene model you judged, up to 25 in one call.
    verdict is error, no_error or undecided. An error names its error type and
    certainty. cause states why in one or two sentences. cites lists the reads
    of this turn the verdict rests on, as the judging rules write them. Nothing
    is stored when one verdict cites a read this turn did not make.
    Returns the id of each stored verdict, in order.
    """
    held = ctx.deps.held_reads()
    unheld = [cite for verdict in verdicts for cite in verdict.unheld_cites(held)]
    if unheld:
        raise ModelRetry(unheld_cites_message(unheld))
    stored: list[int] = []
    for verdict in verdicts:
        stored.append(
            await record_verdict(
                caller=ctx.deps.caller,
                origin=ctx.deps.origin,
                verdict=verdict,
                model_id=ctx.model.model_name,
            )
        )
        ctx.deps.recorded.append(stored[-1])
    summary = "; ".join(f"{', '.join(v.genes)}: {v.verdict}" for v in verdicts)
    return with_summary(stored, summary, ctx=ctx)
