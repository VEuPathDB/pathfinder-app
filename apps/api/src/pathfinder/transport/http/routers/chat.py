from __future__ import annotations

from typing import Annotated

from assistant_core.registry import resolve_turn_assistant
from assistant_core.spec import AssistantSpec
from fastapi import APIRouter, Depends, Response

from pathfinder.ai.conversation.dispatcher import dispatch
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.services.wdk_identity import require_session_matches_wdk_identity
from pathfinder.transport.http.deps import (
    CurrentPrincipal,
    DBSession,
    QuotaCheckedUser,
    refuse_degraded_site,
)

router = APIRouter(tags=["chat"])


async def resolve_chat_assistant(
    body: ChatRequestBody,
    principal: CurrentPrincipal,
) -> AssistantSpec:
    """Name the turn's assistant and enforce the identity it requires.

    The gate runs before dispatch, so the deferred chat_turn job carries the
    user's own registered token, and that token names the session's own user.
    An assistant that declares no requirement is served without one.
    """
    spec = await resolve_turn_assistant(
        registry=get_assistant_registry(),
        conversation_id=body.conversation_id,
        requested_id=body.assistant_id,
    )
    if spec.identity_gate is not None:
        await spec.identity_gate()
        await require_session_matches_wdk_identity(principal, body.site_id)
    return spec


async def require_available_chat_site(body: ChatRequestBody) -> None:
    """Refuse a turn on a site whose catalog this process has not loaded.

    The turn's site rides the body, so the parameter-shaped dependency cannot
    read it.
    """
    refuse_degraded_site(body.site_id)


@router.post("/api/v1/chat", dependencies=[Depends(require_available_chat_site)])
async def chat(
    body: ChatRequestBody,
    session: DBSession,
    user_id: QuotaCheckedUser,
    spec: Annotated[AssistantSpec, Depends(resolve_chat_assistant)],
) -> Response:
    return await dispatch(body=body, session=session, user_id=user_id, spec=spec)
