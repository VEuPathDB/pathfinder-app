"""A gap is a requirement of the researcher: a review row that names no held
requirement, such as an edit instruction, is no gap."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.caveats import RequirementGap, check_gaps
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    provisional_constraints,
)


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=kind.value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_HELD = provisional_constraints(
    [
        _stated(ConstraintKind.ORGANISM, "Trypanosoma brucei gambiense DAL972"),
        _stated(ConstraintKind.OTHER, "RNA-binding domain"),
    ]
)


def _row(text: str) -> RequirementCheck:
    return RequirementCheck(
        text=text,
        turn=3,
        answered_by=["step_dd5b456c"],
        how="search",
        status="met",
        no_record_shows_it=True,
    )


def test_the_researchers_edit_instructions_are_no_gaps() -> None:
    """The tritrypdb delete: two instructions the delete carried out."""
    review = VerificationReview(
        requirements=[
            _row("I only wanted the two counts compared, not merged"),
            _row(
                "put my strategy back to the DAL972 genes alone, without the "
                "TREU927 search or the union"
            ),
        ]
    )

    gaps = check_gaps(structure=None, words=[], review=review, requirements=_HELD)

    assert gaps == []


def test_a_row_that_names_a_held_requirement_is_a_gap() -> None:
    review = VerificationReview(requirements=[_row("RNA-binding domain")])

    gaps = check_gaps(structure=None, words=[], review=review, requirements=_HELD)

    assert gaps == [RequirementGap(text="RNA-binding domain", status="unshown")]


_APICOPLAST = "predicted apicoplast targeting signal"
_ANSWERED_ROW = {
    "how": "parameter",
    "note": "The search uses the PlasmoAP apicoplast-targeting gene list, but "
    "none of the sampled records read here explicitly shows a predicted "
    "targeting signal.",
    "text": _APICOPLAST,
    "turn": 1,
    "shownBy": [],
    "answeredBy": ["step_33f64941"],
}


def test_a_row_a_step_answers_is_never_unmet() -> None:
    """The plasmodb apicoplast row: the PlasmoAP step answers it."""
    with pytest.raises(ValidationError, match="names no step that answers it"):
        RequirementCheck.model_validate({**_ANSWERED_ROW, "status": "unmet"})


def test_a_row_a_step_answers_and_no_record_shows_is_no_gap() -> None:
    row = RequirementCheck.model_validate({**_ANSWERED_ROW, "status": "met"})
    held = provisional_constraints([_stated(ConstraintKind.OTHER, _APICOPLAST)])

    gaps = check_gaps(
        structure=None,
        words=[],
        review=VerificationReview(requirements=[row]),
        requirements=held,
    )

    assert gaps == []


def test_a_combine_that_joins_its_steps_another_way_names_no_answer() -> None:
    with pytest.raises(ValidationError, match="names no step that answers it"):
        RequirementCheck(
            text="A or B",
            turn=1,
            answered_by=["c_a", "c_b"],
            how="structure",
            status="unmet",
        )


def test_a_row_the_records_leave_short_is_either_unshown_or_unjudged() -> None:
    with pytest.raises(ValidationError, match="either unshown or unjudged"):
        RequirementCheck(
            text="RNA-binding domain",
            turn=1,
            answered_by=["c_rbd"],
            how="parameter",
            status="met",
            no_record_shows_it=True,
            no_record_judged_it=True,
        )


def test_a_row_no_record_judged_is_a_gap_of_its_own() -> None:
    row = RequirementCheck(
        text="RNA-binding domain",
        turn=1,
        answered_by=["c_rbd"],
        how="parameter",
        status="met",
        no_record_judged_it=True,
    )

    gaps = check_gaps(
        structure=None,
        words=[],
        review=VerificationReview(requirements=[row]),
        requirements=_HELD,
    )

    assert [(g.sentence, g.fails_the_check) for g in gaps] == [
        ("'RNA-binding domain': no sampled record judged it", False)
    ]
    assert row.shown_status == "unjudged"


def test_an_unmet_row_fails_the_check() -> None:
    gap = RequirementGap(text="RNA-binding domain", status="unmet")

    assert (gap.sentence, gap.fails_the_check) == (
        "'RNA-binding domain': nothing in the strategy answers it",
        True,
    )
