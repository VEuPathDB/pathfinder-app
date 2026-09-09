"""Test-only reduction of a whole chunk log into an ordered message list.

An envelope chunk is a message boundary and its message passes through
unreduced, which ``split_into_turns`` plus ``reduce_chunks`` does not do.
"""

from __future__ import annotations

from typing import Any

from assistant_core.conversation import Chunk
from assistant_core.conversation.ui_message_reducer import (
    ASSISTANT_MESSAGE_CHUNK_TYPE,
    SYSTEM_MESSAGE_CHUNK_TYPE,
    USER_MESSAGE_CHUNK_TYPE,
    reduce_chunks,
)

_ENVELOPE_CHUNK_TYPES = {
    USER_MESSAGE_CHUNK_TYPE,
    SYSTEM_MESSAGE_CHUNK_TYPE,
    ASSISTANT_MESSAGE_CHUNK_TYPE,
}


def reduce_chunks_to_messages(
    chunks: list[Chunk],
    fallback_id_prefix: str = "msg",
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    pending: list[Chunk] = []
    assistant_index = 0
    for chunk in chunks:
        if chunk.get("type") in _ENVELOPE_CHUNK_TYPES:
            if pending:
                messages.append(
                    reduce_chunks(
                        pending,
                        f"{fallback_id_prefix}-{assistant_index}",
                    )
                )
                assistant_index += 1
                pending = []
            raw = chunk.get("message")
            if isinstance(raw, dict):
                messages.append(raw)
            continue
        pending.append(chunk)
        if chunk.get("type") == "done":
            messages.append(
                reduce_chunks(
                    pending,
                    f"{fallback_id_prefix}-{assistant_index}",
                )
            )
            assistant_index += 1
            pending = []
    if pending:
        messages.append(
            reduce_chunks(
                pending,
                f"{fallback_id_prefix}-{assistant_index}",
            )
        )
    return messages
