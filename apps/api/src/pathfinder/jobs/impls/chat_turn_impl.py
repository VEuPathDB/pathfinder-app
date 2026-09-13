from __future__ import annotations

import contextlib
from contextlib import nullcontext
from typing import Any

from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.models.capture import capture_llm
from assistant_core.platform.logging import get_logger
from assistant_core.tasks.scope import (
    attach_conversation_application,
    attach_user_id,
)

from pathfinder.ai.conversation.turn_runner import (
    TurnRequest,
    run_turn,
    turn_closed_on_failure,
)
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.jobs.auth_context import attach_wdk_auth
from pathfinder.jobs.payloads import ChatTurnPayload
from pathfinder.platform.config import get_settings

logger = get_logger(__name__)


async def run_chat_turn(payload: dict[str, Any]) -> None:
    """Procrastinate job body — drives one chat turn through the worker.

    Payload crosses a process boundary (api → worker) so we re-install the
    user's VEuPathDB auth cookie on ``veupathdb_auth_token_ctx`` for the
    duration of the turn. Without this, every WDK call from the agent
    would fall through to the service-account token in settings.
    """
    parsed = ChatTurnPayload.model_validate(payload)
    body = parsed.body

    registry = get_assistant_registry()
    spec = registry.resolve(parsed.assistant_id)

    writer = ChatEventWriter(
        conversation_id=body.conversation_id,
        turn_id=parsed.turn_id,
    )
    settings = get_settings()
    async with (
        attach_wdk_auth(parsed.veupathdb_auth_token),
        attach_user_id(parsed.user_id),
        attach_conversation_application(body.conversation_id),
        contextlib.AsyncExitStack() as stores,
    ):
        async with turn_closed_on_failure(writer):
            saver = await stores.enter_async_context(
                lifespan_checkpointer(
                    settings.database_url,
                    checkpoint_types=registry.checkpoint_types(),
                ),
            )
            store = await stores.enter_async_context(
                lifespan_memory_store(settings.database_url),
            )
            graph = spec.build_graph(saver)
        capture = (
            capture_llm(parsed.capture_dir) if parsed.capture_dir else nullcontext()
        )
        with capture:
            await run_turn(
                request=TurnRequest(body=body, user_id=parsed.user_id),
                spec=spec,
                compiled_graph=graph,
                memory_store=store,
                writer=writer,
            )
    logger.info(
        "chat turn completed",
        conversation_id=str(body.conversation_id),
        turn_id=str(parsed.turn_id),
        assistant_id=spec.assistant_id,
        has_veupathdb_auth=parsed.veupathdb_auth_token is not None,
    )
