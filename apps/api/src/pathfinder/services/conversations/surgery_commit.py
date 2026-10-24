from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.eda.thread_surgery import (
    ReleasableDocument,
    delete_released_document,
)
from pathfinder.services.strategies.abandoned_mint import (
    ReleasableMint,
    delete_released_mint,
)

__all__ = ["SurgeryMade", "commit_or_release", "release_made"]


@dataclass(frozen=True)
class SurgeryMade:
    mint: ReleasableMint | None = None
    document: ReleasableDocument | None = None


async def release_made(made: SurgeryMade) -> None:
    await delete_released_mint(made.mint)
    await delete_released_document(made.document)


async def commit_or_release(session: AsyncSession, made: SurgeryMade) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        await release_made(made)
        raise
