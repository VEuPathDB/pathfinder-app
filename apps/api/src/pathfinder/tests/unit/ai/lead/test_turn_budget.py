"""The budget one Lead turn runs under, and what it says when it reaches it."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic_ai.usage import RunUsage

from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.turn_budget import (
    OFF_TOPIC_TURN_TOKEN_LIMIT,
    lead_turn_budget_message,
    lead_usage_limits,
    off_topic_budget_stop,
)
from pathfinder.platform.config import get_settings
from pathfinder.tests.unit.ai.lead.conftest import user_intent

_CONFIGURED_LIMIT = 123456
_DEFAULT_LIMIT = 600_000
_TAIL = "Narrow the request and send it again, and I will start a fresh turn on it."


@pytest.fixture
def configured_limit(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    monkeypatch.setenv("LEAD_TURN_TOKEN_LIMIT", str(_CONFIGURED_LIMIT))
    get_settings.cache_clear()
    yield _CONFIGURED_LIMIT
    get_settings.cache_clear()


def _usage(total_tokens: int) -> RunUsage:
    return RunUsage(input_tokens=total_tokens)


def _off_topic() -> UserIntent:
    return user_intent(IntentClassification.OFF_TOPIC)


def test_the_turn_budget_is_the_configured_token_ceiling(
    configured_limit: int,
) -> None:
    assert lead_usage_limits().total_tokens_limit == configured_limit


def test_the_turn_budget_covers_the_leads_own_calls_and_tokens() -> None:
    limits = lead_usage_limits()

    assert (limits.request_limit, limits.tool_calls_limit) == (80, 80)
    assert limits.total_tokens_limit == _DEFAULT_LIMIT


def test_each_turn_gets_its_own_limits_object() -> None:
    """One turn's ceiling is never the object another turn is judged by."""
    first = lead_usage_limits()

    assert lead_usage_limits() is not first
    assert lead_usage_limits() == first


def test_the_turn_budget_message_names_the_whole_turn_ceiling() -> None:
    assert lead_turn_budget_message() == (
        f"I stopped this turn at its budget of 80 model calls and "
        f"{_DEFAULT_LIMIT} tokens. {_TAIL}"
    )


def test_the_off_topic_stop_names_the_ceiling_it_stopped_at() -> None:
    assert off_topic_budget_stop(
        _usage(OFF_TOPIC_TURN_TOKEN_LIMIT + 1), _off_topic()
    ) == (
        f"I stopped this turn at its budget of 80 model calls and "
        f"{OFF_TOPIC_TURN_TOKEN_LIMIT} tokens. {_TAIL}"
    )


def test_the_stop_fires_only_for_an_off_topic_turn_over_its_ceiling() -> None:
    at = OFF_TOPIC_TURN_TOKEN_LIMIT
    fired = {
        "off topic, one token over": off_topic_budget_stop(_usage(at + 1), _off_topic())
        is not None,
        "off topic, at the ceiling": off_topic_budget_stop(_usage(at), _off_topic())
        is not None,
        "a question about the data, far over": off_topic_budget_stop(
            _usage(at * 2), user_intent(IntentClassification.FOLLOW_UP_QUESTION)
        )
        is not None,
        "not classified yet, far over": off_topic_budget_stop(_usage(at * 2), None)
        is not None,
    }

    assert fired == {
        "off topic, one token over": True,
        "off topic, at the ceiling": False,
        "a question about the data, far over": False,
        "not classified yet, far over": False,
    }
