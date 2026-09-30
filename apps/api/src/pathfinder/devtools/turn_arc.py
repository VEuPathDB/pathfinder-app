"""Where a worker run stands on the thread's log: a turn still writing, a turn
parked on durable tasks, or a turn that ended."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from assistant_core.conversation.stream_parts.task_parts import BackgroundTaskStarted
from pydantic import BaseModel, ConfigDict

from pathfinder.devtools.models import Chunk

type ArcState = Literal["running", "parked", "ended"]

# The finish reason of a turn that suspended on a durable task or was stopped.
_SUSPENDED = "other"


class TurnArc(BaseModel):
    """The state of the last turn the log holds, and the tools it parked on."""

    model_config = ConfigDict(frozen=True)

    state: ArcState = "running"
    parked_on: tuple[str, ...] = ()


def read_arc(chunks: Iterable[Chunk]) -> TurnArc:
    """A turn that suspended on a task stays open until the turn its tasks open
    writes its own ``done``. A stopped turn ends whatever it started."""
    arc = TurnArc()
    tasks: list[str] = []
    stopped = False
    suspended = False
    for chunk in chunks:
        match chunk.type:
            case "start":
                arc, tasks, stopped, suspended = TurnArc(), [], False, False
            case "data-background-task-started":
                tasks.append(BackgroundTaskStarted.model_validate(chunk.data).tool_name)
            case "data-turn-stopped":
                stopped = True
            case "finish":
                suspended = chunk.finish_reason == _SUSPENDED
            case "done":
                parked = suspended and bool(tasks) and not stopped
                arc = (
                    TurnArc(state="parked", parked_on=tuple(tasks))
                    if parked
                    else TurnArc(state="ended")
                )
            case _:
                pass
    return arc
