"""Worker-side impl for ``run_control_tests_on_step``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from assistant_core.memory.store import MemoryStore

from pathfinder.ai.graph.runtime import Context
from pathfinder.jobs.progress import TaskProgressEmitter
from pathfinder.services.control_tests import run_step_control_tests
from pathfinder.services.tool_payloads import attach_control_downloads


async def run_control_tests_on_step_impl(
    *,
    context: Context,
    task_id: UUID,
    progress: TaskProgressEmitter,
    memory_store: MemoryStore | None,
    wdk_step_id: int,
    positive_controls: list[str] | None = None,
    negative_controls: list[str] | None = None,
    **_extra: Any,
) -> dict[str, Any]:
    """Run control tests against a built WDK step and return the result dict."""
    del task_id, memory_store

    has_positives = bool(positive_controls)
    has_negatives = bool(negative_controls)
    if not has_positives and not has_negatives:
        msg = "At least one of positive_controls or negative_controls must be provided."
        raise ValueError(msg)

    total_sets = int(has_positives) + int(has_negatives)

    await progress.update(
        percent=0.0,
        message=f"Querying WDK step {wdk_step_id}",
        data={"wdk_step_id": wdk_step_id, "total_sets": total_sets},
    )

    result = await run_step_control_tests(
        site_id=context.site_id,
        wdk_step_id=wdk_step_id,
        positive_controls=positive_controls,
        negative_controls=negative_controls,
    )

    emitted = 0
    if has_positives:
        emitted += 1
        await progress.update(
            percent=emitted / (total_sets + 1),
            message="Compared against positive controls",
            data={
                "positive_controls_count": result.positive_controls_count,
                "positive_intersection": result.positive_intersection,
            },
        )
    if has_negatives:
        emitted += 1
        await progress.update(
            percent=emitted / (total_sets + 1),
            message="Compared against negative controls",
            data={
                "negative_controls_count": result.negative_controls_count,
                "negative_intersection": result.negative_intersection,
            },
        )

    await progress.update(percent=0.9, message="Exporting results", data=None)
    exported = await attach_control_downloads(
        result, f"step_{wdk_step_id}_control_tests"
    )
    await progress.update(percent=1.0, message="Control tests complete", data=None)
    return exported.model_dump(by_alias=True, exclude_none=True, mode="json")
