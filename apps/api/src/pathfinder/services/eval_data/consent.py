"""The eval-data consent flag and the notice marker beside it.

Consent is on by default. Turning it off stops extraction and clears whatever
the user already has in the staging queue, in the same transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.eval_staging import delete_staged_for_user
from pathfinder.platform.errors import NotFoundError


class PrivacySettings(CamelModel):
    """What the user has decided about eval data, and whether they were told."""

    model_config = ConfigDict(frozen=True)

    eval_data_consent: bool
    notice_seen: bool


class PrivacyUpdate(CamelModel):
    """A change to one or both of the two flags. An unset field is unchanged."""

    model_config = ConfigDict(frozen=True)

    eval_data_consent: bool | None = None
    notice_seen: bool | None = None


def _settings_of(user: User) -> PrivacySettings:
    return PrivacySettings(
        eval_data_consent=user.eval_data_consent,
        notice_seen=user.eval_notice_seen_at is not None,
    )


async def _load(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError(title="Account not found", detail=str(user_id))
    return user


async def read_privacy(session: AsyncSession, user_id: UUID) -> PrivacySettings:
    """The user's current eval-data decision."""
    return _settings_of(await _load(session, user_id))


async def update_privacy(
    session: AsyncSession,
    user_id: UUID,
    update: PrivacyUpdate,
) -> PrivacySettings:
    """Apply the change. An opt-out also clears the user's staged candidates."""
    user = await _load(session, user_id)
    if update.eval_data_consent is not None:
        user.eval_data_consent = update.eval_data_consent
        if not update.eval_data_consent:
            await delete_staged_for_user(session, user_id=user_id)
    if update.notice_seen is not None:
        user.eval_notice_seen_at = datetime.now(UTC) if update.notice_seen else None
    await session.commit()
    return _settings_of(user)


__all__ = ["PrivacySettings", "PrivacyUpdate", "read_privacy", "update_privacy"]
