"""The eval-data consent flag and the data statement version the user saw.

A copy for review is made only for a user who consents and who saw the
current statement. Turning consent off clears the user's staging queue in the
same transaction.
"""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, computed_field
from sqlalchemy import ColumnElement, and_
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.data_statement import DataStatementVersion
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.eval_staging import delete_staged_for_user
from pathfinder.platform.errors import NotFoundError


class PrivacySettings(CamelModel):
    model_config = ConfigDict(frozen=True)

    eval_data_consent: bool
    data_notice_seen: str | None

    @computed_field
    def notice_due(self) -> bool:
        return self.data_notice_seen != DataStatementVersion.CURRENT


class PrivacyUpdate(CamelModel):
    model_config = ConfigDict(frozen=True)

    eval_data_consent: bool


class DataNoticeContinue(CamelModel):
    model_config = ConfigDict(frozen=True)

    version: DataStatementVersion
    eval_data_consent: bool


def copies_allowed() -> ColumnElement[bool]:
    return and_(
        User.eval_data_consent.is_(True),
        User.data_notice_seen == DataStatementVersion.CURRENT.value,
    )


def _settings_of(user: User) -> PrivacySettings:
    return PrivacySettings(
        eval_data_consent=user.eval_data_consent,
        data_notice_seen=user.data_notice_seen,
    )


async def _load(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError(title="Account not found", detail=str(user_id))
    return user


async def _set_consent(session: AsyncSession, user: User, *, consent: bool) -> None:
    user.eval_data_consent = consent
    if not consent:
        await delete_staged_for_user(session, user_id=user.id)


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
    await _set_consent(session, user, consent=update.eval_data_consent)
    await session.commit()
    return _settings_of(user)


async def continue_past_the_data_notice(
    session: AsyncSession,
    user_id: UUID,
    choice: DataNoticeContinue,
) -> PrivacySettings:
    user = await _load(session, user_id)
    user.data_notice_seen = choice.version.value
    await _set_consent(session, user, consent=choice.eval_data_consent)
    await session.commit()
    return _settings_of(user)


__all__ = [
    "DataNoticeContinue",
    "PrivacySettings",
    "PrivacyUpdate",
    "continue_past_the_data_notice",
    "copies_allowed",
    "read_privacy",
    "update_privacy",
]
