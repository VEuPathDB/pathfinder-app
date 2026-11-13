"""A phrase reads as its runs of letters and digits, in its own spelling or folded."""

from __future__ import annotations

from strategist.domain.strategy.words import spelled_words, words_of


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
