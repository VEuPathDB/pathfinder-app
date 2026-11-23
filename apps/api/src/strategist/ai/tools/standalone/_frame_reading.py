"""The reading a FRAME pass binds from an answer in the researcher's words,
held to the readings a question the researcher was asked offered."""

from __future__ import annotations

from collections.abc import Mapping

from strategist.ai.agents.state import AgentToolState
from strategist.domain.refusal import Check, Problems, RefusalKey
from strategist.domain.strategy.operational_spec import BoundValue
from strategist.domain.strategy.readings import AcceptedReading, ReadingChooser

_READING = RefusalKey(check=Check.READING)


def reading_label_problems(
    state: AgentToolState, criterion_id: str, reading: str
) -> Problems:
    """A reading names one a question the researcher was asked offered on the
    criterion."""
    if not reading:
        return Problems()
    offers = [r for r in state.offered_readings if r.criterion_id == criterion_id]
    if not offers:
        return Problems.one(
            _READING,
            f"{criterion_id} takes no reading: no question the researcher was "
            f"asked offered readings on it. Bind the values the request states "
            f"and pass no reading.",
        )
    if any(r.reading == reading for r in offers):
        return Problems()
    return Problems.one(
        _READING,
        f"No question offered the reading {reading!r} on {criterion_id}. "
        f"Pass the label of one it offered: {[r.reading for r in offers]}.",
    )


def offered_reading(
    state: AgentToolState,
    criterion_id: str,
    reading: str,
    bound: Mapping[str, BoundValue],
) -> tuple[AcceptedReading | None, Problems]:
    """The reading the binding keeps, and the problem a reading whose values
    it does not bind makes. The label was checked before any value was read."""
    values = {name: held.value for name, held in bound.items()}
    kept = next(
        (
            c.accepted_reading
            for c in state.operational_spec_draft.criteria
            if c.id == criterion_id
        ),
        None,
    )
    if kept is not None and kept.unbound(values):
        kept = None
    read = next(
        (
            r
            for r in state.offered_readings
            if r.criterion_id == criterion_id and r.reading == reading
        ),
        None,
    )
    if not reading or read is None:
        return kept, Problems()
    accepted = read.accepted(ReadingChooser.ASSISTANT)
    moved = [f"{name} = {read.params[name]!r}" for name in accepted.unbound(values)]
    if moved:
        return kept, Problems.one(
            _READING,
            f"The reading {reading!r} on {criterion_id} binds {'; '.join(moved)}. "
            f"Bind those values with it, or pass the reading whose values you bind.",
        )
    return (kept if accepted.same_reading(kept, values) else accepted), Problems()
