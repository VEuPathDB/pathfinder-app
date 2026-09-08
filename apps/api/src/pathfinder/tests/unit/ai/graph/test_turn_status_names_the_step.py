"""A waiting turn says which step it is on, not one word for all of them."""

from __future__ import annotations

from pathfinder.ai.graph.turn_status import (
    READING_THE_THREAD,
    RECALLING_EARLIER_WORK,
    turn_step_status,
)


def test_each_step_has_its_own_label() -> None:
    assert RECALLING_EARLIER_WORK != READING_THE_THREAD


def test_a_step_status_waits_on_no_model() -> None:
    chunk = turn_step_status(RECALLING_EARLIER_WORK)

    assert chunk.data["label"] == RECALLING_EARLIER_WORK
    assert chunk.data["waitingOnLlm"] is False


def test_the_labels_read_as_plain_english() -> None:
    for label in (RECALLING_EARLIER_WORK, READING_THE_THREAD):
        assert label[0].isupper()
        assert "..." not in label
        assert len(label.split()) <= 4
