"""Worker-side impl for ``separate_controls``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from assistant_core.memory.store import MemoryStore
from assistant_core.tasks.progress import TaskProgressEmitter
from pydantic import JsonValue
from veupathdb_mcp.separation import (
    SeparationPhase,
    SeparationRequest,
    SeparationUpdate,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.domain.separation import SEPARATION_BUDGET, SeparationMode
from pathfinder.services.evidence.separation import (
    searches_the_thread_runs,
    separate_controls,
)

# A measured row closes its candidate's own lane, so its lane is complete.
_PHASE_PERCENT: dict[SeparationPhase, float] = {
    "resolved": 0.05,
    "uploaded": 0.1,
    "collected": 0.2,
    "measured": 1.0,
    "assembled": 0.9,
    "confirmed": 1.0,
}


@dataclass
class _Rows:
    """Where each row of a run is written: the task's own, or its candidate's lane."""

    progress: TaskProgressEmitter
    lanes: dict[str, TaskProgressEmitter] = field(default_factory=dict)

    def _lane(self, candidate_id: str) -> TaskProgressEmitter:
        lane = self.lanes.get(candidate_id)
        if lane is None:
            lane = self.progress.scoped(candidateId=candidate_id)
            self.lanes[candidate_id] = lane
        return lane

    async def write(self, update: SeparationUpdate) -> None:
        emitter = (
            self.progress
            if update.candidate_id is None
            else self._lane(update.candidate_id)
        )
        await emitter.update(
            percent=_PHASE_PERCENT[update.phase],
            message=update.message,
            data=dict(update.data),
        )

    async def close(self) -> None:
        # Each lane has its own buffer, which the task's flush does not drain.
        for lane in self.lanes.values():
            await lane.aclose()
        await self.progress.flush()


async def separate_controls_impl(
    *,
    context: Context,
    task_id: UUID,
    progress: TaskProgressEmitter,
    memory_store: MemoryStore | None,
    positive_controls: list[str],
    negative_controls: list[str],
    mode: SeparationMode,
    literature: list[dict[str, JsonValue]] | None = None,
    budget: int = SEPARATION_BUDGET,
    **_extra: Any,
) -> dict[str, Any]:
    """Run one separation on the thread's site and return ``SeparationReport`` as JSON.

    The thread's own leaves are candidates, read from its strategy without a model.
    """
    del memory_store
    progress.batch_size = 8
    request = SeparationRequest.model_validate(
        {
            "positives": positive_controls,
            "negatives": negative_controls,
            "mode": mode,
            "literature": literature or [],
            "thread": searches_the_thread_runs(
                context.strategy_session.get_graph(None)
            ),
            "budget": budget,
        }
    )
    rows = _Rows(progress)
    try:
        report = await separate_controls(
            context.site_id, request, task_id=task_id, progress=rows.write
        )
    finally:
        await rows.close()
    return report.model_dump(by_alias=True, mode="json")
