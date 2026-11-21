from __future__ import annotations

from strategist.ai.agents.state import AgentToolState


def held_weight(
    state: AgentToolState, criterion_id: str, weight: int | None
) -> int | None:
    if weight is not None:
        return weight
    return next(
        (
            c.weight
            for c in state.operational_spec_draft.criteria
            if c.id == criterion_id
        ),
        None,
    )
