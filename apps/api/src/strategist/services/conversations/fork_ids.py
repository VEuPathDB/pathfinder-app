from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

_TURN_WITHDRAWN = "data-turn-withdrawn"
_SCRATCHPAD_TOOL_PART_TYPES = frozenset(
    {
        "tool-note",
        "tool-update_note",
        "tool-delete_note",
        "tool-pin_note",
        "tool-unpin_note",
        "tool-read_note",
        "tool-promote_to_memory",
        "tool-list_notes",
        "tool-search_notes",
    }
)


class _ChunkMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None


class _WithdrawnPrompt(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message_id: str = Field(alias="messageId")


class _ChunkIdentity(BaseModel):
    """The message a chunk belongs to, however the chunk spells it."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message_id: str | None = Field(default=None, alias="messageId")
    message: _ChunkMessage | None = None

    @field_validator("message_id", mode="before")
    @classmethod
    def _only_an_id(cls, value: object) -> object:
        """A chunk that spells the key for something else names no message."""
        return value if isinstance(value, str) else None

    @field_validator("message", mode="before")
    @classmethod
    def _only_a_message(cls, value: object) -> object:
        return value if isinstance(value, dict) else None


class IdMint:
    """One id space for a fork: an unseen source id gets a fresh one."""

    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}

    def of(self, source_id: str) -> str:
        minted = self.mapping.get(source_id)
        if minted is None:
            minted = str(uuid4())
            self.mapping[source_id] = minted
        return minted


def rewrite_message_ids_in_chunk(
    chunk: dict[str, Any],
    messages: IdMint,
) -> dict[str, Any]:
    """Move a chunk into the fork's id space."""
    identity = _ChunkIdentity.model_validate(chunk)
    rewritten = chunk
    if identity.message_id is not None:
        rewritten = {**rewritten, "messageId": messages.of(identity.message_id)}
    if identity.message is not None and identity.message.id is not None:
        message = {**rewritten["message"], "id": messages.of(identity.message.id)}
        rewritten = {**rewritten, "message": message}
    if chunk.get("type") == _TURN_WITHDRAWN:
        withdrawn = _WithdrawnPrompt.model_validate(chunk["data"])
        data = {**chunk["data"], "messageId": messages.of(withdrawn.message_id)}
        rewritten = {**rewritten, "data": data}
    return rewritten


def rewrite_scratchpad_ids_in_chunk(
    chunk: dict[str, Any],
    id_map: dict[str, str],
) -> dict[str, Any]:
    if not id_map:
        return chunk
    chunk_type = chunk.get("type")
    if isinstance(chunk_type, str) and chunk_type in _SCRATCHPAD_TOOL_PART_TYPES:
        rewritten = dict(chunk)
        if "input" in rewritten:
            rewritten["input"] = rewrite_note_ids_in_payload(
                rewritten["input"],
                id_map,
            )
        if "output" in rewritten:
            rewritten["output"] = rewrite_note_ids_in_payload(
                rewritten["output"],
                id_map,
            )
        return rewritten
    if chunk_type == "user-message":
        message = chunk.get("message")
        if isinstance(message, dict):
            rewritten_msg = dict(message)
            parts = rewritten_msg.get("parts")
            if isinstance(parts, list):
                rewritten_msg["parts"] = [
                    rewrite_note_ids_in_payload(p, id_map) for p in parts
                ]
            return {**chunk, "message": rewritten_msg}
    return chunk


def rewrite_note_ids_in_payload(
    payload: Any,
    id_map: dict[str, str],
) -> Any:
    """Swap scratchpad note ids inside a JSON-like payload.

    Only values at known note-id keys are rewritten.
    """
    note_id_keys = {"id", "noteId", "note_id", "sourceNoteId", "source_note_id"}
    if isinstance(payload, dict):
        rewritten: dict[str, Any] = {}
        for key, value in payload.items():
            if key in note_id_keys and isinstance(value, str) and value in id_map:
                rewritten[key] = id_map[value]
            else:
                rewritten[key] = rewrite_note_ids_in_payload(value, id_map)
        return rewritten
    if isinstance(payload, list):
        return [rewrite_note_ids_in_payload(item, id_map) for item in payload]
    return payload
