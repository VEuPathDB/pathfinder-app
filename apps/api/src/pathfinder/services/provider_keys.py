"""A researcher's provider keys: stored sealed, read in the worker, never shown.

The payer rule is ``domain.provider_keys``; this module applies it to stored
rows and names the refusal a request or a turn meets.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Literal, get_args
from uuid import UUID

from assistant_core.platform.context import calling_application
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ModelProvider, PaidBy
from cryptography.exceptions import InvalidTag
from pydantic import ConfigDict, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.provider_keys import (
    KeyableProvider,
    KeyRefusal,
    KeyStatuses,
    NobodyPays,
    ProviderKeyring,
    RefusedKey,
    provider_name,
    provider_of,
)
from pathfinder.persistence.repositories import (
    ProviderKeyRepository,
    StoredProviderKey,
)
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import (
    ProviderKeyRefusedError,
    ProviderKeysDisabledError,
    ProviderKeyUnreadableError,
    ProviderNotConfiguredError,
)
from pathfinder.platform.provider_key_cipher import ProviderKeyCipher, hint_for, key_aad


class ProviderKeyView(CamelModel):
    """One stored key as the researcher sees it: never the key, only its tail."""

    model_config = ConfigDict(frozen=True)

    provider: KeyableProvider
    hint: str
    status: Literal["active", "refused"]
    refusal: KeyRefusal | None = None
    created_at: datetime
    refused_at: datetime | None = None


def _view(row: StoredProviderKey) -> ProviderKeyView:
    return ProviderKeyView(
        provider=row.provider,
        hint=row.hint,
        status="active" if row.refusal is None else "refused",
        refusal=row.refusal,
        created_at=row.created_at,
        refused_at=row.refused_at,
    )


def _statuses(rows: Iterable[StoredProviderKey]) -> KeyStatuses:
    listed = list(rows)
    return KeyStatuses(
        active=frozenset(row.provider for row in listed if row.refusal is None),
        refused={
            row.provider: row.refusal for row in listed if row.refusal is not None
        },
    )


def _cipher() -> ProviderKeyCipher:
    cipher = get_settings().provider_key_cipher
    if cipher is None:
        raise ProviderKeysDisabledError
    return cipher


def keys_enabled() -> bool:
    """Whether this deployment holds a secret to seal a researcher's key under."""
    return get_settings().provider_key_cipher is not None


async def list_keys(session: AsyncSession, user_id: UUID) -> list[ProviderKeyView]:
    rows = await ProviderKeyRepository(session).live_rows(user_id)
    return [_view(row) for row in rows]


async def key_statuses(session: AsyncSession, user_id: UUID) -> KeyStatuses:
    """The standing of each live key. Nothing is decrypted."""
    return _statuses(await ProviderKeyRepository(session).live_rows(user_id))


def payers(statuses: KeyStatuses) -> dict[ModelProvider, PaidBy]:
    """Who pays for each provider a model may be picked from."""
    deployment = get_settings().deployment_providers
    paid: dict[ModelProvider, PaidBy] = {}
    for provider in get_args(ModelProvider.__value__):
        match statuses.payer(provider, deployment):
            case PaidBy() as payer:
                paid[provider] = payer
            case _:
                pass
    return paid


def require_payers(
    model_ids: Iterable[str], statuses: KeyStatuses
) -> dict[ModelProvider, PaidBy]:
    """Who pays for each provider the models name, or the refusal that stops them."""
    deployment = get_settings().deployment_providers
    paid: dict[ModelProvider, PaidBy] = {}
    named: list[ModelProvider] = [provider_of(model_id) for model_id in model_ids]
    for provider in dict.fromkeys(named):
        match statuses.payer(provider, deployment):
            case RefusedKey(refusal=KeyRefusal.UNREADABLE):
                raise ProviderKeyUnreadableError(provider_name(provider))
            case RefusedKey():
                raise ProviderKeyRefusedError(provider_name(provider))
            case NobodyPays():
                raise ProviderNotConfiguredError(provider_name(provider))
            case PaidBy() as payer:
                paid[provider] = payer
    return paid


async def store_key(
    session: AsyncSession,
    user_id: UUID,
    provider: KeyableProvider,
    key: SecretStr,
) -> ProviderKeyView:
    """Seal ``key`` and make it the live key for ``provider``."""
    repository = ProviderKeyRepository(session)
    live = await repository.replace_live(
        user_id,
        provider,
        ciphertext=_cipher().seal(key, aad=_aad_for(user_id, provider)),
        hint=hint_for(key),
    )
    return _view(live)


def _aad_for(user_id: UUID, provider: KeyableProvider) -> bytes:
    return key_aad(user_id, calling_application(), provider)


async def revoke_key(
    session: AsyncSession, user_id: UUID, provider: KeyableProvider
) -> bool:
    """Revoke the live key. A revoked key is never read again."""
    return await ProviderKeyRepository(session).revoke(user_id, provider)


def _opened(
    row: StoredProviderKey, cipher: ProviderKeyCipher | None
) -> SecretStr | None:
    if cipher is None:
        return None
    aad = key_aad(row.user_id, row.application_id, row.provider)
    try:
        return cipher.open(row.ciphertext, aad=aad)
    except InvalidTag:
        return None


async def load_keyring(user_id: UUID) -> ProviderKeyring:
    """Open the researcher's live keys for one turn.

    A key the server secret no longer opens is marked unreadable, and the turn
    that needs it is refused.
    """
    cipher = get_settings().provider_key_cipher
    active: dict[KeyableProvider, SecretStr] = {}
    refused: dict[KeyableProvider, KeyRefusal] = {}
    async with async_session_factory() as session:
        repository = ProviderKeyRepository(session)
        for row in await repository.live_rows(user_id):
            if row.refusal is not None:
                refused[row.provider] = row.refusal
                continue
            opened = _opened(row, cipher)
            if opened is None:
                refused[row.provider] = KeyRefusal.UNREADABLE
                await repository.mark_refused(
                    user_id, row.provider, KeyRefusal.UNREADABLE
                )
                continue
            active[row.provider] = opened
        await session.commit()
    return ProviderKeyring(active=active, refused=refused)


async def record_refusals(
    user_id: UUID, refusals: Mapping[KeyableProvider, KeyRefusal]
) -> None:
    """Mark each key a provider refused during a turn; the next turn is refused."""
    if not refusals:
        return
    async with async_session_factory() as session:
        repository = ProviderKeyRepository(session)
        for provider, refusal in refusals.items():
            await repository.mark_refused(user_id, provider, refusal)
        await session.commit()
