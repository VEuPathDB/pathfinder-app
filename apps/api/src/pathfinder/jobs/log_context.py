"""The log context of one chat turn: every line the worker writes while the
turn runs names the conversation and the turn."""

from __future__ import annotations

from contextlib import AbstractContextManager
from uuid import UUID

import structlog


def turn_log_context(
    *, conversation_id: UUID, turn_id: UUID
) -> AbstractContextManager[None]:
    """Bind the conversation and the turn on every log line of the block."""
    return structlog.contextvars.bound_contextvars(
        conversation_id=str(conversation_id), turn_id=str(turn_id)
    )
