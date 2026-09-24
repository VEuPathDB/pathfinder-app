"""The staging queue between extraction and curation.

A staged row names the user and the thread it came from, so an opt-out or a
purge deletes it. Promotion strips both and drops the extract; what stays is
the content hash, which is how the same investigation never queues twice.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from assistant_core.platform.context import calling_application
from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.evals.extract import EvalExtract
from pathfinder.persistence.models import PROMOTED, STAGED, EvalStagedCase

type SessionFactory = Callable[[], AsyncSession]


class EvalStagingRepository:
    """Reads and writes the eval staging queue."""

    def __init__(self, *, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def stage(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        extract: EvalExtract,
        rated_message_id: UUID | None = None,
    ) -> UUID | None:
        """Queue one candidate. Returns None when it is already known.

        An extraction row is known by its thread or its content. A rated row is
        known by its message or its content; when the same thread's extraction
        row waits with that content, that row takes the message instead.
        """
        content_hash = extract.content_hash()
        async with self._session_factory() as session:
            if rated_message_id is None:
                known = (EvalStagedCase.content_hash == content_hash) | (
                    EvalStagedCase.source_conversation_id == conversation_id
                )
            else:
                known = (EvalStagedCase.content_hash == content_hash) | (
                    EvalStagedCase.rated_message_id == rated_message_id
                )
            found = await session.scalar(select(EvalStagedCase).where(known).limit(1))
            if found is not None:
                if (
                    rated_message_id is None
                    or found.status != STAGED
                    or found.rated_message_id is not None
                    or found.source_conversation_id != conversation_id
                ):
                    return None
                found.rated_message_id = rated_message_id
                await session.commit()
                return found.id
            staging_id = uuid4()
            session.add(
                EvalStagedCase(
                    id=staging_id,
                    user_id=user_id,
                    source_conversation_id=conversation_id,
                    application_id=calling_application(),
                    site_id=extract.site_id,
                    assistant_id=extract.assistant_id,
                    content_hash=content_hash,
                    extract=extract.model_dump(by_alias=True, mode="json"),
                    status=STAGED,
                    rated_message_id=rated_message_id,
                ),
            )
            await session.commit()
        return staging_id

    async def get(self, staging_id: UUID) -> EvalStagedCase | None:
        async with self._session_factory() as session:
            return await session.get(EvalStagedCase, staging_id)

    async def list_staged(self, *, limit: int = 100) -> list[EvalStagedCase]:
        """The candidates awaiting curation, oldest first."""
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(EvalStagedCase)
                .where(EvalStagedCase.status == STAGED)
                .order_by(EvalStagedCase.staged_at)
                .limit(limit),
            )
            return list(rows)

    async def promote(self, *, staging_id: UUID, corpus_name: str) -> None:
        """End the association. The science is in the corpus file by now."""
        async with self._session_factory() as session:
            await session.execute(
                update(EvalStagedCase)
                .where(EvalStagedCase.id == staging_id)
                .values(
                    user_id=None,
                    source_conversation_id=None,
                    extract=None,
                    rated_message_id=None,
                    status=PROMOTED,
                    corpus_name=corpus_name,
                    promoted_at=datetime.now(UTC),
                ),
            )
            await session.commit()

    async def unstage_rated(self, message_id: UUID) -> int:
        """Delete the staged row of one rated message. A promoted row names none."""
        async with self._session_factory() as session:
            result = await session.execute(
                delete(EvalStagedCase).where(
                    EvalStagedCase.rated_message_id == message_id,
                    EvalStagedCase.status == STAGED,
                ),
            )
            await session.commit()
        return _deleted(result)


def _deleted(result: object) -> int:
    return cast("CursorResult[object]", result).rowcount or 0


async def delete_staged_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    application_id: str | None = None,
    site_id: str | None = None,
) -> int:
    """Delete one user's staged candidates in the caller's transaction.

    An application and a site narrow the delete to the rows a caller of that
    reach can read. A consent opt-out names neither, because the decision is
    the account's. A promoted row carries no user, so it is out of reach here
    by construction.
    """
    stmt = delete(EvalStagedCase).where(EvalStagedCase.user_id == user_id)
    if application_id is not None:
        stmt = stmt.where(EvalStagedCase.application_id == application_id)
    if site_id is not None:
        stmt = stmt.where(EvalStagedCase.site_id == site_id)
    return _deleted(await session.execute(stmt))


__all__ = ["EvalStagingRepository", "delete_staged_for_user"]
