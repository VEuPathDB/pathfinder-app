"""The requirement a card answer's own words state."""

from __future__ import annotations

from strategist.domain.clipped import clipped_text
from strategist.domain.strategy.constraints import (
    MANY_VALUED_KINDS,
    Constraint,
    ConstraintKind,
    ConstraintSource,
)

LABEL_LIMIT = 120


def answer_requirement(
    prompt: str, labels: list[str], note: str, dimension: ConstraintKind
) -> Constraint | None:
    """The words an answer states as a requirement on the question's dimension, or
    None. Words state none on a dimension of one value: only a structured pick
    replaces a stated value there, and the words reach the Lead as the answer."""
    stated = "; ".join(labels) if labels else note
    if not stated or dimension not in MANY_VALUED_KINDS:
        return None
    return Constraint(
        kind=dimension,
        requested_value=stated,
        label=clipped_text(prompt or stated, LABEL_LIMIT),
        source=ConstraintSource.USER_EXPLICIT,
        hard=True,
    )
