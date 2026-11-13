from __future__ import annotations

from typing import Annotated

from pydantic import TypeAdapter

from strategist.domain.clipped import clipped_text, text_clipped_to
from strategist.domain.strategy.questions import OpenQuestion

_MEASURED = (
    "Should the list hold Plasmodium falciparum 3D7 genes whose products are "
    "exported into the host erythrocyte membrane and bind a host protein, as the "
    "PEXEL motif and the published interactome suggest, or do you have a "
    "literature-validated list of parasite genes and host-protein targets to "
    "restrict the search to, one gene per line?"
)


def test_a_text_within_the_limit_is_unchanged() -> None:
    assert clipped_text("Keep it. All of it!", 19) == "Keep it. All of it!"


def test_a_text_over_the_limit_ends_at_the_last_sentence_that_fits() -> None:
    text = "Which organism do you mean? The site lists three of that name."

    assert clipped_text(text, 40) == "Which organism do you mean?"


def test_a_sentence_end_keeps_its_punctuation_at_the_limit() -> None:
    text = "One. Two! Three words here"

    assert clipped_text(text, 9) == "One. Two!"


def test_with_no_sentence_end_that_fits_the_text_ends_at_a_word_and_an_ellipsis() -> (
    None
):
    text = "a literature-validated list of parasite genes and host-protein targets"

    assert clipped_text(text, 40) == "a literature-validated list of..."


def test_a_single_word_over_the_limit_is_cut_with_an_ellipsis() -> None:
    assert clipped_text("x" * 30, 10) == "xxxxxxx..."


def test_a_clipped_text_never_passes_the_limit() -> None:
    adapter: TypeAdapter[str] = TypeAdapter(Annotated[str, text_clipped_to(20)])

    clipped = adapter.validate_python("words and more words and more words")

    assert clipped == "words and more..."


def test_the_measured_question_reads_whole_on_a_card() -> None:
    assert len(_MEASURED) == 330
    assert OpenQuestion(question=_MEASURED).question == _MEASURED
