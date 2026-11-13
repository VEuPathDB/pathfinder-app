from __future__ import annotations

from typing import Annotated

from assistant_core.conversation.event_stream import EventsSnapshot
from fastapi import APIRouter, Depends, Header

from strategist.assistants.copies import copy_rewrite
from strategist.services.conversations.responses import ConversationResponse
from strategist.services.conversations.sharing import (
    SharedConversation,
    copy_shared,
    read_shared,
    shared_snapshot,
)
from strategist.transport.http.deps import (
    CurrentUser,
    DBSession,
    require_registered_wdk_identity,
)

router = APIRouter(prefix="/api/v1/shared", tags=["shared"])

SharePassword = Annotated[str, Header(alias="X-Share-Password")]


@router.get(
    "/{token}",
    response_model=SharedConversation,
    summary="What a share link opens, and where its completed history ends.",
)
async def get_shared(
    token: str, session: DBSession, password: SharePassword = ""
) -> SharedConversation:
    return await read_shared(session, token=token, password=password)


@router.get(
    "/{token}/snapshot",
    response_model=EventsSnapshot,
    summary="The completed history of a shared conversation.",
)
async def get_shared_snapshot(
    token: str, session: DBSession, password: SharePassword = ""
) -> EventsSnapshot:
    return await shared_snapshot(session, token=token, password=password)


@router.post(
    "/{token}/copy",
    response_model=ConversationResponse,
    dependencies=[Depends(require_registered_wdk_identity)],
    summary="Copy a shared conversation into the caller's account.",
)
async def copy_shared_conversation(
    token: str,
    session: DBSession,
    user_id: CurrentUser,
    password: SharePassword = "",
) -> ConversationResponse:
    return await copy_shared(
        session,
        token=token,
        password=password,
        user_id=user_id,
        rewrite_for=copy_rewrite,
    )
