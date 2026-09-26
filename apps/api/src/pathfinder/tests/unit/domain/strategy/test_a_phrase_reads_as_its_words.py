"""A phrase reads as its runs of letters and digits, in its own spelling or folded."""

from __future__ import annotations

from pathfinder.domain.strategy.words import names_a_run_of, spelled_words, words_of


def test_the_words_keep_the_spelling_of_the_phrase() -> None:
    assert spelled_words("P. falciparum 3D7, exported-to host") == [
        "P",
        "falciparum",
        "3D7",
        "exported",
        "to",
        "host",
    ]


def test_the_folded_words_read_the_same_runs_in_lower_case() -> None:
    assert words_of("Plasmodium FALCIPARUM 3D7") == ["plasmodium", "falciparum", "3d7"]


_ROW = "Also keep only those predicted to be exported to the host cell"


def test_a_run_of_three_words_with_two_content_words_names_the_phrase() -> None:
    assert names_a_run_of("It states 'exported to the host cell.'", _ROW)


def test_a_run_of_filler_words_names_nothing() -> None:
    assert not names_a_run_of("It is exported to the site.", _ROW)


def test_a_phrase_of_three_words_or_fewer_is_named_whole() -> None:
    assert [names_a_run_of("Use sense counts here.", "Use sense counts")] == [True]
    assert [names_a_run_of("The sense of it.", "Use sense counts")] == [False]
