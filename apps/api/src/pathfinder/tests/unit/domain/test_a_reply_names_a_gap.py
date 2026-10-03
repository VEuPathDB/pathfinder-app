"""A reply names a gap by two consecutive naming words of it, and a gap with no
naming word only by its whole text."""

from __future__ import annotations

import pytest

from pathfinder.domain.requirement_naming import named_in_prose

_REPLY = "The check found 3 genes at 0.05; the transmembrane domain step holds."


@pytest.mark.parametrize("text", ["the 3", "of the 0"])
def test_a_gap_with_no_naming_word_is_not_named_by_any_reply(text: str) -> None:
    assert named_in_prose("The strategy is built and verified.", text) is False


def test_a_gap_with_no_naming_word_is_named_by_its_whole_text() -> None:
    assert named_in_prose("Nothing is in the 3 yet.", "the 3") is True


def test_a_gap_is_named_by_two_consecutive_naming_words() -> None:
    assert (
        named_in_prose(_REPLY, "a transmembrane domain"),
        named_in_prose(_REPLY, "a signal peptide"),
    ) == (True, False)
