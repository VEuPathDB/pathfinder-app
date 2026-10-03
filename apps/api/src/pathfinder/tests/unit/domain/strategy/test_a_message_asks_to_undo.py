"""A message asks to undo the last change when it says so in whole words."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.undo_words import asks_to_undo


@pytest.mark.parametrize(
    "message",
    [
        "Undo that, keep the intersection.",
        "please REVERT the last change",
        "Put it back the way it was",
        "go back to the intersection",
        "Roll back that edit",
    ],
)
def test_an_undo_phrase_asks_to_undo(message: str) -> None:
    assert asks_to_undo(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "flip the last combine to a UNION",
        "use the undone transcripts dataset",
        "reverted genes in 3D7",
        "put the signal peptide step first",
        "go to the strategy page",
        "back to back expression peaks",
    ],
)
def test_a_message_with_no_undo_phrase_does_not(message: str) -> None:
    assert asks_to_undo(message) is False
