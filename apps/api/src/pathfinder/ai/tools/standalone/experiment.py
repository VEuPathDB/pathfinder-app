"""The control tests VERIFY runs on a built step or on a search of its own."""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, NoReturn
from uuid import UUID

from assistant_core.graph.tool_summary import summary_chunks, with_summary
from assistant_core.platform.logging import get_logger
from assistant_core.tasks.declaration import declare_durable_tool
from assistant_core.tasks.decorator import DurableOutcome
from pydantic import ConfigDict, Field, JsonValue
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry, ToolFailed
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk
from veupathdb.domain.parameters import ParamValue
from veupathdb_mcp.controls import (
    CONTROLS_PARAM,
    CONTROLS_SEARCH,
    ControlTargetData,
    ControlTestResult,
    IntersectionConfig,
    NegativeControls,
    PositiveControls,
    run_positive_negative_controls,
)
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.stream_events import control_test_results_event
from pathfinder.ai.graph.turn_records import ControlTestRun, ControlTestTarget
from pathfinder.ai.stream_part_payloads import (
    ControlSetSummary,
    ControlTestResults,
    TestedParameter,
)
from pathfinder.ai.tools.standalone.control_repeats import (
    RepeatedControlTest,
    every_step_tested,
    repeated_control_test,
)
from pathfinder.ai.tools.standalone.saved_control_sets import unattached_set
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    NamedControlSet,
)
from pathfinder.platform.durable_worker import durable_agent_tool
from pathfinder.platform.identity import CONTROL_TEST_STRATEGY_NAME
from pathfinder.services.evidence.control_sets import (
    SavedControls,
    UnknownControlSetError,
    saved_control_set,
)
from pathfinder.services.evidence.optimization import tunable_parameters_of_search
from pathfinder.services.experiment.metrics import metrics_from_control_result
from pathfinder.services.experiment.published_names import published_names
from pathfinder.services.export.control_downloads import attach_control_downloads

logger = get_logger(__name__)


VALUE_CHARS = 120


def _shown(value: str) -> str:
    """A parameter value short enough to read in a table cell."""
    if len(value) <= VALUE_CHARS:
        return value
    return f"{value[:VALUE_CHARS].rstrip()} ..."


