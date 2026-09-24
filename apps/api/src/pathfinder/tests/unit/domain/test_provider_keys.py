"""Who pays for a model: the researcher's live key, else the deployment's."""

from __future__ import annotations

from assistant_core.platform.types import ModelProvider, PaidBy
from pydantic import SecretStr

from pathfinder.domain.provider_keys import (
    KeyRefusal,
    KeyStatuses,
    NobodyPays,
    ProviderKeyring,
    RefusedKey,
    provider_name,
    provider_of,
)

_SENTINEL = "sk-proj-sentinel-0123456789WXYZ"
_DEPLOYMENT: frozenset[ModelProvider] = frozenset({"openai"})


def test_a_live_key_pays_for_its_provider_before_the_deployment() -> None:
    statuses = KeyStatuses(active=frozenset({"openai"}))

    assert statuses.payer("openai", _DEPLOYMENT) is PaidBy.USER


def test_the_deployment_pays_where_the_researcher_holds_no_key() -> None:
    assert KeyStatuses().payer("openai", _DEPLOYMENT) is PaidBy.DEPLOYMENT


def test_a_refused_key_is_never_replaced_by_the_deployment_key() -> None:
    statuses = KeyStatuses(refused={"openai": KeyRefusal.INVALID})

    assert statuses.payer("openai", _DEPLOYMENT) == RefusedKey(
        provider="openai", refusal=KeyRefusal.INVALID
    )


def test_a_provider_nobody_holds_a_key_for_is_not_payable() -> None:
    assert KeyStatuses().payer("anthropic", _DEPLOYMENT) == NobodyPays(
        provider="anthropic"
    )


def test_the_keyring_reports_the_standing_of_each_key_without_its_value() -> None:
    keyring = ProviderKeyring(
        active={"anthropic": SecretStr(_SENTINEL)},
        refused={"google": KeyRefusal.UNREADABLE},
    )

    assert keyring.statuses() == KeyStatuses(
        active=frozenset({"anthropic"}),
        refused={"google": KeyRefusal.UNREADABLE},
    )


def test_the_keyring_never_prints_a_key() -> None:
    keyring = ProviderKeyring(active={"openai": SecretStr(_SENTINEL)})

    assert repr(keyring) == (
        "ProviderKeyring(active={'openai': SecretStr('**********')}, refused={})"
    )


def test_a_model_id_names_its_provider() -> None:
    assert [
        provider_of("anthropic:claude-opus-5"),
        provider_of("google:gemini-3.6-flash"),
        provider_of("mock:deterministic"),
    ] == ["anthropic", "google", "mock"]


def test_the_keyring_names_the_key_that_pays_for_a_provider() -> None:
    key = SecretStr(_SENTINEL)
    keyring = ProviderKeyring(active={"anthropic": key})

    assert keyring.keyed("anthropic") == ("anthropic", key)
    assert keyring.keyed("openai") is None


def test_each_provider_has_the_name_a_researcher_reads() -> None:
    assert [provider_name(p) for p in ("openai", "anthropic", "google", "ollama")] == [
        "OpenAI",
        "Anthropic",
        "Google",
        "Ollama",
    ]
