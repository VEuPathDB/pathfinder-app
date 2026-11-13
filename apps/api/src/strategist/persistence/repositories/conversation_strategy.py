"""Reading a thread beside the strategy projection that belongs to it."""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.persistence.models import Conversation
from sqlalchemy import Row, Select, select

from strategist.persistence.models import (
    ABSENT_STRATEGY,
    ConversationStrategy,
    ConversationStrategyView,
)

type ConversationWithStrategy = tuple[Conversation, ConversationStrategyView]
type StrategyRow = Row[tuple[Conversation, ConversationStrategy | None]]


def strategy_view_of(row: ConversationStrategy | None) -> ConversationStrategyView:
    """Read a strategy projection; a thread with no row reads as never built."""
    if row is None:
        return ABSENT_STRATEGY
    return ConversationStrategyView.model_validate(row)


def paired(rows: Sequence[StrategyRow]) -> list[ConversationWithStrategy]:
    return [
        (conversation, strategy_view_of(strategy)) for conversation, strategy in rows
    ]


def with_strategy() -> Select[tuple[Conversation, ConversationStrategy | None]]:
    """Select each thread beside its strategy projection, in one query.

    The outer join makes the strategy column nullable, which the select type
    of the two entities does not express.
    """
    joined: Select[tuple[Conversation, ConversationStrategy | None]] = select(
        Conversation,
        ConversationStrategy,
    )
    return joined.outerjoin(
        ConversationStrategy,
        ConversationStrategy.conversation_id == Conversation.id,
    )
