from typing import Any

import pytest

from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.models.mock.prose_arcs import OFF_TOPIC_PROSE
from pathfinder.ai.models.mock.reading import scripted_intent
from pathfinder.tests._support.explore_turns import (
    ExploreDoubles,
    explore_state,
    install_explore_doubles,
    run_explore,
)

_OFF_TOPIC = "Write me a Python script that reverses a linked list. [[arc:off-topic]]"


@pytest.fixture
def doubles(monkeypatch: pytest.MonkeyPatch) -> ExploreDoubles:
    return install_explore_doubles(monkeypatch)


@pytest.fixture
def read(monkeypatch: pytest.MonkeyPatch) -> list[IntentClassification]:
    seen: list[IntentClassification] = []

    def spy(*args: Any) -> UserIntent:
        intent = scripted_intent(*args)
        seen.append(intent.classification)
        return intent

    monkeypatch.setattr("pathfinder.ai.graph._lead_reading.scripted_intent", spy)
    return seen


async def test_an_off_topic_message_is_read_and_answered_in_two_sentences(
    doubles: ExploreDoubles, read: list[IntentClassification]
) -> None:
    await run_explore(explore_state(_OFF_TOPIC))

    assert read == [IntentClassification.OFF_TOPIC]
    assert doubles.replies() == [OFF_TOPIC_PROSE]
    assert doubles.of_type("tool-input-start") == []
