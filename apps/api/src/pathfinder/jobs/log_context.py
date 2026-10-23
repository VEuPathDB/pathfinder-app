"""The log ids a worker binds that the runtime does not: a chat turn's own ids
and the assistant a completion turn runs."""

from __future__ import annotations

from contextlib import AbstractContextManager

from assistant_core.tasks.completion_turn import CompletionTurn

from pathfinder.jobs.payloads import ChatTurnPayload
from pathfinder.platform.log_ids import LogIds, log_ids_scope


def turn_log_context(payload: ChatTurnPayload) -> AbstractContextManager[None]:
    return log_ids_scope(
        LogIds(
            conversation_id=payload.body.conversation_id,
            turn_id=payload.turn_id,
            user_id=payload.user_id,
            site_id=payload.body.site_id,
            assistant_id=payload.assistant_id,
        )
    )


def completion_log_context(turn: CompletionTurn) -> AbstractContextManager[None]:
    return log_ids_scope(LogIds(assistant_id=turn.spec.assistant_id))
