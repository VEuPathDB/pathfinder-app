"""Worker-side runner for durable tool invocations.

Called from Procrastinate tasks (see ``jobs/tasks.py``). Looks up the real
implementation in ``TOOL_REGISTRY``, builds a worker-side ``Context``,
executes the impl, persists the result on the ``background_tasks`` row, and
hands the answer to ``jobs/completion_turn.py``, which opens the NEW turn on
the thread.
"""

from __future__ import annotations

import dataclasses
from contextlib import nullcontext
from typing import Any, Literal
from uuid import UUID

from assistant_core.conversation.event_writer import append_chunk
from assistant_core.graph.stream_events import task_completed_event
from assistant_core.graph.turn_state import DurableTaskResult
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.memory.store import MemoryStore
from assistant_core.models.capture import capture_llm
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from pydantic import BaseModel

from pathfinder.jobs.auth_context import (
    attach_conversation_application,
    attach_user_id,
    attach_wdk_auth,
)
from pathfinder.jobs.completion_turn import safe_completion_turn
from pathfinder.jobs.progress import TaskProgressEmitter
from pathfinder.jobs.registry import TOOL_REGISTRY
from pathfinder.jobs.runtime import build_worker_runtime_context
from pathfinder.persistence.repositories.background_tasks import (
    BackgroundTaskRepository,
)
from pathfinder.platform.config import get_settings

logger = get_logger(__name__)


async def run_durable_task(
    *,
    tool_name: str,
    task_id: str,
    thread_id: str,
    args: dict[str, Any],
    veupathdb_auth_token: str | None = None,
    capture_dir: str | None = None,
) -> None:
    """Execute a durable tool impl on the worker and open the completion turn.

    The worker-to-worker procrastinate hop drops ``ContextVar`` state, so the
    dispatcher (``@durable_tool`` wrapper) serializes the VEuPathDB auth
    cookie into the task payload and we re-install it here for the impl's
    lifetime. Without this, any WDK call inside the impl (enrichment,
    control tests, optimization) would fall through to the service-account
    token in settings. ``capture_dir`` (devtools only) re-installs LLM capture
    so the completion turn, where the agent reads the result, is recorded.
    """
    capture = capture_llm(capture_dir) if capture_dir else nullcontext()
    with capture:
        await _run_durable_task_inner(
            tool_name=tool_name,
            task_id=task_id,
            thread_id=thread_id,
            args=args,
            veupathdb_auth_token=veupathdb_auth_token,
        )


async def _run_durable_task_inner(
    *,
    tool_name: str,
    task_id: str,
    thread_id: str,
    args: dict[str, Any],
    veupathdb_auth_token: str | None = None,
) -> None:
    task_uuid = UUID(task_id)
    chat_uuid = UUID(thread_id)
    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    await repo.mark_running(task_id=task_uuid)

    impl = TOOL_REGISTRY.get(tool_name)
    if impl is None:
        error = f"unknown durable tool: {tool_name}"
        logger.error("durable runner missing impl", tool_name=tool_name)
        await repo.mark_failed(task_id=task_uuid, error=error)
        await _announce_completion(chat_uuid, task_uuid, "failed", error)
        await _answer_and_settle(
            repo,
            thread_id=thread_id,
            result=DurableTaskResult(task_id=task_uuid, status="failed", error=error),
            veupathdb_auth_token=veupathdb_auth_token,
            fallback=(),
        )
        return

    progress = TaskProgressEmitter(
        task_id=task_uuid,
        conversation_id=chat_uuid,
        session_factory=async_session_factory,
    )

    settings = get_settings()
    try:
        async with (
            attach_wdk_auth(veupathdb_auth_token),
            attach_conversation_application(chat_uuid),
            lifespan_memory_store(settings.database_url) as raw_memory,
        ):
            mem_store = MemoryStore(store=raw_memory)
            base_context = await build_worker_runtime_context(
                conversation_id=thread_id, task_id=task_id
            )
            context = dataclasses.replace(base_context, memory_store=raw_memory)
            async with attach_user_id(context.user_id):
                try:
                    payload = await impl(
                        context=context,
                        task_id=task_uuid,
                        conversation_id=chat_uuid,
                        progress=progress,
                        memory_store=mem_store,
                        **args.get("kwargs", {}),
                    )
                finally:
                    await progress.aclose()
    except Exception as exc:  # worker must record every failure
        logger.exception("durable tool failed", tool_name=tool_name)
        error = str(exc) or exc.__class__.__name__
        await repo.mark_failed(task_id=task_uuid, error=error)
        await _announce_completion(chat_uuid, task_uuid, "failed", error)
        await _answer_and_settle(
            repo,
            thread_id=thread_id,
            result=DurableTaskResult(task_id=task_uuid, status="failed", error=error),
            veupathdb_auth_token=veupathdb_auth_token,
            fallback=(),
        )
        return

    result = _to_dict(payload)
    await repo.mark_result_ready(task_id=task_uuid, result=result)
    await _announce_completion(chat_uuid, task_uuid, "success", None)
    await _answer_and_settle(
        repo,
        thread_id=thread_id,
        result=DurableTaskResult(task_id=task_uuid, status="success", result=result),
        veupathdb_auth_token=veupathdb_auth_token,
        fallback=(task_uuid,),
    )


async def _answer_and_settle(
    repo: BackgroundTaskRepository,
    *,
    thread_id: str,
    result: DurableTaskResult,
    veupathdb_auth_token: str | None,
    fallback: tuple[UUID, ...],
) -> None:
    """Open the completion turn, then close the rows it spoke for.

    ``fallback`` is settled when no parked run answered the task: a task whose
    own tool failed is already terminal, so the failure paths pass nothing.
    """
    outcome = await safe_completion_turn(
        thread_id,
        result,
        veupathdb_auth_token=veupathdb_auth_token,
    )
    if outcome.waiting:
        return
    for task_id in outcome.answered or fallback:
        if outcome.error:
            await repo.mark_failed(task_id=task_id, error=outcome.error)
        else:
            await repo.mark_complete(task_id=task_id)


async def _announce_completion(
    conversation_id: UUID,
    task_id: UUID,
    status: Literal["success", "failed"],
    error: str | None,
) -> None:
    """Record the tool's outcome on the thread, before the completion turn.

    The status reports whether the tool produced a result. A completion turn
    that then fails reports its own failure.
    """
    await append_chunk(
        conversation_id=conversation_id,
        chunk=task_completed_event(
            task_id=task_id,
            status=status,
            error=error,
        ).model_dump(by_alias=True, mode="json", exclude_none=True),
    )


def _to_dict(value: Any) -> dict[str, Any]:
    """Coerce an impl's return into a JSON-serialisable dict.

    Impls return either a Pydantic ``BaseModel`` (dumped via alias + JSON
    mode) or a plain dict. Anything else is wrapped under ``value`` so the
    serialised row stays valid JSON.
    """
    if isinstance(value, BaseModel):
        dumped = value.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if isinstance(value, dict):
        return dict(value)
    return {"value": value}
