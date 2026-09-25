from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from assistant_core.conversation.event_writer import ChatWriter
from assistant_core.conversation.open_tool_calls import (
    OpenToolCalls,
    write_tool_call_errors,
)
from assistant_core.graph.stream_events import (
    conversation_title_event,
    turn_failed_event,
    turn_status_event,
    turn_stopped_event,
)
from assistant_core.graph.turn_state import DurableTaskResult
from assistant_core.mcp.resolution import ResolvedToolSources
from assistant_core.platform.context import PhaseOverrides, attach_phase_overrides
from assistant_core.platform.logging import get_logger
from assistant_core.spec import (
    AssistantSpec,
    TurnContextRequest,
    turn_input,
)
from pydantic_ai.ui.vercel_ai.response_types import (
    DoneChunk,
    ErrorChunk,
    FinishChunk,
    StartChunk,
)

from pathfinder.ai.capabilities.security import tool_output_scan
from pathfinder.ai.conversation._turn_helpers import (
    _extract_chunk,
    build_turn_start,
    resolve_site_id,
)
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.ai.conversation.title_generator import charged_conversation_title
from pathfinder.ai.conversation.turn_failure import (
    turn_closed_on_failure,
    turn_failure_text,
)
from pathfinder.ai.conversation.turn_stop import watch_for_cancel
from pathfinder.platform.tool_sources import source_credential
from pathfinder.services.conversations.turns import (
    load_conversation,
    name_conversation_if_unnamed,
)

logger = get_logger(__name__)


_TASK_STARTED = "data-background-task-started"

# A ceiling on the wait for the thread title. The turn finishes without a
# title when the title model is slower than this.
_TITLE_WAIT_SECONDS = 15.0


@dataclass
class _DriveResult:
    suspended: bool = False
    encountered_error: bool = False
    cancelled: bool = False


@dataclass
class _TrackingWriter:
    """Writes through and remembers which tool calls are still open."""

    inner: ChatWriter
    conversation_id: UUID
    turn_id: UUID
    open_calls: OpenToolCalls

    async def write(self, chunk: dict[str, Any]) -> int:
        self.open_calls.observe(chunk)
        return await self.inner.write(chunk)


@dataclass
class _StreamConsumerCtx:
    compiled_graph: Any
    graph_input: dict[str, Any]
    thread_config: dict[str, Any]
    runtime_context: Any
    writer: ChatWriter
    result: _DriveResult


@dataclass(frozen=True)
class TurnRequest:
    """One turn's inputs: who asked, and what answer it carries.

    ``durable_result`` marks the turn a worker opens to answer a durable call
    the thread parked; ``durable_results`` answers every call the same model
    step parked.
    """

    body: ChatRequestBody
    user_id: UUID
    durable_result: DurableTaskResult | None = None
    durable_results: tuple[DurableTaskResult, ...] = ()


async def run_turn(
    *,
    request: TurnRequest,
    spec: AssistantSpec,
    compiled_graph: Any,
    memory_store: Any,
    writer: ChatWriter,
) -> None:
    """Drive one chat turn to completion, writing chunks through ``writer``.

    Runs to completion regardless of client state; a disconnect cancels nothing.
    The procrastinate worker that calls this coroutine is the owner; any client
    reattaches via the events SSE endpoint in a later task.
    """
    body = request.body
    async with contextlib.AsyncExitStack() as tool_source_sessions:
        async with turn_closed_on_failure(writer):
            conversation = await load_conversation(body.conversation_id)
            effective_site_id = resolve_site_id(
                chat_site_id=conversation.site_id if conversation is not None else None,
                body_site_id=body.site_id,
                conversation_id=body.conversation_id,
            )
            body = body.model_copy(update={"site_id": effective_site_id})
            resolved = await tool_source_sessions.enter_async_context(
                ResolvedToolSources(
                    declarations=spec.tool_sources,
                    credential=source_credential,
                    scan=tool_output_scan(),
                ),
            )
            runtime_context = await spec.build_turn_context(
                TurnContextRequest(
                    conversation=conversation,
                    site_id=effective_site_id,
                    user_id=request.user_id,
                    memory_store=memory_store,
                    cancel_event=asyncio.Event(),
                    phase_models=body.runtime_phase_models,
                    phase_reasoning=body.runtime_phase_reasoning,
                    tool_sources=dict(resolved.by_name),
                ),
            )
        # Work this turn defers outlives the turn, so it reads the picks here.
        with attach_phase_overrides(
            PhaseOverrides(
                models=body.runtime_phase_models,
                reasoning=body.runtime_phase_reasoning,
            ),
        ):
            await _run_turn_with_context(
                request=dataclasses.replace(request, body=body),
                spec=spec,
                compiled_graph=compiled_graph,
                runtime_context=runtime_context,
                writer=writer,
            )


