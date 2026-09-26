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

    gaps = check_gaps(structure=_STRUCTURE, words=["exported"], review=review)

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


def test_a_reply_names_a_gap_by_its_words_in_any_case() -> None:
    assert _STRUCTURE.named_by("It joins Kinases OR Phosphatases at an intersect.")
    assert not WordGap(word="exported").named_by("It reads every exporter.")
