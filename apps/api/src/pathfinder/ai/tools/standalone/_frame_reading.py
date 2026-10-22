"""The reading a FRAME pass binds from an answer in the researcher's words,
held to the readings a question the researcher was asked offered."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic_ai import ModelRetry

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.domain.strategy.operational_spec import BoundValue
from pathfinder.domain.strategy.readings import AcceptedReading


def offered_reading(
    state: AgentToolState,
    criterion_id: str,
    reading: str,
    bound: Mapping[str, BoundValue],
) -> AcceptedReading | None:
    values = {name: held.value for name, held in bound.items()}
    if not reading:
        kept = next(
            (
                c.accepted_reading
                for c in state.operational_spec_draft.criteria
                if c.id == criterion_id
            ),
            None,
        )
        return None if kept is None or kept.unbound(values) else kept
    offers = [r for r in state.offered_readings if r.criterion_id == criterion_id]
    if not offers:
        msg = (
            f"{criterion_id} takes no reading: no question the researcher was "
            f"asked offered readings on it. Bind the values the request states "
            f"and pass no reading."
        )
        raise ModelRetry(msg)
    read = next((r for r in offers if r.reading == reading), None)
    if read is None:
        msg = (
            f"No question offered the reading {reading!r} on {criterion_id}. "
            f"Pass the label of one it offered: {[r.reading for r in offers]}."
        )
        raise ModelRetry(msg)
    accepted = read.accepted()
    moved = [f"{name} = {read.params[name]!r}" for name in accepted.unbound(values)]
    if moved:
        msg = (
            f"The reading {reading!r} on {criterion_id} binds {'; '.join(moved)}. "
            f"Bind those values with it, or pass the reading whose values you bind."
        )
        raise ModelRetry(msg)
    return accepted
