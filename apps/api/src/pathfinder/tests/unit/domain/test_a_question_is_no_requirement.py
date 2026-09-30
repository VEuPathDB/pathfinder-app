"""A question in the researcher's message is answered in the reply and is
never a requirement row of the check."""

from __future__ import annotations

from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.question_rows import ResearcherAsk, without_questions

_MESSAGES = [
    (
        "Toxoplasma gondii ME49 dense granule proteins more expressed in "
        "bradyzoites than in tachyzoites."
    ),
    (
        "I can't see which fold-change cutoff you used. Please loosen it to "
        "1.5-fold and show me how the count changes."
    ),
    (
        "Why did the count fall? What fold change is actually applied now? "
        "What was it before? I want a plain 1.5-fold change (bradyzoite over "
        "tachyzoite)."
    ),
]


def _row(text: str, turn: int) -> RequirementCheck:
    return RequirementCheck(
        text=text, turn=turn, how="analysis", status="unexpressed", note=""
    )


def test_the_questions_the_researcher_asked_file_no_row() -> None:
    kept = [
        _row("loosen it to 1.5-fold", 2),
        _row("a plain 1.5-fold change (bradyzoite over tachyzoite)", 3),
    ]
    review = VerificationReview(
        requirements=[
            kept[0],
            _row("what fold change is actually applied now?", 3),
            _row("what was it before", 3),
            kept[1],
        ]
    )

    assert without_questions(review, _MESSAGES).requirements == kept


def test_a_request_asked_as_a_question_keeps_its_requirements() -> None:
    review = VerificationReview(requirements=[_row("dense granule proteins", 1)])

    assert (
        without_questions(review, ["Can you find the dense granule proteins of ME49?"])
        == review
    )


_GIARDIA = [
    "Ankyrin repeat genes in Giardia Assemblage B isolate GS.",
    (
        "run the same ankyrin repeat search on Assemblage A isolate WB and tell "
        "me how the two counts compare?"
    ),
]


def test_a_comparison_the_gate_read_as_an_ask_files_no_row() -> None:
    wb = _row("Assemblage A isolate WB", 2)
    review = VerificationReview(
        requirements=[wb, _row("tell me how the two counts compare", 2)]
    )
    asks = [
        ResearcherAsk(message=_GIARDIA[1], text="tell me how the two counts compare")
    ]

    assert without_questions(review, _GIARDIA, asks).requirements == [wb]


_TM = [
    "Acanthamoeba castellanii Neff secreted proteins with two or more TM domains.",
    (
        "Let's compare both first. How many of the 227 would remain if the "
        "minimum were 3 TM domains instead of 2? Then I'll decide."
    ),
]


def test_a_message_the_gate_classified_as_a_question_files_no_row() -> None:
    kept = _row("two or more TM domains", 1)
    review = VerificationReview(
        requirements=[kept, _row("how many of the 227 would remain", 2)]
    )
    asks = [ResearcherAsk(message=_TM[1], text=_TM[1], question=True)]

    assert without_questions(review, _TM, asks).requirements == [kept]


def test_an_ask_of_a_later_message_keeps_a_requirement_it_repeats() -> None:
    kept = _row("Assemblage B isolate GS", 1)
    review = VerificationReview(requirements=[kept])
    asks = [
        ResearcherAsk(
            message=_GIARDIA[1],
            text="how the Assemblage B isolate GS count compares with WB",
        )
    ]

    assert without_questions(review, _GIARDIA, asks) == review


# The vectorbase check: the gate put the whole request in its asks.
_OBP = "Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3"


def _checked(text: str, status: str, answered_by: list[str]) -> RequirementCheck:
    return RequirementCheck.model_validate(
        {
            "text": text,
            "turn": 1,
            "answeredBy": answered_by,
            "how": "parameter",
            "status": status,
        }
    )


_OBP_ROWS = [
    _checked("Aedes aegypti LVP_AGWG", "met", ["step_4fa6fd77", "step_986d27dc"]),
    _checked("genes", "unmet", []),
    _checked("chromosome 3", "met", ["step_986d27dc"]),
    _checked("odorant-binding protein", "unmet", []),
    _checked(_OBP, "met", ["step_230c6ccc"]),
]


def test_an_ask_that_holds_a_rows_words_erases_no_row() -> None:
    review = VerificationReview(requirements=_OBP_ROWS)
    asks = [
        ResearcherAsk(
            message=f"{_OBP}.", text="odorant-binding protein genes on chromosome 3"
        )
    ]

    assert without_questions(review, [f"{_OBP}."], asks) == review


def test_a_row_that_restates_an_ask_is_dropped() -> None:
    kept = _row("Assemblage A isolate WB", 2)
    review = VerificationReview(
        requirements=[kept, _row("how the two counts compare", 2)]
    )
    asks = [ResearcherAsk(message=_GIARDIA[1], text="How the two counts compare")]

    assert without_questions(review, _GIARDIA, asks).requirements == [kept]
