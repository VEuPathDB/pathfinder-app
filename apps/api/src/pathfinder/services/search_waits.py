from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any

from assistant_core.conversation.event_writer import ChatWriter
from assistant_core.graph.stream_events import turn_status_event
from assistant_core.tasks.declaration import DurableToolImpl
from assistant_core.tasks.progress import TaskProgressEmitter
from veupathdb.wdk import SearchRequest, get_site, runs_an_expensive_search, search_turn
from veupathdb_mcp.search_line import told_while_waiting

from pathfinder.services.strategies.slow_searches import counts_slowly


def runs_on_the_deployment_line(request: SearchRequest) -> bool:
    return runs_an_expensive_search(request) or any(
        counts_slowly(request.site_id, name) for name in request.search_names
    )


def waiting_for(site_id: str) -> str:
    return f"Waiting for {get_site(site_id).name}"


class TurnStatusWaits:
    def __init__(self, writer: ChatWriter) -> None:
        self.writer = writer

    async def _say(self, label: str) -> None:
        await self.writer.write(
            turn_status_event(label=label).model_dump(
                by_alias=True, mode="json", exclude_none=True
            ),
        )

    async def waiting(self, site_id: str) -> None:
        await self._say(waiting_for(site_id))

    async def running(self, site_id: str) -> None:
        del site_id
        await self._say("")


@contextmanager
def researcher_search_turn(writer: ChatWriter) -> Iterator[None]:
    with search_turn(), told_while_waiting(TurnStatusWaits(writer)):
        yield


class ProgressWaits(TaskProgressEmitter):
    percent: float = 0.0
    message: str = ""

    async def update(
        self,
        *,
        percent: float,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.percent = percent
        self.message = message
        await super().update(percent=percent, message=message, data=data)

    async def waiting(self, site_id: str) -> None:
        await super().update(percent=self.percent, message=waiting_for(site_id))

    async def running(self, site_id: str) -> None:
        del site_id
        await super().update(percent=self.percent, message=self.message)


def told_on_progress(impl: DurableToolImpl) -> DurableToolImpl:
    @wraps(impl)
    async def body(*, progress: TaskProgressEmitter, **kwargs: Any) -> Any:
        waits = ProgressWaits(
            task_id=progress.task_id,
            conversation_id=progress.conversation_id,
            session_factory=progress.session_factory,
            batch_size=progress.batch_size,
            max_flush_interval_seconds=progress.max_flush_interval_seconds,
            on_thread=progress.on_thread,
        )
        try:
            with told_while_waiting(waits):
                return await impl(progress=waits, **kwargs)
        finally:
            await waits.aclose()

    return body


__all__ = [
    "ProgressWaits",
    "TurnStatusWaits",
    "researcher_search_turn",
    "runs_on_the_deployment_line",
    "told_on_progress",
    "waiting_for",
]
