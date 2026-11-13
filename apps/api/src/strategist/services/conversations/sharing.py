from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from uuid import UUID

from assistant_core.conversation.authz import assert_owner
from assistant_core.conversation.event_stream import (
    EventsSnapshot,
    fetch_snapshot_chunks,
    latest_snapshot_boundary,
)
from assistant_core.persistence.models import Conversation
from assistant_core.platform.pydantic_base import CamelModel
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from strategist.domain.owner_reads import without_owner_reads
from strategist.persistence.models import ConversationShare
from strategist.persistence.repositories.checkpoint_rows import ChannelRewrite
from strategist.platform.errors import (
    AppError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
)
from strategist.services.conversations.fork import (
    CopyTerms,
    ForkError,
    copy_conversation,
)
from strategist.services.conversations.new_thread import settle_new_thread
from strategist.services.conversations.responses import ConversationResponse
from strategist.services.conversations.turn_liveness import turn_is_in_flight


class ShareSettings(CamelModel):
    public: bool
    allow_copy: bool
    include_account_reads: bool = False


class ConversationShareView(CamelModel):
    token: str
    public: bool
    allow_copy: bool
    include_account_reads: bool


class ShareState(CamelModel):
    share: ConversationShareView | None


class ShareChange(CamelModel):
    share: ConversationShareView
    password: str | None


class SharedConversation(CamelModel):
    name: str
    site_id: str
    assistant_id: str
    allow_copy: bool
    cursor: int
    turn_in_flight: bool


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _view(row: ConversationShare) -> ConversationShareView:
    return ConversationShareView(
        token=row.token,
        public=row.public,
        allow_copy=row.allow_copy,
        include_account_reads=row.include_account_reads,
    )


async def _owned_share(
    session: AsyncSession, conversation_id: UUID, user_id: UUID
) -> ConversationShare | None:
    await assert_owner(session, conversation_id, user_id)
    return await session.get(ConversationShare, conversation_id, populate_existing=True)


async def share_of(
    session: AsyncSession, *, conversation_id: UUID, user_id: UUID
) -> ShareState:
    row = await _owned_share(session, conversation_id, user_id)
    return ShareState(share=None if row is None else _view(row))


async def set_share(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
    settings: ShareSettings,
) -> ShareChange:
    await assert_owner(session, conversation_id, user_id)
    await session.execute(
        insert(ConversationShare)
        .values(
            conversation_id=conversation_id,
            token=secrets.token_urlsafe(32),
            public=True,
            password_hash=None,
            allow_copy=False,
        )
        .on_conflict_do_nothing(index_elements=[ConversationShare.conversation_id])
    )
    row = await session.scalar(
        select(ConversationShare)
        .where(ConversationShare.conversation_id == conversation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFoundError(
            code=ErrorCode.SHARE_NOT_FOUND, title="This conversation is not shared"
        )
    password = None
    if not settings.public and (row.public or row.password_hash is None):
        password = secrets.token_urlsafe(12)
    row.public = settings.public
    row.allow_copy = settings.allow_copy
    row.include_account_reads = settings.include_account_reads
    if settings.public:
        row.password_hash = None
    elif password is not None:
        row.password_hash = _hash(password)
    row.updated_at = func.now()
    await session.commit()
    return ShareChange(share=_view(row), password=password)


async def renew_password(
    session: AsyncSession, *, conversation_id: UUID, user_id: UUID
) -> ShareChange:
    row = await _owned_share(session, conversation_id, user_id)
    if row is None:
        raise NotFoundError(
            code=ErrorCode.SHARE_NOT_FOUND, title="This conversation is not shared"
        )
    if row.public:
        raise AppError(
            code=ErrorCode.SHARE_IS_PUBLIC,
            title="Anyone with the link can open this conversation",
            status=409,
            detail="A link open to anyone has no password.",
        )
    password = secrets.token_urlsafe(12)
    row.password_hash = _hash(password)
    row.updated_at = func.now()
    await session.commit()
    return ShareChange(share=_view(row), password=password)


async def stop_sharing(
    session: AsyncSession, *, conversation_id: UUID, user_id: UUID
) -> None:
    await assert_owner(session, conversation_id, user_id)
    await session.execute(
        delete(ConversationShare).where(
            ConversationShare.conversation_id == conversation_id
        )
    )
    await session.commit()


async def _opened(
    session: AsyncSession, token: str, password: str
) -> tuple[ConversationShare, Conversation]:
    found = (
        await session.execute(
            select(ConversationShare, Conversation)
            .join(Conversation, Conversation.id == ConversationShare.conversation_id)
            .where(ConversationShare.token == token)
        )
    ).one_or_none()
    if found is None:
        raise NotFoundError(
            code=ErrorCode.SHARE_NOT_FOUND,
            title="This link is no longer shared",
        )
    share, conversation = found.tuple()
    if share.password_hash is not None and not (
        password is not None
        and hmac.compare_digest(_hash(password), share.password_hash)
    ):
        raise ForbiddenError(
            code=ErrorCode.SHARE_LOCKED,
            title="This link needs its password",
        )
    return share, conversation


async def read_shared(
    session: AsyncSession, *, token: str, password: str
) -> SharedConversation:
    share, conversation = await _opened(session, token, password)
    return SharedConversation(
        name=conversation.name,
        site_id=conversation.site_id,
        assistant_id=conversation.assistant_id,
        allow_copy=share.allow_copy,
        cursor=await latest_snapshot_boundary(conversation.id),
        turn_in_flight=await turn_is_in_flight(
            session, conversation_id=conversation.id, user_id=conversation.user_id
        ),
    )


async def shared_snapshot(
    session: AsyncSession, *, token: str, password: str
) -> EventsSnapshot:
    share, conversation = await _opened(session, token, password)
    snapshot = await fetch_snapshot_chunks(conversation.id)
    if share.include_account_reads:
        return snapshot
    return snapshot.model_copy(update={"chunks": without_owner_reads(snapshot.chunks)})


async def copy_shared(
    session: AsyncSession,
    *,
    token: str,
    password: str,
    user_id: UUID,
    rewrite_for: Callable[[str], ChannelRewrite | None],
) -> ConversationResponse:
    share, conversation = await _opened(session, token, password)
    rewrite = rewrite_for(conversation.assistant_id)
    if not share.allow_copy or rewrite is None:
        raise ForbiddenError(
            code=ErrorCode.SHARE_COPY_NOT_ALLOWED,
            title="This link does not allow copies",
        )
    try:
        copy = await copy_conversation(
            session,
            source=conversation,
            user_id=user_id,
            terms=CopyTerms(
                rewrite=rewrite, keep_owner_reads=share.include_account_reads
            ),
        )
    except ForkError as exc:
        raise NotFoundError(code=ErrorCode.SHARE_NOT_FOUND, title=str(exc)) from exc
    return await settle_new_thread(session, copy)


__all__ = [
    "ConversationShareView",
    "ShareChange",
    "ShareSettings",
    "ShareState",
    "SharedConversation",
    "copy_shared",
    "read_shared",
    "renew_password",
    "set_share",
    "share_of",
    "shared_snapshot",
    "stop_sharing",
]
