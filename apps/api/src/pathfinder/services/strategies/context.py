"""Narrow context for strategy-mutation services.

The strategy build/commit/persist services need only a strategy session,
a site id, and (for persistence) a conversation id + DB session factory,
not the full AI ``AgentDeps`` container. Depending on this narrow context
keeps the service layer free of any AI-layer import.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from assistant_core.platform.db import DBSessionFactory
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.strategy.operational_spec import SpecStructure
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.domain.strategy.spec_edit_guard import StatedCriterion


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
    stated_structure: SpecStructure | None = None
    """The tree the spec declares, or nothing when the turn framed none.

    A write that joins those criteria at another operator is refused.
    """
    criterion_texts: Mapping[str, str] = field(default_factory=dict)
    """The researcher's words for each step the spec states, keyed by step id."""
    stated_values: Mapping[str, StatedCriterion] = field(default_factory=dict)
    """The values the spec's criteria state, keyed by criterion id.

    A write that sends another value for one of them is refused, wherever the
    value rides: a parameter patch or a leaf inside a written tree.
    """
    user_prompt: str = ""
    """The researcher's request this turn. A strategy with no name yet takes it."""
    locked_session: AsyncSession | None = None
    """A session that already owns the thread's strategy lock.

    The caller that read the AST holds the lock across the whole edit, so the
    persist step joins that transaction instead of opening one of its own.
    """