class _ControlCounts(ControlOutcome):
    """What a control test filed, flat as the worker reports it, with WDK's names.

    ``target_label`` and ``parameter_labels`` are what WDK calls the tested
    step and its parameters, and they are empty when WDK did not answer.
    """

    model_config = ConfigDict(extra="ignore")

    target_label: str = ""
    parameter_labels: dict[str, str] = Field(default_factory=dict)
    tunable_parameters: list[str] = Field(default_factory=list)
    control_set: NamedControlSet | None = None

    def positive_controls(self) -> PositiveControls | None:
        """The positive set, or None when the test was given no positives."""
        match (self.positive_recovered_ids, self.positive_missed_ids):
            case (list() as recovered, list() as missed):
                return PositiveControls(recovered_ids=recovered, missed_ids=missed)
            case _:
                return None

    def negative_controls(self) -> NegativeControls | None:
        """The negative set, or None when the test was given no negatives."""
        match (self.negative_admitted_ids, self.negative_excluded_ids):
            case (list() as admitted, list() as excluded):
                return NegativeControls(admitted_ids=admitted, excluded_ids=excluded)
            case _:
                return None

    def measured(self) -> ControlTestResult:
        """The typed result the metrics engine scores."""
        return ControlTestResult(
            target=ControlTargetData(
                search_name=self.search_name,
                step_id=self.step_id,
                estimated_size=self.estimated_size,
            ),
            positive=self.positive_controls(),
            negative=self.negative_controls(),
        )

    def positive_set(self) -> ControlSetSummary | None:
        """The positive set as the exhibit shows it."""
        positive = self.positive_controls()
        if positive is None:
            return None
        return ControlSetSummary(
            controls_count=positive.controls_count,
            intersection_count=positive.intersection_count,
            recall=positive.recall,
            hit_ids=positive.recovered_ids,
            missed_ids=positive.missed_ids,
        )

    def negative_set(self) -> ControlSetSummary | None:
        """The negative set as the exhibit shows it."""
        negative = self.negative_controls()
        if negative is None:
            return None
        return ControlSetSummary(
            controls_count=negative.controls_count,
            intersection_count=negative.intersection_count,
            false_positive_rate=negative.false_positive_rate,
            hit_ids=negative.admitted_ids,
            missed_ids=negative.excluded_ids,
        )

    def evidence(self, wdk_step_id: int | None) -> ControlTestEvidence | None:
        """The test as the card files it, or None when it was given no control."""
        positive = self.positive_controls()
        negative = self.negative_controls()
        if positive is None and negative is None:
            return None
        return ControlTestEvidence(
            tested_label=self.reader_label(),
            wdk_step_id=wdk_step_id,
            control_set=self.control_set,
            positive=None
            if positive is None
            else ControlSetEvidence(
                returned=positive.recovered_ids, not_returned=positive.missed_ids
            ),
            negative=None
            if negative is None
            else ControlSetEvidence(
                returned=negative.admitted_ids, not_returned=negative.excluded_ids
            ),
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


def _control_scores(counts: _ControlCounts) -> str:
    """What the test recovered and how well it scored.

    Precision and MCC need a negative set. A test that ran none reports
    recall alone, and a test of negatives alone counts what it returned.
    """
    if counts.positive_controls_count is None and counts.negative_controls_count:
        return (
            f"{counts.negative_controls_count} negative controls: "
            f"{counts.negative_intersection or 0} returned"
        )
    metrics = metrics_from_control_result(counts.measured())
    scored = (
        f"precision {metrics.precision:.2f}, MCC {metrics.mcc:.2f}"
        if counts.negative_controls_count is not None
        else "no negative controls tested"
    )
    return (
        f"{counts.positive_intersection or 0} of "
        f"{counts.positive_controls_count or 0} positive controls recovered; "
        f"recall {metrics.sensitivity:.2f}, {scored}"
    )


def controls_summary(counts: _ControlCounts) -> str:
    """What the test recovered, how well it scored, and what a sweep could vary."""
    knobs = (
        f"tunable parameters: {', '.join(counts.tunable_parameters)}"
        if counts.tunable_parameters
        else "no tunable parameters"
    )
    return f"{_control_scores(counts)}; {knobs}"


def control_test_run(
    result: dict[str, JsonValue], *, tool_call_id: str
) -> ControlTestRun | None:
    """The run a finished step test records, or None when it was given no control."""
    counts = _ControlCounts.model_validate(result)
    evidence = counts.evidence(counts.step_id)
    if evidence is None:
        return None
    return ControlTestRun(tool_call_id=tool_call_id, evidence=evidence)


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


_NONE_ATTACHED = (
    "No control set is attached to this conversation; the check states that no "
    "controls were available."
)
_ATTACHED_ONLY = (
    "A control test runs only on a control set attached to this conversation."
)
_SAVED_SETS_ONLY = (
    "A control test runs only against a saved control set; list_control_sets "
    "names them. With none, state that no controls were available."
)


async def _saved_controls(
    ctx: RunContext[AgentDeps], control_set_id: str
) -> SavedControls:
    """The attached set a test names, read under the turn's user and site."""
    deps = ctx.deps
    attached = deps.verification_scope.control_sets
    refused = unattached_set(control_set_id, attached)
    if refused is not None:
        raise ModelRetry(
            _NONE_ATTACHED if not attached else f"{refused} {_ATTACHED_ONLY}"
        )
    try:
        saved = await saved_control_set(
            deps.db_session_factory,
            control_set_id,
            site_id=deps.site_id,
            user_id=deps.user_id,
        )
    except UnknownControlSetError as exc:
        msg = f"{exc.detail} {_SAVED_SETS_ONLY}"
        raise ModelRetry(msg) from None
    if not saved.positive_ids and not saved.negative_ids:
        msg = f"Control set {saved.control_set_id} ({saved.name}) holds no gene id."
        raise ModelRetry(msg)
    return saved


_REPEAT_NOTE = (
    "These ids were already tested on this step under this message. This is "
    "that result; no new task started. Test the whole control set once per "
    "step; a subset adds nothing."
)


def _answered_from_this_message(
    deferred: Callable[..., Awaitable[NoReturn]],
) -> Callable[..., Awaitable[ToolReturn[RepeatedControlTest]]]:
    """Answer a repeat test from the message's record before it defers."""

    @wraps(deferred)
    async def tool(
        ctx: RunContext[AgentDeps],
        wdk_step_id: int,
        control_set_id: str,
    ) -> ToolReturn[RepeatedControlTest]:
        saved = await _saved_controls(ctx, control_set_id)
        held = repeated_control_test(
            ctx.deps.turn_markers,
            wdk_step_id,
            saved.positive_ids,
            saved.negative_ids,
        )
        if held is None:
            return await deferred(
                ctx, wdk_step_id=wdk_step_id, control_set_id=saved.control_set_id
            )
        markers = ctx.deps.turn_markers
        target = ControlTestTarget(
            wdk_step_id=wdk_step_id, control_set_id=saved.control_set_id
        )
        asked = markers.control_tests_asked_again.count(target)
        markers.control_tests_asked_again.append(target)
        if asked:
            msg = (
                f"{saved.name} was tested on step {wdk_step_id} under this message, "
                f"and that result was already given again once. Every step tested "
                f"under this message: {every_step_tested(markers)}. Report these; "
                f"no test runs again."
            )
            # A repeat past the failure spends the tool's retries, so a loop ends.
            raise ToolFailed(msg) if asked == 1 else ModelRetry(msg)
        counts = _ControlCounts.model_validate(held.model_dump())
        return with_summary(
            RepeatedControlTest(note=_REPEAT_NOTE, outcome=held),
            f"Already tested on this step: {_control_scores(counts)}",
            ctx=ctx,
        )

    return tool


CONTROL_TESTS = declare_durable_tool(
    tool_name="run_control_tests_on_step",
    estimated_duration_seconds=180,
    chunks_from_result=_control_test_chunks_from_result,
)


@_answered_from_this_message
@durable_agent_tool(CONTROL_TESTS)
async def run_control_tests_on_step(
    ctx: RunContext[AgentDeps],
    wdk_step_id: int,
    control_set_id: str,
) -> NoReturn:
    """Test a built WDK strategy step against a saved control set.

    A test runs on a control set attached to this conversation and on no
    other; ``list_control_sets`` names them. Durable: the worker runs the test
    and the turn ends while it runs. You are called again with a dict
    matching :class:`ControlOutcome`'s serialised shape. A set this message
    already tested on the step is answered from that test, with no new task.

    For a standalone (not-yet-built) search, use
    ``run_control_tests_on_search`` instead.

    Args:
        ctx: Agent run context.
        wdk_step_id: WDK step ID from a built strategy to test against.
            Read it from get_strategy(summary_only=false): the root step
            carries the WDK step id.
        control_set_id: An attached control set, by the id
            ``list_control_sets`` gives it.
    """
    del ctx, wdk_step_id, control_set_id
    msg = "run_control_tests_on_step runs on the worker via @durable_agent_tool"
    raise NotImplementedError(msg)


async def run_control_tests_on_search(
    ctx: RunContext[AgentDeps],
    target_search_name: str,
    target_parameters: dict[str, ParamValue],
    control_set_id: str,
    record_type: str = "transcript",
) -> ToolReturn[ControlOutcome]:
    """Test a standalone WDK search (not a built strategy) against a saved
    control set.

    A test runs on a control set attached to this conversation and on no
    other; ``list_control_sets`` names them. A temporary WDK strategy intersects
    the search results with the set's gene ids. Use
    ``run_control_tests_on_step`` instead for a built strategy step.

    Args:
        ctx: Agent run context.
        target_search_name: WDK search/question urlSegment to test.
        target_parameters: Target search parameter mapping. Each value MUST be
            wrapped in its typed shape - see the ``valueFormat`` field from
            ``get_search_overview`` for the per-param template.
        control_set_id: An attached control set, by the id
            ``list_control_sets`` gives it.
        record_type: Record type. Defaults to 'transcript'.
    """
    saved = await _saved_controls(ctx, control_set_id)
    measured = await run_positive_negative_controls(
        IntersectionConfig(
            site_id=ctx.deps.site_id,
            record_type=record_type,
            target_search_name=target_search_name,
            target_parameters=dict(target_parameters),
            controls_search_name=CONTROLS_SEARCH,
            controls_param_name=CONTROLS_PARAM,
            controls_value_format="newline",
            internal_strategy_name=CONTROL_TEST_STRATEGY_NAME,
        ),
        positive_controls=saved.positive_ids or None,
        negative_controls=saved.negative_ids or None,
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
            "tunable_parameters": await tunable_parameters_of_search(
                ctx.deps.site_id, record_type, target_search_name
            ),
            "control_set": NamedControlSet(id=saved.control_set_id, name=saved.name),
        }
    )
    tool_call_id = ctx.tool_call_id or ""
    # A search test reads a step it creates and deletes, so no step id is kept.
    evidence = counts.evidence(None)
    if evidence is not None:
        ctx.deps.turn_markers.record_control_tests(
            [ControlTestRun(tool_call_id=tool_call_id, evidence=evidence)]
        )
    return with_summary(
        outcome,
        controls_summary(counts),
        ctx=ctx,
        extra=[control_test_results_event(counts.exhibit(tool_call_id))],
    )
