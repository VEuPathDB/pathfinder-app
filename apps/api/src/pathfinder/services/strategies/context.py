"""Narrow context for strategy-mutation services.

The strategy build/commit/persist services need only a strategy session,
a site id, and (for persistence) a conversation id + DB session factory —
not the full AI ``AgentDeps`` container. Depending on this narrow context
keeps the service layer free of any AI-layer import.
"""

from dataclasses import dataclass
from uuid import UUID

from assistant_core.platform.db import DBSessionFactory
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.session import StrategySession


@dataclass(frozen=True)
class StrategyMutationContext:
    site_id: str
    strategy_session: StrategySession
    conversation_id: UUID | None = None
    db_session_factory: DBSessionFactory | None = None
    stated_criteria: frozenset[str] = frozenset()
    """The criterion ids the spec states, empty when the turn frames none.

    A batch that replaces a subtree holds them, so a write cannot drop the
    evidence the spec claims.
    """
    locked_session: AsyncSession | None = None
    """A session that already owns the thread's strategy lock.

    The caller that read the AST holds the lock across the whole edit, so the
    persist step joins that transaction instead of opening one of its own.
    """
