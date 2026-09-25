from __future__ import annotations

from typing import Annotated
from uuid import UUID

from assistant_core.registry import resolve_turn_assistant
from assistant_core.spec import AssistantSpec
from fastapi import APIRouter, Depends, Response

from pathfinder.ai.conversation.attachments import ReadAttachment, read_attachments
from pathfinder.ai.conversation.dispatcher import dispatch
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.ai.models.catalog import get_model_entry
from pathfinder.assistants.registry import (
    assistant_role_models,
    get_assistant_registry,
    prompt_reader_model,
)
from pathfinder.services.wdk_identity import require_session_matches_wdk_identity
from pathfinder.transport.http.deps import (
    CurrentPrincipal,
    CurrentUser,
    DBSession,
    refuse_degraded_site,
    require_turn_paid,
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


ChatAssistant = Annotated[AssistantSpec, Depends(resolve_chat_assistant)]


def refuse_unreadable_attachments(
    body: ChatRequestBody, assistant_id: str
) -> list[ReadAttachment]:
    """The message's attachments, once the model that reads the message can read
    each one and they fit the caps. The refusal comes before the event log
    stores them or a model is called."""
    files = body.last_user_files
    if not files:
        return []
    model_id = prompt_reader_model(assistant_id, body.runtime_phase_models)
    model = get_model_entry(model_id)
    if model is None:
        msg = f"the reader model {model_id!r} is not in the catalog"
        raise LookupError(msg)
    return read_attachments(files, model)


async def require_readable_attachments(
    body: ChatRequestBody, spec: ChatAssistant
) -> None:
    refuse_unreadable_attachments(body, spec.assistant_id)


async def paid_turn_user(
    body: ChatRequestBody,
    session: DBSession,
    user_id: CurrentUser,
    spec: ChatAssistant,
) -> UUID:
    """The caller, once a key is known to pay for every model the turn runs."""
    roles = assistant_role_models(spec.assistant_id, body.runtime_phase_models)
    await require_turn_paid(session, user_id, roles.values())
    return user_id


@router.post(
    "/api/v1/chat",
    dependencies=[
        Depends(require_available_chat_site),
        Depends(require_readable_attachments),
    ],
)
async def chat(
    body: ChatRequestBody,
    session: DBSession,
    user_id: Annotated[UUID, Depends(paid_turn_user)],
    spec: ChatAssistant,
) -> Response:
    return await dispatch(body=body, session=session, user_id=user_id, spec=spec)
