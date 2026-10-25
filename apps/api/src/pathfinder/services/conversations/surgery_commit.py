from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.repositories.committed_names import (
    a_binding_names,
    a_projection_names,
)
from pathfinder.services.eda.thread_surgery import (
    ReleasableDocument,
    delete_released_document,
)
from pathfinder.services.strategies.abandoned_mint import (
    ReleasableMint,
    delete_released_mint,
)

__all__ = ["CONFIRM_SECONDS", "SurgeryMade", "commit_or_release"]

logger = get_logger(__name__)

CONFIRM_SECONDS = 5.0


@dataclass(frozen=True)
class SurgeryMade:
    mint: ReleasableMint | None = None
    document: ReleasableDocument | None = None


@dataclass(frozen=True)
class _Unnamed:
    mint: ReleasableMint | None
    document: ReleasableDocument | None


async def _unnamed_by_committed_rows(made: SurgeryMade) -> _Unnamed:
    async with asyncio.timeout(CONFIRM_SECONDS), async_session_factory() as session:
        mint_named = made.mint is not None and await a_projection_names(
            session,
            made.mint.wdk_strategy_id,
        )
        document_named = made.document is not None and await a_binding_names(
            session,
            made.document.analysis_id,
        )
    return _Unnamed(
        mint=None if mint_named else made.mint,
        document=None if document_named else made.document,
    )


async def _best_effort(release: Awaitable[None]) -> None:
    try:
        await release
    except Exception:
        logger.exception("a release after a failed surgery raised")


async def _release_uncommitted(made: SurgeryMade) -> None:
    try:
        unnamed = await _unnamed_by_committed_rows(made)
    except Exception:
        logger.exception("kept what a surgery made: its commit could not be confirmed")
        return
    await _best_effort(delete_released_mint(unnamed.mint))
    await _best_effort(delete_released_document(unnamed.document))


async def commit_or_release(session: AsyncSession, made: SurgeryMade) -> None:
    try:
        await session.commit()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            logger.exception("the rollback after a failed surgery commit raised")
        await _release_uncommitted(made)
        raise
