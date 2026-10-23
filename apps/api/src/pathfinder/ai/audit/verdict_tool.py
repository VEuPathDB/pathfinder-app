"""The tool that stores a model's verdict on a gene model, citing only reads its turn made."""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.domain.audit.verdicts import GeneModelVerdict
from pathfinder.services.audit.verdicts import record_verdict


def unheld_cites_message(unheld: Sequence[str]) -> str:
    return (
        f"These cites name no read of this turn: {', '.join(unheld)}. Cite only "
        "the reads the tools of this turn made, or run the read first. Nothing "
        "was stored."
    )


async def record_gene_model_verdict(
    ctx: RunContext[AuditDeps], verdict: GeneModelVerdict
) -> ToolReturn[int]:
    """Store your verdict on one gene model, with the reads of this turn it rests on.

    verdict is error, no_error or undecided. An error names its error type and
    certainty. cause states why in one or two sentences. cites lists the reads
    of this turn the verdict rests on, as the judging rules write them.
    Returns the id of the stored verdict.
    """
    unheld = verdict.unheld_cites(ctx.deps.held_reads())
    if unheld:
        raise ModelRetry(unheld_cites_message(unheld))
    verdict_id = await record_verdict(
        caller=ctx.deps.caller,
        origin=ctx.deps.origin,
        verdict=verdict,
        model_id=ctx.model.model_name,
    )
    summary = f"{', '.join(verdict.genes)}: {verdict.verdict}"
    return with_summary(verdict_id, summary, ctx=ctx)