async def _run_turn_with_context(
    *,
    request: TurnRequest,
    spec: AssistantSpec,
    compiled_graph: Any,
    runtime_context: Any,
    writer: ChatWriter,
) -> None:
    body = request.body
    turn_message_id = writer.turn_id
    async with turn_closed_on_failure(writer):
        turn_token = await spec.turn_prologue(body.conversation_id)
        start_event_id = await writer.write(
            StartChunk(message_id=str(turn_message_id)).model_dump(
                by_alias=True,
                mode="json",
                exclude_none=True,
            ),
        )
        await writer.write(
            turn_status_event(label="Starting the turn").model_dump(
                by_alias=True,
                mode="json",
                exclude_none=True,
            ),
        )
        graph_input = _graph_input(request, spec, writer, start_event_id)

    title_task: asyncio.Task[str] | None = None
    if body.last_user_text.strip():
        title_task = asyncio.create_task(
            charged_conversation_title(
                body.last_user_text, spec.build_mock_model, user_id=request.user_id
            ),
        )

    result = await _drive_graph(
        body=body,
        graph_input=graph_input,
        compiled_graph=compiled_graph,
        runtime_context=runtime_context,
        writer=writer,
    )

    finish_reason = (
        "error"
        if result.encountered_error
        else "other"
        if result.suspended or result.cancelled
        else "stop"
    )
    if result.cancelled:
        await spec.turn_cancel(body.conversation_id, turn_token)
        await writer.write(
            turn_stopped_event().model_dump(
                by_alias=True,
                mode="json",
                exclude_none=True,
            ),
        )
    if spec.turn_epilogue is not None:
        for chunk in await spec.turn_epilogue(body.conversation_id):
            await writer.write(chunk)
    if title_task is not None:
        await _write_title(title_task, body.conversation_id, writer)
    await writer.write(
        FinishChunk(finish_reason=finish_reason).model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        ),
    )
    await writer.write(
        DoneChunk().model_dump(by_alias=True, mode="json", exclude_none=True),
    )


async def _consume_graph_stream(ctx: _StreamConsumerCtx) -> None:
    async for payload in ctx.compiled_graph.astream(
        ctx.graph_input,
        config=ctx.thread_config,
        context=ctx.runtime_context,
        stream_mode="custom",
    ):
        await _handle_custom(payload, ctx.result, ctx.writer)


def _graph_input(
    request: TurnRequest,
    spec: AssistantSpec,
    writer: ChatWriter,
    start_event_id: int,
) -> dict[str, Any]:
    return turn_input(
        spec.build_initial_state(
            build_turn_start(
                request.body,
                request.user_id,
                turn_message_id=writer.turn_id,
                turn_start_event_id=start_event_id - 1,
                durable_result=request.durable_result,
                durable_results=request.durable_results,
            ),
        ),
    )


async def _drive_graph(
    *,
    body: ChatRequestBody,
    graph_input: dict[str, Any],
    compiled_graph: Any,
    runtime_context: Any,
    writer: ChatWriter,
) -> _DriveResult:
    result = _DriveResult()
    open_calls = OpenToolCalls()
    tracked = _TrackingWriter(
        inner=writer,
        conversation_id=writer.conversation_id,
        turn_id=writer.turn_id,
        open_calls=open_calls,
    )
    turn_message_id: UUID = graph_input["turn_message_id"]
    thread_config = {
        "configurable": {"thread_id": str(body.conversation_id)},
        "metadata": {
            "turn_id": str(turn_message_id),
            "user_prompt_preview": body.last_user_text[:120],
        },
    }
    cancel_event: asyncio.Event = runtime_context.cancel_event

    consume_task = asyncio.create_task(
        _consume_graph_stream(
            _StreamConsumerCtx(
                compiled_graph=compiled_graph,
                graph_input=graph_input,
                thread_config=thread_config,
                runtime_context=runtime_context,
                writer=tracked,
                result=result,
            ),
        ),
    )

    async def _kill_on_cancel() -> None:
        await cancel_event.wait()
        consume_task.cancel()

    cancel_watcher = asyncio.create_task(
        watch_for_cancel(
            conversation_id=body.conversation_id,
            turn_id=turn_message_id,
            cancel_event=cancel_event,
        ),
    )
    killer = asyncio.create_task(_kill_on_cancel())
    try:
        await consume_task
    except asyncio.CancelledError:
        if cancel_event.is_set():
            result.cancelled = True
            await write_tool_call_errors(
                tracked,
                open_calls.ids(),
                "Stopped by the user.",
            )
        else:
            raise
    except Exception as exc:
        result.encountered_error = True
        logger.exception(
            "Turn runner failed",
            conversation_id=str(body.conversation_id),
            user_id=str(graph_input.get("user_id")),
            error_type=type(exc).__name__,
            error_detail=str(exc),
        )
        error_text = turn_failure_text(exc, graph_ran=True)
        await write_tool_call_errors(tracked, open_calls.ids(), error_text)
        for chunk in (
            ErrorChunk(error_text=error_text),
            turn_failed_event(error_text=error_text),
        ):
            await tracked.write(
                chunk.model_dump(by_alias=True, mode="json", exclude_none=True),
            )
    finally:
        cancel_watcher.cancel()
        killer.cancel()
        for task in (cancel_watcher, killer):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
    return result


async def _handle_custom(
    payload: object,
    result: _DriveResult,
    writer: ChatWriter,
) -> None:
    chunk = _extract_chunk(payload)
    if chunk is None:
        return
    if chunk.get("type") == _TASK_STARTED:
        result.suspended = True
    await writer.write(chunk)


async def _write_title(
    title_task: asyncio.Task[str],
    conversation_id: UUID,
    writer: ChatWriter,
) -> None:
    """Write the thread's title as the last chunk before the turn finishes."""
    try:
        title = await asyncio.wait_for(title_task, _TITLE_WAIT_SECONDS)
    except TimeoutError:
        logger.warning(
            "Conversation title generation exceeded its wait",
            conversation_id=str(conversation_id),
        )
        return
    except Exception:
        logger.exception("Conversation title generation failed")
        return
    if not title:
        return
    try:
        named = await name_conversation_if_unnamed(conversation_id, title=title)
    except Exception:
        # The next turn names the thread, so a failed write costs one chunk.
        logger.exception(
            "Naming the thread failed", conversation_id=str(conversation_id)
        )
        return
    if not named:
        return
    await writer.write(
        conversation_title_event(title=title).model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        ),
    )
