"""The requirement a card answer's own words state."""

from __future__ import annotations

from collections.abc import Sequence

from strategist.ai.lead.organism_reader import site_entry
from strategist.domain.clipped import clipped_text
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrganismValue,
)

LABEL_LIMIT = 120


def answer_requirement(
    prompt: str,
    labels: list[str],
    note: str,
    dimension: ConstraintKind,
    organisms: Sequence[str],
) -> Constraint | None:
    """The words an answer states as a requirement on the question's
    dimension, or None when it states none. Words on the organism dimension
    state the one organism of the site they name, and none otherwise."""
    stated = "; ".join(labels) if labels else note
    if not stated:
        return None
    label = clipped_text(prompt or stated, LABEL_LIMIT)
    if dimension is not ConstraintKind.ORGANISM:
        return Constraint(
            kind=dimension,
            requested_value=stated,
            label=label,
            source=ConstraintSource.USER_EXPLICIT,
            hard=True,
        )
    entry = site_entry(stated, organisms)
    if entry is None:
        return None
    return Constraint(
        kind=dimension,
        requested_value=entry,
        label=label,
        source=ConstraintSource.USER_EXPLICIT,
        quote=stated,
        hard=True,
        value=OrganismValue(organism=entry),
    )
