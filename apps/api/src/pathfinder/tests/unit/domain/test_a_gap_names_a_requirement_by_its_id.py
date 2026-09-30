"""A check row that carries several requirements is named by the one it
misses, whatever order the ledger lists them in: a requirement a met row names
is not the one missing, and a row that still names several keeps its words."""

from __future__ import annotations

import pytest

from pathfinder.domain.caveats import RequirementGap, check_gaps
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
)


def _held(kind: ConstraintKind, value: str) -> GroundedConstraint:
    return GroundedConstraint(
        constraint=Constraint(
            kind=kind,
            requested_value=value,
            label=value,
            source=ConstraintSource.USER_EXPLICIT,
        ),
        status=ConstraintStatus.GROUNDED,
    )


_PEXEL = _held(ConstraintKind.OTHER, "PEXEL motif")
_RING = _held(ConstraintKind.OTHER, "expressed in the ring stage")
_PLASMODB_REVIEW = VerificationReview(
    requirements=[
        RequirementCheck(
            text="PEXEL motif",
            turn=1,
            how="search",
            status="met",
            answered_by=["step_c475a23b"],
        ),
        RequirementCheck(
            text="with a PEXEL motif that are expressed in the ring stage",
            turn=1,
            how="structure",
            status="unexpressed",
        ),
    ]
)


@pytest.mark.parametrize(
    "requirements", [[_RING, _PEXEL], [_PEXEL, _RING]], ids=["turn1", "turn2"]
)
def test_the_plasmodb_row_names_the_ring_stage_in_either_order(
    requirements: list[GroundedConstraint],
) -> None:
    gaps = check_gaps(
        structure=None,
        words=[],
        review=_PLASMODB_REVIEW,
        requirements=requirements,
    )

    assert gaps == [
        RequirementGap(text="expressed in the ring stage", status="unexpressed")
    ]


_FOLD = _held(ConstraintKind.FOLD_CHANGE, "1.5-fold")
_DIRECTION = _held(ConstraintKind.COMPARATOR, "bradyzoite over tachyzoite")
_TOXODB_ROW = "a plain 1.5-fold change (bradyzoite over tachyzoite)"


@pytest.mark.parametrize(
    "requirements",
    [[_FOLD, _DIRECTION], [_DIRECTION, _FOLD]],
    ids=["fold-first", "direction-first"],
)
def test_the_toxodb_row_naming_two_requirements_keeps_its_words(
    requirements: list[GroundedConstraint],
) -> None:
    review = VerificationReview(
        requirements=[
            RequirementCheck(text=_TOXODB_ROW, turn=3, how="analysis", status="unmet")
        ]
    )

    gaps = check_gaps(
        structure=None, words=[], review=review, requirements=requirements
    )

    assert gaps == [RequirementGap(text=_TOXODB_ROW, status="unmet")]
