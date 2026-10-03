"""Every log line written while a chat turn runs carries the conversation id
and the turn id, and none written after it does."""

from __future__ import annotations

from uuid import uuid4

import structlog

from pathfinder.jobs.log_context import turn_log_context


def test_the_turn_binds_both_ids_for_the_block_alone() -> None:
    conversation_id, turn_id = uuid4(), uuid4()

    with turn_log_context(conversation_id=conversation_id, turn_id=turn_id):
        inside = structlog.contextvars.get_contextvars()
    after = structlog.contextvars.get_contextvars()

    assert (inside["conversation_id"], inside["turn_id"]) == (
        str(conversation_id),
        str(turn_id),
    )
    assert [k for k in after if k in {"conversation_id", "turn_id"}] == []
