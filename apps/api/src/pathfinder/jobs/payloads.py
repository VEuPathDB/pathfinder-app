"""The typed payload of this application's chat-turn job.

Procrastinate has no pydantic awareness: ``defer_async`` receives a JSON dict
of task kwargs, so the model is dumped at the dispatch and validated at the
worker entry point. The VEuPathDB auth token is a plain ``str`` because
``model_dump`` masks a ``SecretStr`` to ``"**********"``, which would destroy
the value at the producer. The log redaction is
``pathfinder.jobs.logging_filters``.
"""

from __future__ import annotations

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict
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


__all__ = ["ChatTurnPayload"]
