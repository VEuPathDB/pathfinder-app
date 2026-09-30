"""A requirement the researcher withdrew or replaced yields no gap, and a gap
the researcher's requirement names carries the requirement's own words."""

from __future__ import annotations

import pytest

from pathfinder.domain.caveats import (
    RequirementGap,
    StructureGap,
    WordGap,
    check_gaps,
)
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import (
    BoundLifecycle,
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    Lifecycle,
    OpenLifecycle,
    ReplacedLifecycle,
    WithdrawnLifecycle,
)


def _row(text: str, status: str) -> RequirementCheck:
    return RequirementCheck.model_validate(
        {"text": text, "turn": 1, "how": "search", "status": status, "note": ""}
    )


def _requirement(
    value: str,
    lifecycle: Lifecycle,
    kind: ConstraintKind = ConstraintKind.OTHER,
) -> GroundedConstraint:
    return GroundedConstraint(
        constraint=Constraint(
            kind=kind,
            requested_value=value,
            label=value,
            source=ConstraintSource.USER_EXPLICIT,
        ),
        status=ConstraintStatus.GROUNDED,
        lifecycle=lifecycle,
    )


_EXPORTED_ROW = VerificationReview(
    requirements=[_row("exported to the host cell", "unexpressed")]
)


@pytest.mark.parametrize(
    "lifecycle",
    [WithdrawnLifecycle(turn_id="t2"), ReplacedLifecycle(by="other:secreted")],
)
def test_a_retired_requirement_yields_no_gap(lifecycle: Lifecycle) -> None:
    gaps = check_gaps(
        structure=None,
        words=["exported"],
        review=_EXPORTED_ROW,
        requirements=[_requirement("exported", lifecycle)],
    )

    assert gaps == []


@pytest.mark.parametrize(
    "lifecycle",
    [OpenLifecycle(), BoundLifecycle(criterion_id="c_exp", params=["export"])],
)
def test_an_open_or_bound_requirement_gap_carries_the_requirement_words(
    lifecycle: Lifecycle,
) -> None:
    gaps = check_gaps(
        structure=None,
        words=[],
        review=_EXPORTED_ROW,
        requirements=[_requirement("exported", lifecycle)],
    )

    assert gaps == [RequirementGap(text="exported", status="unexpressed")]


def test_a_row_that_names_two_requirements_keeps_its_own_words() -> None:
    gaps = check_gaps(
        structure=None,
        words=[],
        review=_EXPORTED_ROW,
        requirements=[
            _requirement("exported", OpenLifecycle()),
            _requirement("host cell", OpenLifecycle()),
        ],
    )

    assert gaps == [
        RequirementGap(text="exported to the host cell", status="unexpressed")
    ]


def test_a_row_no_requirement_names_is_no_gap() -> None:
    gaps = check_gaps(
        structure=None,
        words=[],
        review=_EXPORTED_ROW,
        requirements=[_requirement("kinase", OpenLifecycle())],
    )

    assert gaps == []


def test_a_withdrawn_combination_yields_no_structure_gap() -> None:
    gaps = check_gaps(
        structure=StructureGap(expression="kinases OR phosphatases", built="AND"),
        words=[],
        review=VerificationReview(),
        requirements=[
            _requirement(
                "kinases OR phosphatases",
                WithdrawnLifecycle(turn_id="t3"),
                ConstraintKind.COMBINATION,
            )
        ],
    )

    assert gaps == []


def test_an_open_requirement_leaves_the_word_gap() -> None:
    gaps = check_gaps(
        structure=None,
        words=["exported"],
        review=VerificationReview(),
        requirements=[_requirement("exported", OpenLifecycle())],
    )

    assert gaps == [WordGap(word="exported")]


def test_a_requirement_is_keyed_by_its_dimension_and_value() -> None:
    held = _requirement("exported", OpenLifecycle()).constraint

    assert held.key == "other:exported"


def test_a_lifecycle_defaults_to_open() -> None:
    grounded = GroundedConstraint(
        constraint=Constraint(
            kind=ConstraintKind.OTHER, requested_value="x", label="x"
        ),
        status=ConstraintStatus.PROVISIONAL,
    )

    assert (grounded.lifecycle, grounded.retired) == (OpenLifecycle(), False)


def test_a_value_the_model_assumed_never_words_a_gap() -> None:
    assumed = GroundedConstraint(
        constraint=Constraint(
            kind=ConstraintKind.OTHER,
            requested_value="host",
            label="host",
            source=ConstraintSource.ASSUMED,
        ),
        status=ConstraintStatus.GROUNDED,
    )

    gaps = check_gaps(
        structure=None, words=[], review=_EXPORTED_ROW, requirements=[assumed]
    )

    assert gaps == [
        RequirementGap(text="exported to the host cell", status="unexpressed")
    ]


def test_a_row_worded_as_a_word_gap_is_one_gap() -> None:
    gaps = check_gaps(
        structure=None,
        words=["exported"],
        review=_EXPORTED_ROW,
        requirements=[_requirement("exported", OpenLifecycle())],
    )

    assert gaps == [WordGap(word="exported")]
