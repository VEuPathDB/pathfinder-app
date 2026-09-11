"""Worker-side impl for ``run_control_tests_on_step``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from assistant_core.memory.store import MemoryStore
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.tasks.progress import TaskProgressEmitter
from pydantic import Field
from veupathdb.errors import VEuPathDBError
from veupathdb.logging import get_logger
from veupathdb.wdk.factory import get_strategy_api
from veupathdb_mcp.controls import run_step_control_tests
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.graph.runtime import Context
from pathfinder.services.experiment.published_names import published_names
from pathfinder.services.export.control_downloads import attach_control_downloads

logger = get_logger(__name__)


class TestedStep(CamelModel):
    """How WDK names the tested step and the parameters it ran."""

    search_name: str = ""
    label: str = ""
    parameter_labels: dict[str, str] = Field(default_factory=dict)


async def _tested_step(site_id: str, wdk_step_id: int) -> TestedStep:
    """What WDK calls the tested step. Empty when WDK refuses the step."""
    try:
        step = await get_strategy_api(site_id).find_step(wdk_step_id)
    except VEuPathDBError as exc:
        logger.warning(
            "Control test could not name the tested step",
            step_id=wdk_step_id,
            error=str(exc),
        )
        return TestedStep()
    published = await published_names(
        site_id, step.record_class_name or "", step.search_name
    )
    return TestedStep(
        search_name=step.search_name,
        label=step.custom_name or step.display_name or published.label,
        parameter_labels=published.parameter_labels,
    )


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

    tested = await _tested_step(context.site_id, wdk_step_id)
    result.target.search_name = tested.search_name

    emitted = 0
    if result.positive is not None:
        emitted += 1
        await progress.update(
            percent=emitted / (total_sets + 1),
            message="Compared against positive controls",
            data={
                "positive_controls_count": result.positive.controls_count,
                "positive_intersection": result.positive.intersection_count,
            },
        )
    if result.negative is not None:
        emitted += 1
        await progress.update(
            percent=emitted / (total_sets + 1),
            message="Compared against negative controls",
            data={
                "negative_controls_count": result.negative.controls_count,
                "negative_intersection": result.negative.intersection_count,
            },
        )

    await progress.update(percent=0.9, message="Exporting results", data=None)
    exported = await attach_control_downloads(
        ControlOutcome.model_validate(result), f"step_{wdk_step_id}_control_tests"
    )
    await progress.update(percent=1.0, message="Control tests complete", data=None)
    # The library's outcome carries the numbers; only WDK names the step and
    # its parameters, so the worker reports those names beside them.
    reported = exported.model_dump(by_alias=True, exclude_none=True, mode="json")
    reported["targetLabel"] = tested.label
    reported["parameterLabels"] = tested.parameter_labels
    return reported
