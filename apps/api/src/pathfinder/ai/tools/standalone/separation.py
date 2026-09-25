"""The separation run: a durable, approval-gated search for the strategy that
tells known positive genes from known negatives, every score a WDK count."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from assistant_core.graph.tool_summary import summary_chunks
from assistant_core.tasks.declaration import declare_durable_tool
from assistant_core.tasks.decorator import DurableOutcome
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk
from veupathdb_mcp.separation import CandidateProposal

from pathfinder.ai.graph.stream_events import separation_result_event
from pathfinder.ai.lead.card_reply import CardReply
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.separation import (
    SEPARATION_BUDGET,
    SEPARATION_BUDGET_MAX,
    SEPARATION_BUDGET_MIN,
    SeparationMode,
    SeparationReport,
)
from pathfinder.platform.durable_worker import durable_agent_tool

# The intersection's answer lists every control the target holds.
MAX_CONTROLS = 500
MAX_LITERATURE = 8


def separation_chunks(
    report: SeparationReport, tool_call_id: str | None
) -> list[BaseChunk]:
    """The card of one finished run and its one-line summary."""
    return [
        separation_result_event(report),
        *summary_chunks(tool_call_id, report.summary),
    ]


def _separation_chunks_from_result(
    resumed: Any,
    task_id: UUID,
    tool_call_id: str | None,
) -> list[BaseChunk]:
    del task_id
    outcome = DurableOutcome.model_validate(resumed)
    if not outcome.succeeded:
        return []
    return separation_chunks(
        SeparationReport.model_validate(outcome.result), tool_call_id
    )


SEPARATION = declare_durable_tool(
    tool_name="separate_controls",
    estimated_duration_seconds=300,
    chunks_from_result=_separation_chunks_from_result,
)


@durable_agent_tool(SEPARATION)
async def separate_controls(
    ctx: RunContext[LeadDeps],
    *,
    reply: CardReply,
    positive_controls: Annotated[
        list[str], Field(min_length=2, max_length=MAX_CONTROLS)
    ],
    negative_controls: Annotated[
        list[str], Field(min_length=1, max_length=MAX_CONTROLS)
    ],
    mode: SeparationMode,
    literature: Annotated[
        tuple[CandidateProposal, ...], Field(max_length=MAX_LITERATURE)
    ] = (),
    budget: Annotated[
        int, Field(ge=SEPARATION_BUDGET_MIN, le=SEPARATION_BUDGET_MAX)
    ] = SEPARATION_BUDGET,
) -> dict[str, Any]:
    """Find the strategy that tells known positive genes from known negatives.

    The worker measures candidate searches with real WDK steps against both
    lists: the conversation's own searches, the ``literature`` queries, the site's GO
    and pathway enrichment of the positives, their product phrases and the
    catalog's gene searches. It assembles the AND/OR/MINUS the counts support
    and reads that tree back from the site. The model estimates nothing.

    ``mode`` "exact" asks for every positive and no negative; "similar" asks
    for every positive in a result that returns the positives above chance.

    Call this directly: the researcher approves the run on its card, so do
    not also ask in prose. ``reply`` streams above the card and names the two
    lists, the mode, the budget and that the run takes about five minutes.
    Durable: the run happens on the worker, the turn ends, and you are called
    again with the report. When it carries an ``offer``, write the reply from
    its counts and call ``adopt_separating_strategy`` with its task id.

    Args:
        reply: Your reply, which the researcher reads above the card.
        positive_controls: Gene ids the strategy should return.
        negative_controls: Gene ids it should not return.
        mode: "exact" or "similar".
        literature: Catalog query words drawn from a paper this turn read,
            each with the url, DOI or PMID it came from.
        budget: An estimate of the WDK requests the run may make; one
            measured search costs about ten.
    """
    del ctx, reply, positive_controls, negative_controls, mode, literature, budget
    msg = "separate_controls runs on the worker via @durable_agent_tool"
    raise NotImplementedError(msg)
