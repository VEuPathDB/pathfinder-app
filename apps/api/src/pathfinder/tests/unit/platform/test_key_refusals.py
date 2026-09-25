"""A provider refusal of a key is read from a body the provider sends or documents.

Every fixture is written by ``pathfinder.devtools.provider_refusals``: a recorded
body is one a provider sent, and a documented body is copied from the
provider's error reference, whose URL the fixture names.
"""

from __future__ import annotations

import pytest

from pathfinder.devtools.provider_refusals import (
    ProviderRefusal,
    every_refusal,
    load_refusal,
)
from pathfinder.domain.provider_keys import (
    KEYABLE_PROVIDERS,
    KeyableProvider,
    KeyRefusal,
)
from pathfinder.platform.key_refusals import classify_refusal

_FIXTURES = every_refusal()


@pytest.mark.parametrize("name", sorted(_FIXTURES))
def test_every_fixture_classifies_as_the_refusal_it_names(name: str) -> None:
    fixture = _FIXTURES[name]

    assert classify_refusal(fixture.provider, fixture.status, fixture.body) is (
        fixture.refusal
    )


def test_the_fixtures_name_what_was_recorded_and_what_was_documented() -> None:
    assert {
        name: (one.provenance, one.status, one.refusal)
        for name, one in _FIXTURES.items()
    } == {
        "anthropic-forbidden": ("documented", 403, KeyRefusal.FORBIDDEN),
        "anthropic-invalid-key": ("recorded", 401, KeyRefusal.INVALID),
        "anthropic-no-credit": ("recorded", 400, KeyRefusal.NO_CREDIT),
        "anthropic-no-credit-billing": ("documented", 402, KeyRefusal.NO_CREDIT),
        "google-forbidden": ("documented", 403, KeyRefusal.FORBIDDEN),
        "google-invalid-key": ("recorded", 400, KeyRefusal.INVALID),
        "google-no-credit": ("documented", 402, KeyRefusal.NO_CREDIT),
        "openai-invalid-key": ("recorded", 401, KeyRefusal.INVALID),
        "openai-no-credit": ("documented", 429, KeyRefusal.NO_CREDIT),
        "openai-no-credit-quota": ("documented", 429, KeyRefusal.NO_CREDIT),
    }


def test_a_documented_body_cites_the_page_it_was_read_from() -> None:
    documented = [one for one in _FIXTURES.values() if one.provenance == "documented"]

    assert documented
    assert [
        one.source for one in documented if not one.source.startswith("https://")
    ] == []


def test_a_fixture_that_cites_no_page_is_not_documented() -> None:
    with pytest.raises(ValueError, match="cites"):
        ProviderRefusal.model_validate(
            {
                **load_refusal("google-forbidden").model_dump(mode="json"),
                "source": "copied by hand",
            }
        )


@pytest.mark.parametrize("provider", KEYABLE_PROVIDERS)
def test_a_rate_limit_or_an_outage_is_not_a_refusal(provider: KeyableProvider) -> None:
    body = load_refusal(f"{provider}-invalid-key").body

    assert {s: classify_refusal(provider, s, body) for s in (429, 500, 503)} == {
        429: None,
        500: None,
        503: None,
    }


def test_an_openai_rate_limit_is_not_a_quota() -> None:
    rate_limit = {
        "message": "Rate limit reached for requests",
        "type": "requests",
        "code": "rate_limit_exceeded",
        "param": None,
    }

    quota = load_refusal("openai-no-credit").body

    assert [
        classify_refusal("openai", 429, rate_limit),
        classify_refusal("openai", 429, quota),
    ] == [None, KeyRefusal.NO_CREDIT]


def test_the_openai_region_refusal_is_not_a_refusal_of_the_key() -> None:
    """The region is the deployment's, so another key meets the same answer."""
    region = {
        "message": "Country, region, or territory not supported",
        "type": "request_forbidden",
        "code": "unsupported_country_region_territory",
        "param": None,
    }

    assert [
        classify_refusal("openai", 403, region),
        classify_refusal("google", 403, load_refusal("google-forbidden").body),
    ] == [None, KeyRefusal.FORBIDDEN]


def test_an_anthropic_bad_request_about_the_prompt_is_not_a_refusal() -> None:
    about_the_prompt = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "adaptive thinking is not supported on this model",
        },
    }
    about_the_credit = load_refusal("anthropic-no-credit").body

    assert [
        classify_refusal("anthropic", 400, about_the_prompt),
        classify_refusal("anthropic", 400, about_the_credit),
    ] == [None, KeyRefusal.NO_CREDIT]


def test_a_google_bad_request_about_the_prompt_is_not_a_refusal() -> None:
    about_the_prompt = {
        "error": {
            "code": 400,
            "message": "Request contains an invalid argument.",
            "status": "INVALID_ARGUMENT",
        }
    }
    about_the_key = load_refusal("google-invalid-key").body

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
    openai = load_refusal("openai-invalid-key").body

    assert [
        classify_refusal("anthropic", 401, openai),
        classify_refusal("openai", 401, openai),
    ] == [None, KeyRefusal.INVALID]
