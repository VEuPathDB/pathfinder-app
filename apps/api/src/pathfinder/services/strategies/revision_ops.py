"""Reading and restoring the strategy a thread held at a chosen point."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from assistant_core.persistence.models import Conversation, Message
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.strategy.revision import (
    parse_strategy_ast,
    without_wdk_readings,
)
from pathfinder.persistence.models import StrategyRevisionView
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.services.strategies.abandoned_mint import (
    ReleasableMint,
    abandoned_mint_to_release,
)
from pathfinder.services.strategies.materialize import (
    MaterializedStrategy,
    materialize_strategy_snapshot,
)

__all__ = [
    "DiscardedWrites",
    "discard_turn_strategy_writes",
    "materialize_revision",
    "restore_revision",
    "revision_at_message",
]


@dataclass(frozen=True)
class DiscardedWrites:
    """What a discard undid, and the mint its caller releases after committing."""

    undone: bool
    release: ReleasableMint | None = None


async def revision_at_message(
    session: AsyncSession,
    *,
    message: Message,
) -> StrategyRevisionView | None:
    """The strategy snapshot in force at ``message``.

    A snapshot the message names wins; otherwise the newest snapshot written
    no later than the message.
    """
    repo = StrategyRevisionRepository(session)
    named = await repo.named_by(message.conversation_id, message_id=message.id)
    if named is not None:
        return named
    return await repo.at_or_before(message.conversation_id, message.created_at)


async def _write_strategy_state(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    state: MaterializedStrategy,
) -> None:
    """Write one adopted strategy state, or clear the thread's when it holds none."""
    ast = parse_strategy_ast(state.strategy_ast)
    repo = ConversationRepository(session)
    if ast is None:
        await repo.clear_strategy(conversation_id)
        return
    await repo.update_conversation(
        conversation_id,
        ConversationUpdate(
            strategy_ast=ast,
            record_type=state.record_type,
            step_count=state.step_count,
            wdk_strategy_id=state.wdk_strategy_id,
            wdk_strategy_id_set=True,
            wdk_strategy_created_here=state.created_wdk_strategy,
            wdk_strategy_created_here_set=True,
            is_saved=state.is_saved,
            is_saved_set=True,
            estimated_size=None,
            estimated_size_set=True,
        ),
    )


async def restore_revision(
    session: AsyncSession,
    *,
    revision: StrategyRevisionView,
) -> ReleasableMint | None:
    """Write a thread's strategy back to one of its snapshots, as recorded.

    The snapshot's WDK identity stands: the caller is undoing writes made
    against the same steps, so nothing has moved under it. Reports the
    strategy the thread held when the restore leaves nothing naming it, for
    the caller to delete once it has committed.
    """
    repo = ConversationRepository(session)
    abandoned = await repo.get_strategy(revision.conversation_id)
    await _write_strategy_state(
        session,
        conversation_id=revision.conversation_id,
        state=MaterializedStrategy(
            strategy_ast=without_wdk_readings(revision.strategy_ast),
            record_type=revision.record_type,
            step_count=revision.step_count,
            wdk_strategy_id=revision.wdk_strategy_id,
            created_wdk_strategy=revision.wdk_strategy_created_here,
            is_saved=revision.is_saved,
        ),
    )
    return await abandoned_mint_to_release(
        session,
        conversation_id=revision.conversation_id,
        abandoned=abandoned,
        restored_wdk_strategy_id=revision.wdk_strategy_id,
    )


async def materialize_revision(
    session: AsyncSession,
    *,
    conversation: Conversation,
    revision: StrategyRevisionView,
) -> None:
    """Adopt a snapshot as a strategy of the thread's own on WDK.

    The steps the snapshot names may have moved since it was written, and a
    copied snapshot names none at all, so the tree is pushed again. A refusal
    leaves the thread holding the plan.
    """
    await _write_strategy_state(
        session,
        conversation_id=revision.conversation_id,
        state=await materialize_strategy_snapshot(
            site_id=conversation.site_id,
            conversation_id=conversation.id,
            name=conversation.name,
            strategy_ast=revision.strategy_ast,
            record_type=revision.record_type,
            step_count=revision.step_count,
        ),
    )


async def discard_turn_strategy_writes(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    pre_turn_revision_id: int | None,
) -> DiscardedWrites:
    """Undo the strategy a stopped turn had already written.

    ``pre_turn_revision_id`` is the newest snapshot the thread held when the
    turn opened; ``None`` means it held no strategy at all. Reports whether
    anything was undone, and the mint the caller releases after committing.
    """
    repo = StrategyRevisionRepository(session)
    conversations = ConversationRepository(session)
    removed = await repo.delete_newer_than(
        conversation_id,
        revision_row_id=pre_turn_revision_id,
    )
    if removed == 0:
        return DiscardedWrites(undone=False)
    if pre_turn_revision_id is None:
        abandoned = await conversations.get_strategy(conversation_id)
        await conversations.clear_strategy(conversation_id)
        return DiscardedWrites(
            undone=True,
            release=await abandoned_mint_to_release(
                session,
                conversation_id=conversation_id,
                abandoned=abandoned,
                restored_wdk_strategy_id=None,
            ),
        )
    snapshot = await repo.latest(conversation_id)
    if snapshot is None:
        return DiscardedWrites(undone=False)
    return DiscardedWrites(
        undone=True,
        release=await restore_revision(session, revision=snapshot),
    )
