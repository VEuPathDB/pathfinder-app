"""What the researcher asked verification to answer, read from the thread."""

from __future__ import annotations

from pathfinder.ai.graph.runtime import VerificationScope
from pathfinder.ai.lead.sub_agent_tools import LeadDeps


def verification_scope(deps: LeadDeps, *, check_id: str) -> VerificationScope:
    """The request this turn answers and the check that answers it, as VERIFY reads them."""
    return VerificationScope(
        messages=deps.state.researcher_messages(),
        check_id=check_id,
        last_card=deps.state.domain.card_of_the_strategy(),
        controls=deps.state.domain.attached_controls,
        control_sets=list(deps.state.domain.control_sets),
    )
