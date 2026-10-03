"""Lead arcs on what a turn shows: a listing whose ids the reply names by
reference, which the facts part shows under the step it listed."""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic import Field
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.reads import ToolAnswer, last_return

# The ids a listing turn reads from the result, and names in its reply.
LISTED = 5


class _Listing(ToolAnswer):
    gene_ids: list[str] = Field(default_factory=list)


def list_ids(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read the result's first ids and name each by a reference to its record."""
    listing = last_return(messages, "read_step_ids", _Listing)
    ids = [] if listing is None else listing.gene_ids[:LISTED]
    prose = (
        f"The result starts with {', '.join(f'[record:{i}]' for i in ids)}."
        if ids
        else "The listing did not answer."
    )
    return [
        classify("follow_up_question"),
        scripted_call("read_step_ids", {"limit": LISTED}),
        lead_final(prose, "await_user"),
    ]


__all__ = ["LISTED", "list_ids"]
