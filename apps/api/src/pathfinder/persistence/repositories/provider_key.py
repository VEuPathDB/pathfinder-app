"""The live provider keys of one researcher in the calling application."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from assistant_core.platform.context import calling_application
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ColumnElement, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.provider_keys import KeyableProvider, KeyRefusal
from pathfinder.persistence.models import UserProviderKey


class StoredProviderKey(BaseModel):
    """Read shape of one live key row. The ciphertext never prints."""

    model_config = ConfigDict(frozen=True, from_attributes=True, extra="ignore")

    user_id: UUID
    application_id: str
    provider: KeyableProvider
    hint: str
    ciphertext: bytes = Field(repr=False)
    created_at: datetime
    refused_at: datetime | None = None
    refusal: KeyRefusal | None = None


class ProviderKeyRepository:
    """Every read and write scopes to the calling application."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _live(self, user_id: UUID) -> list[ColumnElement[bool]]:
        return [
            UserProviderKey.user_id == user_id,
            UserProviderKey.application_id == calling_application(),
            UserProviderKey.revoked_at.is_(None),
        ]

    async def live_rows(self, user_id: UUID) -> list[StoredProviderKey]:
        result = await self.session.execute(
            select(UserProviderKey)
            .where(*self._live(user_id))
            .order_by(UserProviderKey.provider)
        )
        return [StoredProviderKey.model_validate(row) for row in result.scalars()]

    async def revoke(self, user_id: UUID, provider: KeyableProvider) -> bool:
        """Revoke the live key and drop its ciphertext. False when none was live."""
        result = await self.session.execute(
            update(UserProviderKey)
            .where(*self._live(user_id), UserProviderKey.provider == provider)
            .values(revoked_at=datetime.now(UTC), ciphertext=None)
            .returning(UserProviderKey.id)
        )
        return result.first() is not None

    async def replace_live(
        self,
        user_id: UUID,
        provider: KeyableProvider,
        *,
        ciphertext: bytes,
        hint: str,
    ) -> StoredProviderKey:
        """Revoke the live key, if any, and store the new one in its place."""
        await self.revoke(user_id, provider)
        row = UserProviderKey(
            user_id=user_id,
            application_id=calling_application(),
            provider=provider,
            ciphertext=ciphertext,
            hint=hint,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return StoredProviderKey.model_validate(row)

    async def mark_refused(
        self, user_id: UUID, provider: KeyableProvider, refusal: KeyRefusal
    ) -> None:
        """Mark the live key refused; a later turn is refused before it runs."""
        await self.session.execute(
            update(UserProviderKey)
            .where(*self._live(user_id), UserProviderKey.provider == provider)
            .values(refused_at=datetime.now(UTC), refusal=refusal.value)
        )
