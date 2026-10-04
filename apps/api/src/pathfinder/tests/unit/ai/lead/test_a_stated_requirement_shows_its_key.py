"""Each requirement the Lead reads names the key a proposal card answers it by."""

from __future__ import annotations

from pathfinder.ai.lead.ledger_sections import ConstraintSection
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
)

_VSG = Constraint(
    kind=ConstraintKind.OTHER,
    requested_value="variant surface glycoprotein",
    label="VSG products",
    source=ConstraintSource.USER_EXPLICIT,
)


def test_a_stated_requirement_names_its_key() -> None:
    section = ConstraintSection(
        grounded=[
            GroundedConstraint(constraint=_VSG, status=ConstraintStatus.PROVISIONAL)
        ]
    )

    assert section.render_stated() == [
        (
            "- VSG products (other): 'variant surface glycoprotein' -> provisional; "
            "key other:variant surface glycoprotein"
        )
    ]
