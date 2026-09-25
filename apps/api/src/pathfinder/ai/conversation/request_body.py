from __future__ import annotations

from typing import Literal
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ReasoningEffort
from pydantic import ConfigDict, Field, field_validator
from pydantic_ai.ui.vercel_ai._utils import iter_tool_approval_responses
from pydantic_ai.ui.vercel_ai.request_types import (
    FileUIPart,
    TextUIPart,
    UIMessage,
)

from pathfinder.ai.models.catalog import get_model_entry
from pathfinder.platform.tiers import KNOWN_ROLES

_TURN_FACTS = frozenset({"errors", "aborted", "finishReason"})
_PART_STREAM_FACTS = frozenset(
    {"resultProviderMetadata", "summary", "summaryStatus"},
)


def _without_stream_facts(entry: dict[str, object]) -> dict[str, object]:
    cleaned = {k: v for k, v in entry.items() if k not in _TURN_FACTS}
    parts = cleaned.get("parts")
    if isinstance(parts, list):
        cleaned["parts"] = [
            {k: v for k, v in part.items() if k not in _PART_STREAM_FACTS}
            if isinstance(part, dict)
            else part
            for part in parts
        ]
    return cleaned


class ChatRequestBody(CamelModel):
    """Typed body for ``POST /api/v1/chat`` (AI SDK v6 + PathFinder extras).

    The shape matches ``@ai-sdk/react``'s ``useChat`` submit payload
    (``trigger``, ``id``, ``messages``) with PathFinder-scoped fields
    (``conversationId``, ``siteId``, ``mode``) layered on
    via ``body`` on the client transport. The authenticated user UUID still
    comes from the ``pathfinder-auth`` cookie. ``messages`` uses pydantic-ai's
    ``UIMessage`` so deferred-tool approval-responded parts deserialize into
    the discriminated union and ``iter_tool_approval_responses`` works.
    """

    model_config = ConfigDict(extra="ignore")

    trigger: Literal["submit-message", "regenerate-message"] = "submit-message"
    id: str = ""
    messages: list[UIMessage] = Field(default_factory=list)

    conversation_id: UUID
    # Which assistant answers. Read only when the conversation is created; an
    # existing thread keeps the assistant it was created with.
    assistant_id: str | None = None
    site_id: str = Field(default="", max_length=50)
    mode: str = "strategy"
    # A role no installed assistant runs a model for is refused here, so the
    # runtime downstream only ever sees a role some preset names.
    phase_models: dict[str, str] = Field(default_factory=dict)
    phase_reasoning: dict[str, ReasoningEffort] = Field(default_factory=dict)

    @field_validator("messages", mode="before")
    @classmethod
    def _drop_reduction_turn_facts(cls, value: object) -> object:
        """Drop the members the client's thread holds and the strict message
        union forbids: the reduction's turn facts and the parts' stream facts."""
        if not isinstance(value, list):
            return value
        return [
            _without_stream_facts(entry) if isinstance(entry, dict) else entry
            for entry in value
        ]

    @field_validator("messages")
    @classmethod
    def _only_the_last_message_carries_files(
        cls, value: list[UIMessage]
    ) -> list[UIMessage]:
        """The worker reads every earlier turn from its checkpoint, so an
        earlier message's files are not carried again."""
        last = len(value) - 1
        return [
            message
            if index == last
            else message.model_copy(
                update={"parts": [p for p in message.parts if p.type != "file"]}
            )
            for index, message in enumerate(value)
        ]

    @field_validator("phase_models", "phase_reasoning")
    @classmethod
    def _roles_are_declared[ValueT](cls, value: dict[str, ValueT]) -> dict[str, ValueT]:
        """Reject a role no installed assistant runs a model for."""
        unknown = sorted(set(value) - KNOWN_ROLES)
        if unknown:
            msg = f"unknown phase roles: {unknown}"
            raise ValueError(msg)
        return value

    @field_validator("phase_models")
    @classmethod
    def _models_are_in_the_catalog(cls, value: dict[str, str]) -> dict[str, str]:
        """Reject a model id the catalog does not define."""
        for role, model_id in value.items():
            if get_model_entry(model_id) is None:
                msg = f"phase {role!r} requests unknown model {model_id!r}"
                raise ValueError(msg)
        return value

    @property
    def runtime_phase_models(self) -> dict[str, str]:
        """The validated per-role model picks, as the runtime keys them."""
        return dict(self.phase_models)

    @property
    def runtime_phase_reasoning(self) -> dict[str, ReasoningEffort]:
        """The validated per-role reasoning picks, as the runtime keys them."""
        return dict(self.phase_reasoning)

    @property
    def last_user_text(self) -> str:
        """The text of the last user message, one block per part."""
        if not self.messages:
            return ""
        last = self.messages[-1]
        if last.role != "user":
            return ""
        return "\n\n".join(
            part.text
            for part in last.parts
            if isinstance(part, TextUIPart) and part.text
        )

    @property
    def last_user_files(self) -> list[FileUIPart]:
        """The files the last user message carries, in the order it holds them."""
        if not self.messages or self.messages[-1].role != "user":
            return []
        return [p for p in self.messages[-1].parts if isinstance(p, FileUIPart)]

    @property
    def last_user_parts(self) -> list[dict[str, object]]:
        """The last user message as the event log records it: its text, then
        each file."""
        text = self.last_user_text
        parts: list[TextUIPart | FileUIPart] = [
            *([TextUIPart(text=text)] if text else []),
            *self.last_user_files,
        ]
        return [part.model_dump(by_alias=True, exclude_none=True) for part in parts]

    @property
    def last_user_message_id(self) -> UUID:
        if not self.messages or self.messages[-1].role != "user":
            msg = "ChatRequestBody.messages must end with a user message"
            raise ValueError(msg)
        return UUID(self.messages[-1].id)

    @property
    def is_approval_resume(self) -> bool:
        """True when this turn is the user's structured approve/deny click.

        SDK v6 fires a chat POST automatically (via ``sendAutomaticallyWhen``)
        after ``addToolApprovalResponse``; the request carries the assistant
        message with the ``approval-responded`` part instead of a new user
        message.
        """
        return any(True for _ in iter_tool_approval_responses(self.messages))

    @property
    def prior_assistant_message_id(self) -> UUID | None:
        if not self.is_approval_resume:
            return None
        for msg in reversed(self.messages):
            if msg.role == "assistant":
                return UUID(msg.id)
        return None
