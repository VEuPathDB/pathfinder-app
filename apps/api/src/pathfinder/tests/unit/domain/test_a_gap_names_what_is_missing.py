"""A gap is what the strategy does not answer, typed by its source, and each
one is listed once whichever check found it."""

from __future__ import annotations

from pathfinder.domain.caveats import (
    RequirementGap,
    StructureGap,
    WordGap,
    check_gaps,
)
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    provisional_constraints,
)

_STRUCTURE = StructureGap(expression="kinases OR phosphatases", built="INTERSECT")


def _row(text: str, status: str, how: str = "search") -> RequirementCheck:
    return RequirementCheck.model_validate(
        {
            "text": text,
            "turn": 1,
            "answeredBy": ["step_a"] if status == "met" else [],
            "how": how,
            "status": status,
            "note": "",
        }
    )


def test_each_gap_is_listed_once_with_its_sentence() -> None:
    review = VerificationReview(
        requirements=[
            _row("kinases OR phosphatases", "unmet", how="structure"),
            _row("exported", "unexpressed"),
            _row("at least 2 transmembrane domains", "unmet"),
            _row("with a signal peptide", "met"),
            _row("in the host cell", "unexpressed"),
        ]
    )

    gaps = check_gaps(
        structure=_STRUCTURE,
        words=["exported"],
        review=review,
        requirements=provisional_constraints(
            [
                Constraint(
                    kind=ConstraintKind.OTHER,
                    requested_value=value,
                    label=value,
                    source=ConstraintSource.USER_EXPLICIT,
                )
                for value in (
                    "exported",
                    "at least 2 transmembrane domains",
                    "in the host cell",
                )
            ]
        ),
    )

    assert [gap.sentence for gap in gaps] == [
        "'kinases OR phosphatases': the strategy joins it with INTERSECT",
        "'exported': no search the strategy runs states it",
        "'at least 2 transmembrane domains': nothing in the strategy answers it",
        "'in the host cell': no search on this site states it",
    ]
    assert gaps[1:] == [
        WordGap(word="exported"),
        RequirementGap(text="at least 2 transmembrane domains", status="unmet"),
        RequirementGap(text="in the host cell", status="unexpressed"),
    ]
