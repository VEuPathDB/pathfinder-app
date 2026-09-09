"""Typed payloads for procrastinate jobs.

Procrastinate has no pydantic awareness: ``defer_async`` receives a JSON-dict
of task kwargs which psycopg wraps in ``Jsonb`` before persisting. We dump
these models with ``model_dump(mode="json", by_alias=True)`` at the dispatch
site and ``model_validate`` at the worker entrypoint. The VEuPathDB auth
token is a plain ``str`` (not ``SecretStr``) because ``model_dump`` masks
SecretStr to ``"**********"`` by default — that would destroy the value at
the producer side. Redaction happens in logs via
``pathfinder.jobs.logging_filters``, not by in-memory masking.
"""

from __future__ import annotations

from typing import Self
from uuid import UUID

from assistant_core.models.capture import current_capture_dir
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, Field
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.ai.conversation.request_body import ChatRequestBody


class ChatTurnPayload(BaseModel):
    """Typed payload for the ``chat_turn:run`` procrastinate job."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    body: ChatRequestBody
    user_id: UUID
    turn_id: UUID
    # The assistant the dispatcher resolved from the conversation row.
    assistant_id: str
    veupathdb_auth_token: str | None = None
    capture_dir: str | None = None

    @classmethod
    def from_context(
        cls,
        *,
        body: ChatRequestBody,
        user_id: UUID,
        turn_id: UUID,
        assistant_id: str,
        capture_dir: str | None = None,
    ) -> Self:
        """Build a payload, capturing ``veupathdb_auth_token_ctx`` at call time.
        ``capture_dir`` (devtools only) routes worker LLM capture to a run-dir."""
        return cls(
            body=body,
            user_id=user_id,
            turn_id=turn_id,
            assistant_id=assistant_id,
            veupathdb_auth_token=veupathdb_auth_token_ctx.get(),
            capture_dir=capture_dir,
        )


class DurableTaskPayload(BaseModel):
    """Typed payload for ``durable:<tool_name>`` procrastinate jobs."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task_id: UUID
    thread_id: UUID
    args: JSONObject = Field(default_factory=dict)
    veupathdb_auth_token: str | None = None
    capture_dir: str | None = None

    @classmethod
    def from_context(
        cls,
        *,
        task_id: UUID,
        thread_id: UUID,
        args: JSONObject,
    ) -> Self:
        """Build a durable payload, capturing ``veupathdb_auth_token_ctx`` and the
        active LLM-capture run-dir so the worker resume job keeps capturing."""
        return cls(
            task_id=task_id,
            thread_id=thread_id,
            args=args,
            veupathdb_auth_token=veupathdb_auth_token_ctx.get(),
            capture_dir=current_capture_dir(),
        )


__all__ = ["ChatTurnPayload", "DurableTaskPayload"]
