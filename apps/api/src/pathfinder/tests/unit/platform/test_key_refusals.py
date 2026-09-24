"""A provider refusal of a key is read from the body the provider really sends.

The three bodies are recorded by ``pathfinder.devtools.provider_refusals``.
"""

from __future__ import annotations

import pytest

from pathfinder.devtools.provider_refusals import load_recorded
from pathfinder.domain.provider_keys import (
    KEYABLE_PROVIDERS,
    KeyableProvider,
    KeyRefusal,
)
from pathfinder.platform.key_refusals import classify_refusal


@pytest.mark.parametrize("provider", KEYABLE_PROVIDERS)
def test_the_recorded_refusal_of_a_key_is_an_invalid_key(
    provider: KeyableProvider,
) -> None:
    recorded = load_recorded(provider)

    assert classify_refusal(provider, recorded.status, recorded.body) is (
        KeyRefusal.INVALID
    )


def test_the_recorded_statuses_are_the_ones_measured() -> None:
    assert {p: load_recorded(p).status for p in KEYABLE_PROVIDERS} == {
        "openai": 401,
        "anthropic": 401,
        "google": 400,
    }


@pytest.mark.parametrize("provider", KEYABLE_PROVIDERS)
def test_a_rate_limit_or_an_outage_is_not_a_refusal(provider: KeyableProvider) -> None:
    body = load_recorded(provider).body

    assert {s: classify_refusal(provider, s, body) for s in (429, 500, 503)} == {
        429: None,
        500: None,
        503: None,
    }


def test_a_google_bad_request_about_the_prompt_is_not_a_refusal() -> None:
    about_the_prompt = {
        "error": {
            "code": 400,
            "message": "Request contains an invalid argument.",
            "status": "INVALID_ARGUMENT",
        }
    }
    about_the_key = load_recorded("google").body

    assert [
        classify_refusal("google", 400, about_the_prompt),
        classify_refusal("google", 400, about_the_key),
    ] == [None, KeyRefusal.INVALID]


def test_a_body_of_another_shape_is_not_a_refusal() -> None:
    bodies: list[object] = [None, "upstream connect error", ["x"]]

    assert [classify_refusal("openai", 401, body) for body in bodies] == [
        None,
        None,
        None,
    ]


def test_one_provider_body_does_not_classify_another_provider() -> None:
    openai = load_recorded("openai").body

    assert [
        classify_refusal("anthropic", 401, openai),
        classify_refusal("openai", 401, openai),
    ] == [None, KeyRefusal.INVALID]
