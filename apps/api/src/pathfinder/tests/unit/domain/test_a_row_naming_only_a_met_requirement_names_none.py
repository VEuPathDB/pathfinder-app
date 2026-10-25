"""An unmet check row whose words carry only requirements a met row answers
names none of them: the gap keeps the row's own words and holds no requirement
the strategy answers."""

from __future__ import annotations

from pathfinder.domain.caveats import RequirementGap, check_gaps
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.requirement_naming import requirement_naming
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
)

_ORGANISM = GroundedConstraint(
    constraint=Constraint(
        kind=ConstraintKind.ORGANISM,
        requested_value="Plasmodium species",
        label="organism scope",
        source=ConstraintSource.USER_EXPLICIT,
    ),
    status=ConstraintStatus.GROUNDED,
)
_DEFINITION = GroundedConstraint(
    constraint=Constraint(
        kind=ConstraintKind.OTHER,
        requested_value="singleton genes, meaning genes in a group of their own",
        label="singleton definition",
        source=ConstraintSource.USER_EXPLICIT,
    ),
    status=ConstraintStatus.GROUNDED,
)
_QUESTION = "Which Plasmodium species has the most singleton genes?"
_REVIEW = VerificationReview(
    requirements=[
        RequirementCheck(
            text="Plasmodium species",
            turn=1,
            how="search",
            status="met",
            answered_by=["step_5ebea5e6"],
        ),
        RequirementCheck(
            text="singleton genes, meaning genes in a group of their own",
            turn=1,
            how="search",
            status="met",
            answered_by=["step_c3186ea7"],
        ),
        RequirementCheck(text=_QUESTION, turn=1, how="analysis", status="unmet"),
    ]
)


def test_a_row_naming_only_a_met_requirement_names_none() -> None:
    assert [
        requirement_naming(
            _QUESTION, [_ORGANISM, _DEFINITION], met=["Plasmodium species"]
        )
    ] == [None]


def test_the_gap_keeps_the_rows_words_and_no_requirement_key() -> None:
    gaps = check_gaps(
        structure=None,
        words=[],
        review=_REVIEW,
        requirements=[_ORGANISM, _DEFINITION],
    )

    assert gaps == [RequirementGap(text=_QUESTION, status="unmet")]


def test_a_row_still_names_the_requirement_no_met_row_answers() -> None:
    assert requirement_naming(_QUESTION, [_ORGANISM, _DEFINITION]) == _ORGANISM
