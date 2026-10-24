"""Each emitted reply takes a note label of its own."""

from __future__ import annotations

import re

from pathfinder.ai.graph.note_labels import note_label


def test_each_reply_takes_a_note_label_of_its_own() -> None:
    labels = {note_label() for _ in range(50)}

    assert len(labels) == 50
    assert all(re.fullmatch(r"n[0-9a-f]{8}-", label) for label in labels)
