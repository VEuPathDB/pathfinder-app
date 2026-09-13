"""Standalone experiment control test tools for pydantic-ai migration."""

from typing import Any
from uuid import UUID

from assistant_core.graph.tool_summary import summary_chunks, with_summary
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.tasks.declaration import declare_durable_tool
from assistant_core.tasks.decorator import DurableOutcome
from pydantic import ConfigDict, Field
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk
from veupathdb.domain.parameters import ParamValue
from veupathdb_mcp import ToolErrorPayload, tool_error
from veupathdb_mcp.controls import IntersectionConfig, run_positive_negative_controls
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.stream_events import control_test_results_event
from pathfinder.ai.stream_part_payloads import (
    ControlSetSummary,
    ControlTestResults,
    TestedParameter,
)
from pathfinder.platform.durable_worker import durable_agent_tool
from pathfinder.platform.errors import ErrorCode
from pathfinder.platform.identity import CONTROL_TEST_STRATEGY_NAME
from pathfinder.services.experiment.published_names import published_names
from pathfinder.services.export.control_downloads import attach_control_downloads

logger = get_logger(__name__)


VALUE_CHARS = 120


def _shown(value: str) -> str:
    """A parameter value short enough to read in a table cell."""
    if len(value) <= VALUE_CHARS:
        return value
    return f"{value[:VALUE_CHARS].rstrip()} ..."


class _ControlCounts(CamelModel):
    """What a control test measured, flat as the worker reports it.

    A control set the test did not run leaves its count absent.
    ``target_label`` and ``parameter_labels`` are what WDK calls the tested
    step and its parameters, and they are empty when WDK did not answer.
    """

    model_config = ConfigDict(extra="ignore")

    step_id: int | None = None
    search_name: str = ""
    target_label: str = ""
    estimated_size: int = 0
    parameters: dict[str, ParamValue] = Field(default_factory=dict)
    parameter_labels: dict[str, str] = Field(default_factory=dict)
    positive_intersection: int | None = None
    positive_controls_count: int | None = None
    positive_recall: float | None = None
    positive_intersection_ids: list[str] = Field(default_factory=list)
    positive_missing_ids: list[str] = Field(default_factory=list)
    negative_intersection: int | None = None
    negative_controls_count: int | None = None
    negative_false_positive_rate: float | None = None
    negative_intersection_ids: list[str] = Field(default_factory=list)

    def positive_set(self) -> ControlSetSummary | None:
        """The positive set, or None when the test ran no positives."""
        if self.positive_controls_count is None:
            return None
        return ControlSetSummary(
            controls_count=self.positive_controls_count,
            intersection_count=self.positive_intersection or 0,
            recall=self.positive_recall,
            hit_ids=self.positive_intersection_ids,
            missed_ids=self.positive_missing_ids,
        )

    def negative_set(self) -> ControlSetSummary | None:
        """The negative set, or None when the test ran no negatives."""
        if self.negative_controls_count is None:
            return None
        return ControlSetSummary(
            controls_count=self.negative_controls_count,
            intersection_count=self.negative_intersection or 0,
            false_positive_rate=self.negative_false_positive_rate,
            hit_ids=self.negative_intersection_ids,
        )

    def reader_label(self) -> str:
        """What the tested step is called for a reader, never a url segment."""
        if self.target_label != "":
            return self.target_label
        return "the tested step" if self.step_id is None else f"step {self.step_id}"

    def criteria(self) -> list[TestedParameter]:
        """The tested step's parameters, each under the name WDK shows."""
        return [
            TestedParameter(
                label=self.parameter_labels.get(name, name),
                value=_shown(value.to_wire()),
            )
            for name, value in self.parameters.items()
        ]

    def exhibit(self, tool_call_id: str, task_id: str = "") -> ControlTestResults:
        """The numbered exhibit this control test leaves on the thread."""
        return ControlTestResults(
            task_id=task_id,
            tool_call_id=tool_call_id,
            target_step_id=self.step_id,
            target_label=self.reader_label(),
            target_estimated_size=self.estimated_size,
            target_parameters=self.criteria(),
            positive=self.positive_set(),
            negative=self.negative_set(),
        )


def controls_summary(counts: _ControlCounts) -> str:
    """How many known positives the tested result set returned."""
    return (
        f"{counts.positive_intersection or 0} of "
        f"{counts.positive_controls_count or 0} positive controls recovered"
    )


