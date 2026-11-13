from __future__ import annotations

from uuid import UUID

from assistant_core.conversation.authz import assert_owner
from assistant_core.platform.pydantic_base import CamelModel
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from strategist.persistence.models import ConversationAccountRead, User
from strategist.platform.errors import NotFoundError


class AccountReads(CamelModel):
    allowed: bool | None


class AlwaysAccountReads(CamelModel):
    always: bool


async def _user(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError(title="Account not found", detail=str(user_id))
    return user


async def read_always_account_reads(
    session: AsyncSession, user_id: UUID
) -> AlwaysAccountReads:
    return AlwaysAccountReads(
        always=(await _user(session, user_id)).account_reads_always
    )


async def set_always_account_reads(
    session: AsyncSession, user_id: UUID, *, always: bool
) -> AlwaysAccountReads:
    user = await _user(session, user_id)
    user.account_reads_always = always
    await session.commit()
    return AlwaysAccountReads(always=always)


async def account_reads_allowed(
    session: AsyncSession, *, conversation_id: UUID, user_id: UUID
) -> bool:
    user = await session.get(User, user_id)
    if user is not None and user.account_reads_always:
        return True
    return await account_reads_of(session, conversation_id) is True


async def account_reads_of(session: AsyncSession, conversation_id: UUID) -> bool | None:
    row = await session.get(
        ConversationAccountRead, conversation_id, populate_existing=True
    )
    return None if row is None else row.allowed


async def keep_account_reads(
    session: AsyncSession, *, conversation_id: UUID, allowed: bool
) -> None:
    await session.execute(
        insert(ConversationAccountRead)
        .values(conversation_id=conversation_id, allowed=allowed)
        .on_conflict_do_update(
            index_elements=[ConversationAccountRead.conversation_id],
            set_={"allowed": allowed, "updated_at": func.now()},
        )
    )


async def set_account_reads(
    session: AsyncSession, *, conversation_id: UUID, user_id: UUID, allowed: bool
) -> AccountReads:
    await assert_owner(session, conversation_id, user_id)
    await keep_account_reads(session, conversation_id=conversation_id, allowed=allowed)
    await session.commit()
    return AccountReads(allowed=allowed)


__all__ = [
    "AccountReads",
    "AlwaysAccountReads",
    "account_reads_allowed",
    "account_reads_of",
    "keep_account_reads",
    "read_always_account_reads",
    "set_account_reads",
    "set_always_account_reads",
]
