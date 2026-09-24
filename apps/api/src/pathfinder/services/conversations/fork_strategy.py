from __future__ import annotations

from uuid import UUID

from assistant_core.persistence.models import Conversation, Message
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import (
    ConversationStrategy,
    StrategyRevisionView,
)
from pathfinder.persistence.repositories.conversation_strategy import (
    strategy_view_of,
)
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.errors import ForkRefusedError
from pathfinder.services.strategies.materialize import (
    materialize_strategy_snapshot,
)
from pathfinder.services.strategies.revision_ops import revision_at_message


async def anchor_snapshot(
    session: AsyncSession,
    *,
    source_conversation_id: UUID,
    anchor: Message,
    strategy_row: ConversationStrategy | None,
) -> StrategyRevisionView | None:
    """The strategy the anchor message was answered against.

    ``None`` means the fork starts with no strategy. A thread that holds a
    strategy but no history at all cannot be reproduced, so it is refused
    rather than copied at its latest state.
    """
    if strategy_row is None:
        return None
    snapshot = await revision_at_message(session, message=anchor)
    if snapshot is not None:
        return snapshot
    if await StrategyRevisionRepository(session).has_any(source_conversation_id):
        # Every snapshot postdates the anchor: nothing was built yet.
        return None
    msg = (
        "This chat predates the strategy history, so a branch cannot "
        "reproduce the strategy it had at that message."
    )
    raise ForkRefusedError(msg)


async def write_forked_strategy(
    session: AsyncSession,
    *,
    branch: Conversation,
    snapshot: StrategyRevisionView,
    strategy_row: ConversationStrategy,
    new_conversation_id: UUID,
    anchor_message_id: UUID,
) -> None:
    """Push the snapshot as the fork's own WDK strategy and store it.

    The stored strategy and the WDK strategy carry the branch thread's name.
    """
    source_strategy = strategy_view_of(strategy_row)
    # The snapshot's own WDK id says nothing about whether its tree was ever
    # pushed: a fork's copied history carries none. Every snapshot with a tree
    # is pushed, and a WDK refusal leaves the branch holding the plan.
    materialized = await materialize_strategy_snapshot(
        site_id=branch.site_id,
        conversation_id=new_conversation_id,
        name=branch.name,
        strategy_ast=snapshot.strategy_ast,
        record_type=snapshot.record_type,
        step_count=snapshot.step_count,
    )
    session.add(
        ConversationStrategy(
            conversation_id=new_conversation_id,
            record_type=materialized.record_type,
            strategy_ast=materialized.strategy_ast,
            step_count=materialized.step_count,
            # A gene set taken from a strategy is re-synced against whatever
            # strategy its thread holds, so a branch that inherited the link
            # would rewrite its source's set. The branch imports its own.
            gene_set_id=None,
            gene_set_auto_imported=False,
            wdk_strategy_id=materialized.wdk_strategy_id,
            wdk_strategy_created_here=materialized.created_wdk_strategy,
            # The fork still embeds the imported subtrees, so it keeps
            # the references.
            imported_saved_strategy_ids=list(
                source_strategy.imported_saved_strategy_ids,
            ),
        ),
    )
    await session.flush()
    await StrategyRevisionRepository(session).record(
        new_conversation_id,
        strategy_view_of(
            await session.get(ConversationStrategy, new_conversation_id),
        ),
        message_id=anchor_message_id,
    )
