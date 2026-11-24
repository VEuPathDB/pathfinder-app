"""The stated requirements no step of a spec meets."""

from __future__ import annotations

from collections.abc import Sequence

from strategist.domain.refusal import Check, Problem, Problems, RefusalKey
from strategist.domain.strategy.constraint_grounding import ground_against_spec
from strategist.domain.strategy.constraints import (
    STRATEGY_SCOPES,
    Constraint,
    ConstraintSource,
)
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.domain.strategy.requirement_reports import numbered_requirements


def requirements_no_step_meets(
    requirements: Sequence[Constraint], spec: OperationalSpec
) -> Problems:
    """One problem for each hard requirement the researcher stated that no step
    of the spec states."""
    numbered = {c.id: n for n, c in numbered_requirements(requirements).items()}
    stated = [
        c
        for c in requirements
        if c.source is ConstraintSource.USER_EXPLICIT
        and c.hard
        and c.kind not in STRATEGY_SCOPES
    ]
    return Problems(
        found=tuple(
            Problem(
                key=RefusalKey(
                    check=Check.UNMET_REQUIREMENT, criterion=numbered[g.constraint.id]
                ),
                sentence=(
                    f"The requirement '{g.constraint.requested_value}' is not met by "
                    f"any step: {g.note}."
                ),
            )
            for g in ground_against_spec(stated, spec)
            if g.met_by_no_step
        )
    )


__all__ = ["requirements_no_step_meets"]
