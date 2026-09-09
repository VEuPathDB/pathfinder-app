"""Which assistant answers a turn.

A new conversation takes the assistant the request names, or the default. An
existing one keeps the assistant it was created with, and a request that
names another one is refused rather than answered by the wrong architecture.
A caller that is about to create the thread passes no id and reads no row.
"""

from __future__ import annotations

from uuid import UUID

from assistant_core.registry import AssistantRegistry, UnknownAssistantError
from assistant_core.spec import AssistantSpec

from pathfinder.platform.errors import AssistantMismatchError, AssistantNotFoundError
from pathfinder.services.conversations.authz import conversation_assistant_id


def resolve_assistant(registry: AssistantRegistry, assistant_id: str) -> AssistantSpec:
    """Look one assistant up, answering an unknown id as a 404."""
    try:
        return registry.resolve(assistant_id)
    except UnknownAssistantError as exc:
        raise AssistantNotFoundError(exc.assistant_id, exc.known) from exc


async def resolve_turn_assistant(
    *,
    registry: AssistantRegistry,
    conversation_id: UUID | None,
    requested_id: str | None,
) -> AssistantSpec:
    """The assistant this turn runs under."""
    existing = (
        None
        if conversation_id is None
        else await conversation_assistant_id(conversation_id)
    )
    if existing is None:
        return resolve_assistant(registry, requested_id or registry.default_id)
    if requested_id is not None and requested_id != existing:
        raise AssistantMismatchError(requested=requested_id, existing=existing)
    return resolve_assistant(registry, existing)


__all__ = ["resolve_assistant", "resolve_turn_assistant"]