def _control_test_chunks_from_result(
    resumed: Any,
    task_id: UUID,
    tool_call_id: str | None,
) -> list[BaseChunk]:
    outcome = DurableOutcome.model_validate(resumed)
    if not outcome.succeeded or tool_call_id is None:
        return []
    counts = _ControlCounts.model_validate(outcome.result)
    exhibit = control_test_results_event(
        counts.exhibit(tool_call_id, task_id=str(task_id))
    )
    return [exhibit, *summary_chunks(tool_call_id, controls_summary(counts))]


CONTROL_TESTS = declare_durable_tool(
    tool_name="run_control_tests_on_step",
    estimated_duration_seconds=180,
    chunks_from_result=_control_test_chunks_from_result,
)


@durable_agent_tool(CONTROL_TESTS)
async def run_control_tests_on_step(
    ctx: RunContext[AgentDeps],
    wdk_step_id: int,
    positive_controls: list[str] | None = None,
    negative_controls: list[str] | None = None,
) -> dict[str, Any]:
    """Run control tests against an already-built WDK strategy step.

    Durable: this tool defers work to the verification worker and the turn
    ends while it runs. You are called again with a dict matching
    :class:`ControlOutcome`'s serialised shape.

    Tests directly against the strategy's actual results using Python set
    operations -- no temporary WDK strategy needed.  Use this after a
    multi-step strategy is built with ``build_strategy``.

    For testing a standalone (not-yet-built) search, use
    ``run_control_tests_on_search`` instead.

    Args:
        ctx: Agent run context.
        wdk_step_id: WDK step ID from a built strategy to test against.
            Read it from get_strategy(summary_only=false): the root step
            carries the WDK step id.
        positive_controls: Known-positive IDs that should be returned.
        negative_controls: Known-negative IDs that should NOT be returned.
    """
    del ctx, wdk_step_id, positive_controls, negative_controls
    msg = "run_control_tests_on_step runs on the worker via @durable_agent_tool"
    raise NotImplementedError(msg)


async def run_control_tests_on_search(
    ctx: RunContext[AgentDeps],
    target_search_name: str,
    target_parameters: dict[str, ParamValue],
    positive_controls: list[str] | None = None,
    negative_controls: list[str] | None = None,
    record_type: str = "transcript",
) -> ToolReturn[ControlOutcome | ToolErrorPayload]:
    """Run control tests against a standalone WDK search (not a built strategy).

    Creates a temporary WDK strategy to intersect the search results with
    control gene IDs.  Use ``run_control_tests_on_step`` instead when you
    already have a built multi-step strategy.

    Controls are matched via ``GeneByLocusTag`` (parameter ``ds_gene_ids``).

    Args:
        ctx: Agent run context.
        target_search_name: WDK search/question urlSegment to test.
        target_parameters: Target search parameter mapping. Each value MUST be
            wrapped in its typed shape - see the ``valueFormat`` field from
            ``get_search_overview`` for the per-param template.
        positive_controls: Known-positive IDs that should be returned.
        negative_controls: Known-negative IDs that should NOT be returned.
        record_type: Record type. Defaults to 'transcript'.
    """
    if not positive_controls and not negative_controls:
        return with_summary(
            tool_error(
                ErrorCode.VALIDATION_ERROR,
                "At least one of positive_controls or negative_controls "
                "must be provided.",
            ),
            "No control ids given to test against",
            ctx=ctx,
            status="warn",
        )
    measured = await run_positive_negative_controls(
        IntersectionConfig(
            site_id=ctx.deps.site_id,
            record_type=record_type,
            target_search_name=target_search_name,
            target_parameters=dict(target_parameters),
            controls_search_name="GeneByLocusTag",
            controls_param_name="ds_gene_ids",
            controls_value_format="newline",
            internal_strategy_name=CONTROL_TEST_STRATEGY_NAME,
        ),
        positive_controls=positive_controls,
        negative_controls=negative_controls,
    )
    outcome = await attach_control_downloads(
        ControlOutcome.model_validate(measured),
        f"{target_search_name}_control_tests",
    )
    published = await published_names(ctx.deps.site_id, record_type, target_search_name)
    counts = _ControlCounts.model_validate(
        outcome.model_dump()
        | {
            "target_label": published.label,
            "parameter_labels": published.parameter_labels,
        }
    )
    tool_call_id = ctx.tool_call_id or ""
    return with_summary(
        outcome,
        controls_summary(counts),
        ctx=ctx,
        extra=[control_test_results_event(counts.exhibit(tool_call_id))],
    )
