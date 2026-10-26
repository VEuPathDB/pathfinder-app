"""A caveat a step row already draws, or a column a caveat already shows, is known
by its key."""

from __future__ import annotations

from pathfinder.domain.caveat_rows import drawn_by_a_row, sampled_column
from pathfinder.domain.caveats import PhraseCaveat, SampleCaveat
from pathfinder.tests._support.column_fits import tm_fit

_PHRASE = PhraseCaveat(
    criterion_id="c_text",
    param_display_name="Text term",
    value="merozoite surface",
    words_count=412,
    phrase_count=37,
)


def test_a_value_caveat_a_row_notes_is_drawn_by_that_row() -> None:
    assert drawn_by_a_row(_PHRASE, {("c_text", "Text term")}) is True


def test_a_value_caveat_no_row_notes_is_not_drawn_by_a_row() -> None:
    assert drawn_by_a_row(_PHRASE, {("c_text", "Organism")}) is False


def test_a_sample_caveat_shows_its_column_and_no_other_caveat_shows_one() -> None:
    fit = tm_fit(12, 40)

    assert [sampled_column(SampleCaveat(fit=fit)), sampled_column(_PHRASE)] == [
        fit.column_key,
        None,
    ]
