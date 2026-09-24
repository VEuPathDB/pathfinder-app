"""The providers a researcher may key, the keys one turn runs under, and who pays."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, get_args

from assistant_core.platform.types import ModelProvider, PaidBy
from pydantic import SecretStr, TypeAdapter

type KeyableProvider = Literal["openai", "anthropic", "google"]

KEYABLE_PROVIDERS: tuple[KeyableProvider, ...] = get_args(KeyableProvider.__value__)

PROVIDER_NAMES: Mapping[KeyableProvider, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
}

_PROVIDER = TypeAdapter[ModelProvider](ModelProvider)


class KeyRefusal(StrEnum):
    """Why a stored key cannot pay for a turn."""

    # The provider answered that it does not accept the key.
    INVALID = "invalid"
    # The server secret no longer opens the stored ciphertext.
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class RefusedKey:
    """The researcher's key for the provider exists and cannot be used."""

    provider: KeyableProvider
    refusal: KeyRefusal


@dataclass(frozen=True)
class NobodyPays:
    """Neither the researcher nor the deployment holds a key for the provider."""

    provider: ModelProvider


type Payer = PaidBy | RefusedKey | NobodyPays


@dataclass(frozen=True)
class KeyStatuses:
    """The standing of each live key of one researcher, without its value."""

    active: frozenset[KeyableProvider] = frozenset()
    refused: Mapping[KeyableProvider, KeyRefusal] = field(default_factory=dict)

    def payer(
        self, provider: ModelProvider, deployment: frozenset[ModelProvider]
    ) -> Payer:
        """A live key pays for its provider; a refused one pays for nothing."""
        for keyable, refusal in self.refused.items():
            if keyable == provider:
                return RefusedKey(provider=keyable, refusal=refusal)
        if provider in self.active:
            return PaidBy.USER
        if provider in deployment:
            return PaidBy.DEPLOYMENT
        return NobodyPays(provider=provider)


@dataclass(frozen=True)
class ProviderKeyring:
    """The keys one turn runs under. Each value prints masked."""

    active: Mapping[KeyableProvider, SecretStr] = field(default_factory=dict)
    refused: Mapping[KeyableProvider, KeyRefusal] = field(default_factory=dict)

    def statuses(self) -> KeyStatuses:
        return KeyStatuses(active=frozenset(self.active), refused=dict(self.refused))

    def keyed(
        self, provider: ModelProvider
    ) -> tuple[KeyableProvider, SecretStr] | None:
        """The live key that pays for ``provider``, under its keyable name."""
        return next(
            (
                (keyable, key)
                for keyable, key in self.active.items()
                if keyable == provider
            ),
            None,
        )


def provider_name(provider: ModelProvider) -> str:
    """The name a researcher reads for ``provider``."""
    return next(
        (name for keyable, name in PROVIDER_NAMES.items() if keyable == provider),
        provider.capitalize(),
    )


def provider_of(model_id: str) -> ModelProvider:
    """The provider a ``provider:model`` id names."""
    return _PROVIDER.validate_python(model_id.partition(":")[0])
