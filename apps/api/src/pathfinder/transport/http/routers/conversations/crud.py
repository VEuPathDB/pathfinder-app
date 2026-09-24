"""Strategy CRUD endpoints. Thin transport over ``ConversationService``."""

from functools import partial
from typing import Annotated
from uuid import UUID

from assistant_core.platform.types import JSONObject
from assistant_core.registry import resolve_turn_assistant
from fastapi import APIRouter, Depends, Query, Response

from pathfinder.ai.conversation.title_generator import generate_conversation_title
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.services.conversations.begin import start_title_generation
from pathfinder.services.conversations.responses import ConversationResponse
from pathfinder.services.conversations.service import ConversationService
from pathfinder.services.conversations.update_input import ConversationUpdateInput
from pathfinder.transport.http.deps import (
    CurrentUser,
    DBSession,
    SiteIdQuery,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.schemas import (
    BeginConversationRequest,
    BeginConversationResponse,
    CreateConversationRequest,
    UpdateConversationRequest,
)
from pathfinder.transport.http.schemas.conversations import ForkConversationRequest

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationResponse])
async def list_strategies(
    session: DBSession,
    user_id: CurrentUser,
    site_id: SiteIdQuery = None,
) -> list[ConversationResponse]:
    """List the user's chats (active, non-dismissed)."""
    return await ConversationService(session).list_active(user_id, site_id)


@router.get("/dismissed", response_model=list[ConversationResponse])
async def list_dismissed_strategies(
    session: DBSession,
    user_id: CurrentUser,
    site_id: SiteIdQuery = None,
) -> list[ConversationResponse]:
    """List the user's dismissed (soft-deleted) chats."""
    return await ConversationService(session).list_dismissed(user_id, site_id)


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_strategy(
    request: CreateConversationRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> ConversationResponse:
    """Create a new strategy (chat with plan metadata)."""
    return await ConversationService(session).create(
        user_id=user_id,
        site_id=request.site_id,
        name=request.name,
        strategy_ast=request.strategy_ast,
    )


@router.get("/{strategyId:uuid}", response_model=ConversationResponse)
async def get_strategy(
    strategyId: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> ConversationResponse:
    """Get a strategy (chat) by ID."""
    return await ConversationService(session).get_detail(strategyId, user_id)


@router.patch("/{strategyId:uuid}", response_model=ConversationResponse)
async def update_strategy(
    strategyId: UUID,
    request: UpdateConversationRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> ConversationResponse:
    """Update strategy metadata (name, plan, wdk link, saved flag)."""
    fields_set = request.model_fields_set
    patch = ConversationUpdateInput(
        name=request.name,
        strategy_ast=request.strategy_ast,
        wdk_strategy_id=request.wdk_strategy_id,
        wdk_strategy_id_set="wdk_strategy_id" in fields_set,
        is_saved=request.is_saved,
        is_saved_set="is_saved" in fields_set,
    )
    return await ConversationService(session).update(strategyId, user_id, patch)


# A fork copies the source WDK strategy into the user's own account.
@router.post(
    "/{strategyId:uuid}/fork",
    response_model=ConversationResponse,
    dependencies=[Depends(require_registered_wdk_identity)],
)
async def fork_strategy(
    strategyId: UUID,
    request: ForkConversationRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> ConversationResponse:
    """Branch a conversation at a chosen assistant message into a new chat."""
    return await ConversationService(session).fork(
        strategyId,
        user_id,
        request.from_message_id,
    )


@router.delete("/{strategyId:uuid}", status_code=204, response_class=Response)
async def delete_strategy(
    strategyId: UUID,
    session: DBSession,
    user_id: CurrentUser,
    *,
    delete_from_wdk: Annotated[bool, Query(alias="deleteFromWdk")] = False,
    cascade: Annotated[bool, Query()] = False,
) -> Response:
    """Delete a strategy (soft-delete WDK-linked unless deleteFromWdk=true)."""
    await ConversationService(session).delete(
        strategyId,
        user_id,
        delete_from_wdk=delete_from_wdk,
        cascade=cascade,
    )
    return Response(status_code=204)


@router.get("/{strategyId:uuid}/ast")
async def get_strategy_ast(
    strategyId: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> JSONObject:
    """Return the raw plan AST from a strategy chat."""
    return await ConversationService(session).get_ast(strategyId, user_id)


@router.post("/{strategyId:uuid}/restore", response_model=ConversationResponse)
async def restore_strategy(
    strategyId: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> ConversationResponse:
    """Restore a dismissed (soft-deleted) strategy."""
    return await ConversationService(session).restore(strategyId, user_id)


@router.post("/{conversation_id}/begin", response_model=BeginConversationResponse)
async def begin_strategy(
    conversation_id: Annotated[UUID, "Conversation id (client-generated UUID)."],
    body: BeginConversationRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> BeginConversationResponse:
    """Idempotent first-action setup for a conversation."""
    spec = await resolve_turn_assistant(
        registry=get_assistant_registry(),
        conversation_id=conversation_id,
        requested_id=body.assistant_id,
    )
    begun = await ConversationService(session).begin(
        conversation_id=conversation_id,
        user_id=user_id,
        site_id=body.site_id,
        assistant_id=spec.assistant_id,
    )
    if begun.is_new and body.seed_text:
        start_title_generation(
            conversation_id=conversation_id,
            seed_text=body.seed_text,
            title_generator=partial(
                generate_conversation_title,
                mock_model=spec.build_mock_model,
            ),
        )
    return BeginConversationResponse(
        conversation_id=begun.conversation_id,
        is_new=begun.is_new,
        name=begun.name,
    )
