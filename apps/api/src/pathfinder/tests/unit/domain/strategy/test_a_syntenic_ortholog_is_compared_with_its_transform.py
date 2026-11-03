from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue

from pathfinder.domain.requirement_checks import grounded_check
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    GroundedConstraint,
    OrthologValue,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from pathfinder.tests.unit.domain.strategy._linked_values import requirement

_PV = "Plasmodium vivax P01"


def _orthologs(syntenic: bool | None) -> Constraint:
    return requirement(
        ConstraintKind.ORTHOLOG, OrthologValue(organisms=[_PV], syntenic=syntenic)
    )


def _transform(held: Constraint, syntenic: str | None) -> Criterion:
    setting = (
        {}
        if syntenic is None
        else {
            "isSyntenic": BoundValue(
                value=SinglePickValue(value=syntenic), source="stated"
            )
        }
    )
    return Criterion(
        id="c_orthologs",
        text="their orthologs",
        search_name="GenesByOrthologs",
        role="transform",
        organism_param="organism",
        resolved_params={
            "organism": BoundValue(value=MultiPickValue(values=[_PV]), source="stated"),
            **setting,
        },
        answers=[RequirementLink(requirement=held.id)],
    )


def _grounded(held: Constraint, criterion: Criterion) -> GroundedConstraint:
    [grounded] = ground_against_spec(
        [held], OperationalSpec(goal="g", criteria=[criterion])
    )
    return grounded


def test_a_syntenic_ortholog_the_transform_holds_is_grounded() -> None:
    held = _orthologs(syntenic=True)

    grounded = _grounded(held, _transform(held, "yes"))

    assert (grounded.status, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        _PV,
    )
    assert grounded_check(grounded).status == "pass"


def test_a_syntenic_ortholog_the_transform_does_not_hold_fails() -> None:
    held = _orthologs(syntenic=True)

    grounded = _grounded(held, _transform(held, "no"))

    assert (
        grounded.status,
        grounded.realized_param,
        grounded.realized_value,
        grounded.note,
    ) == (
        ConstraintStatus.SUBSTITUTED,
        "isSyntenic",
        "no",
        "asked syntenic orthologs, isSyntenic holds 'no'",
    )
    assert grounded_check(grounded).status == "fail"


def test_any_ortholog_the_transform_limits_to_syntenic_ones_fails() -> None:
    held = _orthologs(syntenic=False)

    grounded = _grounded(held, _transform(held, "yes"))

    assert (grounded.status, grounded.note) == (
        ConstraintStatus.SUBSTITUTED,
        "asked orthologs not limited to syntenic ones, isSyntenic holds 'yes'",
    )


def test_a_synteny_no_transform_sets_is_not_verified() -> None:
    held = _orthologs(syntenic=True)

    grounded = _grounded(held, _transform(held, None))

    assert (grounded.status, grounded.unverified, grounded.note) == (
        ConstraintStatus.NOT_VERIFIED,
        "no_value_to_compare",
        "no ortholog step that answers it sets isSyntenic",
    )
    assert grounded_check(grounded).status == "unchecked"


def test_an_ortholog_that_states_no_synteny_reads_only_its_organisms() -> None:
    held = _orthologs(syntenic=None)

    grounded = _grounded(held, _transform(held, None))

    assert grounded.status is ConstraintStatus.GROUNDED
