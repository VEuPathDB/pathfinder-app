"""A tally's values reference renders the number of values alone, so the noun the
prose writes after it names them once and a clause names them, and a word for
none just before a reference that renders 0 says the count twice."""

from __future__ import annotations

import pytest

from pathfinder.domain.reply_references import prose_faults, render_reply
from pathfinder.domain.tally_facts import TallyFact, TallyRowFact
from pathfinder.domain.turn_facts import StepFact, TurnFacts

_ID = "tally_57ea13f0"
_TALLY = TallyFact(
    id=_ID,
    title="Proteins by Taxon Code",
    record_noun="protein",
    total=333932,
    distinct=61,
    rows=[TallyRowFact(value="pyxn", count=7666)],
)
_FACTS = TurnFacts(tallies=[_TALLY], record_noun="protein")
_PROSE = (
    f"The comparison covered [tally:{_ID}:values] taxon labels and [tally:{_ID}] "
    "overall."
)


def test_the_noun_after_a_values_reference_is_written_once() -> None:
    assert render_reply(_PROSE, _FACTS) == (
        "The comparison covered 61 taxon labels and 333,932 proteins overall."
    )


def test_a_values_reference_followed_by_its_noun_is_no_fault() -> None:
    assert prose_faults(_PROSE, _FACTS) == []


def test_values_written_after_the_reference_render_once() -> None:
    assert render_reply(f"Across [tally:{_ID}:values] values.", _FACTS) == (
        "Across 61 values."
    )


def test_the_tally_shows_its_number_of_values_alone() -> None:
    assert _TALLY.lines() == [
        "Proteins by Taxon Code",
        f"[tally:{_ID}] = 333,932 proteins",
        f"[tally:{_ID}:values] = 61",
        f"[tally:{_ID}.pyxn] = 7666",
    ]


_EMPTY = TurnFacts(
    steps=[StepFact(step_id="step_bd503b89", display_name="Intersect", count=0)],
    root_count=0,
    record_noun="protein",
)


@pytest.mark.parametrize(
    "prose",
    [
        "The build recovered from a zero-result search and returns [root].",
        "The empty step was dropped, and the final result holds [root].",
    ],
)
def test_a_word_for_none_elsewhere_in_the_clause_stands(prose: str) -> None:
    assert prose_faults(prose, _EMPTY) == []


def test_a_word_for_none_before_a_count_that_is_not_0_stands() -> None:
    facts = _EMPTY.model_copy(update={"root_count": 2744})

    assert prose_faults("The result holds no [root].", facts) == []
