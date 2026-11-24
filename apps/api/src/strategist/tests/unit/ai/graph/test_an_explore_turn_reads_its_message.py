from typing import Any

import pytest

from strategist.ai.graph import _lead_reading, explore_node
from strategist.ai.graph._lead_reading import MessageNotReadError
from strategist.ai.lead.intent import IntentClassification, UserIntent
from strategist.tests._support.explore_turns import (
    ExploreDoubles,
    explore_state,
    install_explore_doubles,
    run_explore,
)
from strategist.tests._support.scripted import scripted_with
from strategist_scripted.models.prose_arcs import OFF_TOPIC_PROSE
from strategist_scripted.models.reading import scripted_intent

_NOT_READ = "the reader's model did not answer"
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

    monkeypatch.setattr(_lead_reading, "scripted", scripted_with(intent=spy))
    return seen


async def test_an_off_topic_message_is_read_and_answered_in_two_sentences(
    doubles: ExploreDoubles, read: list[IntentClassification]
) -> None:
    await run_explore(explore_state(_OFF_TOPIC))

    assert read == [IntentClassification.OFF_TOPIC]
    assert doubles.replies() == [OFF_TOPIC_PROSE]
    assert doubles.of_type("tool-input-start") == []


async def test_a_message_the_reader_could_not_read_ends_the_turn_saying_so(
    doubles: ExploreDoubles, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _unread(*_args: Any, **_kwargs: Any) -> None:
        raise MessageNotReadError(_NOT_READ)

    monkeypatch.setattr(explore_node, "classify_the_words", _unread)

    await run_explore(explore_state("Which kinases are exported?"))

    assert doubles.replies() == [
        (
            "I could not read your message into its requirements: the reader's "
            "model did not answer. Nothing was changed. Send the message again."
        )
    ]
