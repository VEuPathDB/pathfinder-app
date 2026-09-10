"""Scratchpad reads and writes for a request that holds a session."""

from uuid import UUID

from assistant_core.conversation.authz import get_visible_conversation
from assistant_core.persistence.repositories.scratchpad import ScratchpadRepository
from assistant_core.scratchpad.models import Note
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.errors import NotFoundError


class ScratchpadService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _verify(self, conversation_id: UUID, user_id: UUID) -> None:
        await get_visible_conversation(
            ConversationRepository(self._session),
            conversation_id,
            user_id,
        )

    async def list_notes(self, conversation_id: UUID, user_id: UUID) -> list[Note]:
        await self._verify(conversation_id, user_id)
        repo = ScratchpadRepository(self._session)
        return await repo.list_notes(conversation_id=conversation_id, limit=200)

    async def set_pinned(
        self,
        conversation_id: UUID,
        note_id: str,
        *,
        pinned: bool,
        user_id: UUID,
    ) -> Note:
        await self._verify(conversation_id, user_id)
        try:
            updated = await ScratchpadRepository(self._session).set_pinned(
                conversation_id=conversation_id,
                note_id=note_id,
                pinned=pinned,
            )
        except LookupError as exc:
            raise NotFoundError(title="note not found") from exc
        await self._session.commit()
        return updated

    async def delete_note(
        self,
        conversation_id: UUID,
        note_id: str,
        user_id: UUID,
    ) -> None:
        await self._verify(conversation_id, user_id)
        ok = await ScratchpadRepository(self._session).delete(
            conversation_id=conversation_id,
            note_id=note_id,
        )
        if not ok:
            raise NotFoundError(title="note not found")
        await self._session.commit()
