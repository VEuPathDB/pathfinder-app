"""The researcher's provider keys, for the one turn a worker runs.

The worker reads the keys by user id, never from a job payload, and holds them
in a context scope for the turn alone. A turn nobody may pay for is refused
before its graph runs; a key a provider refused during the turn is marked after.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from assistant_core.conversation.event_writer import ChatWriter
from assistant_core.spec import AssistantSpec

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.ai.conversation.turn_failure import turn_closed_on_failure
from pathfinder.assistants.registry import assistant_role_models
from pathfinder.platform.model_keys import (
    ProviderBuilder,
    attach_keyring,
    build_provider,
)
from pathfinder.services.provider_keys import (
    load_keyring,
    record_refusals,
    require_payers,
)


@asynccontextmanager
async def turn_keys(
    *,
    user_id: UUID,
    spec: AssistantSpec,
    body: ChatRequestBody,
    writer: ChatWriter,
    build: ProviderBuilder = build_provider,
) -> AsyncIterator[None]:
    """Run one turn under the researcher's keys, or end it with the refusal.

    ``build`` makes the provider client each model call sends a key through.
    """
    async with turn_closed_on_failure(writer):
        keyring = await load_keyring(user_id)
        roles = assistant_role_models(spec.assistant_id, body.runtime_phase_models)
        require_payers(roles.values(), keyring.statuses())
    with attach_keyring(keyring, build) as keys:
        try:
            yield
        finally:
            await record_refusals(user_id, keys.refusals)


__all__ = ["turn_keys"]
