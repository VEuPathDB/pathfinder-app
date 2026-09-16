"""Scratchpad HTTP routes: list, pin, delete."""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.scratchpad.models import Note
from fastapi import APIRouter, status
from pydantic import ConfigDict, Field

from pathfinder.services.conversations.scratchpad_service import ScratchpadService
from pathfinder.transport.http.deps import CurrentUser, DBSession

router = APIRouter(prefix="/api/v1/conversations", tags=["scratchpad"])


class ScratchpadPatchRequest(CamelModel):
    """User-driven PATCH - only the ``pinned`` flag is settable from the UI.

    ``extra="forbid"`` rejects ``title``/``body``/``summary`` edits with 422
    so scratchpad content stays agent-authored.
    """

    model_config = ConfigDict(extra="forbid")

    pinned: bool = Field(description="New pin state.")


@router.get(
    "/{conversation_id}/scratchpad/notes",
    response_model=list[Note],
    summary="List scratchpad notes for the conversation.",
)
async def list_scratchpad_notes(
    conversation_id: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> list[Note]:
    return await ScratchpadService(session).list_notes(conversation_id, user_id)


@router.patch(
    "/{conversation_id}/scratchpad/notes/{note_id}",
    response_model=Note,
    summary="Pin or unpin a scratchpad note.",
)
async def patch_scratchpad_note(
    conversation_id: UUID,
    note_id: str,
    request: ScratchpadPatchRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> Note:
    return await ScratchpadService(session).set_pinned(
        conversation_id,
        note_id,
        pinned=request.pinned,
        user_id=user_id,
    )


@router.delete(
    "/{conversation_id}/scratchpad/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a scratchpad note.",
)
async def delete_scratchpad_note(
    conversation_id: UUID,
    note_id: str,
    session: DBSession,
    user_id: CurrentUser,
) -> None:
    await ScratchpadService(session).delete_note(conversation_id, note_id, user_id)
