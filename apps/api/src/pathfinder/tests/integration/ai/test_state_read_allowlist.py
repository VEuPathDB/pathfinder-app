"""Reading a finished thread decodes only allowlisted types.

The debugger's gate detection and the eval runner's verdict read both inspect a
thread through ``graph.aget_state``. LangGraph emits a serde event for every
type it decodes outside the msgpack allowlist, so a read that emits none proves
the allowlist reaches the decode.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.serde.event_hooks import (
    SerdeEvent,
    register_serde_event_listener,
)

from pathfinder.devtools.chat import (
    _gate_from_checkpoint,
    parse_run_args,
    resolve_run_assistant,
    run_once,
)
from pathfinder.platform.config import get_settings
from pathfinder.tests._support.wdk_cleanup import delete_the_threads_strategy

_PROMPT = "Build a comprehensive kinase strategy for Plasmodium."


async def _events_of_a_read_declaring_no_assistant_types(
    conversation_id: UUID,
    database_url: str,
) -> list[SerdeEvent]:
    """The same state read, with the assistant's own types left undeclared."""
    spec = await resolve_run_assistant(conversation_id)
    events: list[SerdeEvent] = []
    unregister = register_serde_event_listener(events.append)
    try:
        async with lifespan_checkpointer(database_url) as saver:
            config: RunnableConfig = {
                "configurable": {"thread_id": str(conversation_id)},
            }
            await spec.build_graph(saver).aget_state(config)
    finally:
        unregister()
    return events


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_aget_state_read_emits_no_unregistered_type_warning(
    tmp_path: Path, wdk_registered_token: str | None
) -> None:
    conversation_id = uuid4()
    try:
        exit_code = await run_once(
            parse_run_args(
                [
                    _PROMPT,
                    "--site",
                    "plasmodb",
                    "--mock",
                    "--approve",
                    "auto",
                    "--quiet",
                    "--conversation-id",
                    str(conversation_id),
                    "--run-dir",
                    str(tmp_path / "run"),
                ],
            ),
        )
        database_url = get_settings().database_url
        # A read that decoded nothing would satisfy the last assertion for the
        # wrong reason, so first prove this thread carries assistant state types.
        undeclared = await _events_of_a_read_declaring_no_assistant_types(
            conversation_id,
            database_url,
        )
        events: list[SerdeEvent] = []
        unregister = register_serde_event_listener(events.append)
        try:
            await _gate_from_checkpoint(conversation_id, database_url)
        finally:
            unregister()
    finally:
        await delete_the_threads_strategy(
            "plasmodb", conversation_id, wdk_registered_token
        )

    assert exit_code == 0
    assert undeclared, "the state read decoded no assistant type"
    assert events == []
