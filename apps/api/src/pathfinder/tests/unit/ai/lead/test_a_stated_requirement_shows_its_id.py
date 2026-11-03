"""Each requirement the Lead reads names the id a card question asks it by."""

from __future__ import annotations

from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.ledger_sections import ConstraintSection
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
)
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_VSG = Constraint(
    kind=ConstraintKind.UNTYPED,
    requested_value="variant surface glycoprotein",
    label="VSG products",
    source=ConstraintSource.USER_EXPLICIT,
)


def test_a_stated_requirement_names_its_id() -> None:
    section = ConstraintSection(
        grounded=[
            GroundedConstraint(constraint=_VSG, status=ConstraintStatus.PROVISIONAL)
        ]
    )

    assert section.render_stated() == [
        (
            "- VSG products (untyped): 'variant surface glycoprotein' -> provisional; "
            f"id {_VSG.id}"
        )
    ]


def test_a_held_requirement_names_the_number_a_card_replaces_it_by() -> None:
    section = ConstraintSection(
        grounded=[
            GroundedConstraint(constraint=_VSG, status=ConstraintStatus.PROVISIONAL)
        ],
        numbers={_VSG.id: "R2"},
    )

    assert section.render_stated() == [
        (
            "- R2: VSG products (untyped): 'variant surface glycoprotein' -> "
            f"provisional; id {_VSG.id}"
        )
    ]


def test_the_ledger_numbers_the_held_requirements_as_the_card_reads_them() -> None:
    state = pipeline_state()
    state.domain.requirements = [_VSG]

    assert derive_ledger(state, None).constraints.numbers == {_VSG.id: "R1"}


def test_a_requirement_nothing_compared_reads_not_verified() -> None:
    section = ConstraintSection(
        grounded=[
            GroundedConstraint(
                constraint=_VSG,
                status=ConstraintStatus.NOT_VERIFIED,
                unverified="no_step_states_it",
            )
        ]
    )

    [line] = section.render_stated()
    assert "'variant surface glycoprotein' -> not verified;" in line
    assert "grounded" not in line
