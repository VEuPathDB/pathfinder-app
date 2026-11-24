"""The stated requirements no step of a spec meets."""

from __future__ import annotations

from collections.abc import Sequence

from strategist.domain.refusal import Check, Problem, Problems, RefusalKey
from strategist.domain.strategy.constraint_grounding import ground_against_spec
from strategist.domain.strategy.constraints import Constraint
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.domain.strategy.requirement_reports import numbered_requirements


def requirements_no_step_meets(
    requirements: Sequence[Constraint], spec: OperationalSpec
) -> Problems:
    """One problem for each hard requirement the researcher stated that the
    steps' values show no step meets."""
    numbered = {c.id: n for n, c in numbered_requirements(requirements).items()}
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
            for g in ground_against_spec(requirements, spec)
            if g.blocks
        )
    )


__all__ = ["requirements_no_step_meets"]
