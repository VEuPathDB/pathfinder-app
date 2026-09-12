"""Standalone strategy graph inspection tools for pydantic-ai migration.

Each function takes ``RunContext[AgentDeps]`` and mirrors the original
:class:`StrategyGraphOps` methods exactly.
"""

import math

from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import Field, JsonValue, ValidationError
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.parameters import to_wire
from veupathdb.domain.strategy import StrategyStep
from veupathdb_mcp import ToolErrorPayload, tool_error
from veupathdb_mcp.catalog import EdaStepRequest

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import ConstraintCheck
from pathfinder.ai.tools.standalone._graph_helpers import serialize_step
from pathfinder.ai.tools.standalone._validation_helpers import (
    get_graph,
    graph_not_found,
    step_not_found,
)
from pathfinder.domain.strategy.build_outcome import citable_count
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.export import exported_thresholds
from pathfinder.services.strategies.schemas import StepResponse

logger = get_logger(__name__)


def _root_count(
    graph: StrategyGraph, sync_state: SyncStateProtocol | None
) -> int | None:
    """The root step's WDK count. Nothing when no single root carries one."""
    if sync_state is None or len(graph.roots) != 1:
        return None
    return citable_count(
        next(iter(graph.roots)),
        counts=sync_state.step_counts,
        refused=sync_state.wdk_push_errors,
    )


class StrategySummaryResponse(CamelModel):
    """Summary metadata for a strategy graph."""

    graph_id: str
    graph_name: str | None = None
    record_type: str | None = None
    wdk_strategy_id: JsonValue = None
    is_built: bool = False
    step_count: int = 0
    description: str | None = None
    steps: list[StepResponse] | None = None
    revision: str = ""
    """Fingerprint of the strategy's inputs; pass to ``apply_operations``.

    Hashes search names, parameters, operators and tree shape only, so a
    refreshed count never looks like an edit. Empty for no strategy.
    """


async def get_strategy(
    ctx: RunContext[AgentDeps],
    graph_id: str | None = None,
    *,
    summary_only: bool = True,
) -> ToolReturn[StrategySummaryResponse | ToolErrorPayload]:
    """Get the current strategy graph -- summary metadata or full step details.

    By default returns a lightweight summary (step count, record type, build status).
    Pass summary_only=false for per-step details including WDK step IDs and estimated
    result counts.
    """
    deps = ctx.deps
    session = deps.strategy_session

    graph = get_graph(session, graph_id)
    if not graph:
        return with_summary(
            graph_not_found(graph_id),
            "No strategy yet",
            ctx=ctx,
            status="empty",
        )

    sync_state = session.sync_state
    wdk_strategy_id = sync_state.wdk_strategy_id if sync_state else None

    steps: list[StepResponse] | None = None
    if not summary_only:
        steps = [
            serialize_step(graph, step, sync_state) for step in graph.steps.values()
        ]

    summary = StrategySummaryResponse(
        graph_id=graph.id,
        graph_name=graph.name,
        record_type=graph.record_type,
        wdk_strategy_id=wdk_strategy_id,
        is_built=wdk_strategy_id is not None,
        step_count=len(graph.steps),
        description=graph.description,
        steps=steps,
        revision=strategy_revision(graph.to_strategy_ast(sync_state=sync_state)),
    )
    if not graph.steps:
        return with_summary(summary, "No strategy yet", ctx=ctx, status="empty")
    genes = _root_count(graph, sync_state)
    if genes is None:
        return with_summary(
            summary,
            f"{len(graph.steps)} steps, count not available",
            ctx=ctx,
            status="warn",
        )
    return with_summary(
        summary,
        f"{len(graph.steps)} steps, {genes:,} genes",
        ctx=ctx,
        status="ok" if genes else "empty",
    )


def _fold_change(effect_size_threshold: float) -> float:
    """A volcano cut as a fold change. Its effect size axis is log2."""
    return 2**effect_size_threshold


class StudyStepCheck(CamelModel):
    """A study step's volcano cut, and how it answers what was asked."""

    step_id: str
    search_name: str | None = None
    dataset_id: str
    record_count: int | None = None
    thresholds: VolcanoThresholds | None = None
    checks: list[ConstraintCheck] = Field(default_factory=list)

    @computed
    def fold_change_threshold(self) -> float | None:
        if self.thresholds is None:
            return None
        return _fold_change(self.thresholds.effect_size_threshold)


def _number(value: float) -> str:
    return f"{value:g}"


def _constraint_check(
    label: str, requested: float | None, realized: float
) -> ConstraintCheck | None:
    if requested is None:
        return None
    return ConstraintCheck(
        label=label,
        requested=_number(requested),
        realized=_number(realized),
        honored=math.isclose(requested, realized, rel_tol=1e-9),
    )


def _threshold_checks(
    thresholds: VolcanoThresholds,
    *,
    requested_fold_change: float | None,
    requested_significance: float | None,
) -> list[ConstraintCheck]:
    found = (
        _constraint_check(
            "fold change",
            requested_fold_change,
            _fold_change(thresholds.effect_size_threshold),
        ),
        _constraint_check(
            "significance",
            requested_significance,
            thresholds.significance_threshold,
        ),
    )
    return [check for check in found if check is not None]


def _study_step_request(step: StrategyStep) -> EdaStepRequest | None:
    """The two EDA parameters the step carries, or None when it carries none."""
    try:
        return EdaStepRequest.model_validate(
            {name: to_wire(value) for name, value in step.parameters.items()},
        )
    except ValidationError:
        return None


def check_study_step(
    ctx: RunContext[AgentDeps],
    step_id: str,
    requested_fold_change: float | None = None,
    requested_significance: float | None = None,
) -> ToolReturn[StudyStepCheck | ToolErrorPayload]:
    """Read a study step's thresholds and compare them with what was asked.

    A study step exports an EDA analysis, so the cut it was built with lives in
    its ``eda_analysis_spec`` parameter rather than in a plain search
    parameter. This reads that cut and the step's record count, so a study step
    is verified by its own numbers instead of reported as unverified.

    Pass ``requested_fold_change`` as a fold change (2 for "at least
    2-fold") and ``requested_significance`` as the p-value the user asked for.
    Each one you pass comes back as a ``constraint_report`` entry you copy into
    the digest.

    Args:
        step_id: The strategy step to read.
        requested_fold_change: The fold change the user asked for.
        requested_significance: The p-value cut the user asked for.
    """
    session = ctx.deps.strategy_session
    graph = get_graph(session, None)
    if graph is None:
        return with_summary(
            graph_not_found(None),
            "No strategy yet",
            ctx=ctx,
            status="empty",
        )
    step = graph.get_step(step_id)
    if step is None:
        return with_summary(
            step_not_found(step_id),
            f"No step {step_id}",
            ctx=ctx,
            status="warn",
        )
    request = _study_step_request(step)
    if request is None:
        return with_summary(
            tool_error(
                ErrorCode.VALIDATION_ERROR,
                f"Step {step_id} carries no readable EDA analysis, so it is "
                f"not a study step. Read its parameters with get_strategy.",
                stepId=step_id,
            ),
            f"Step {step_id} is not a study step",
            ctx=ctx,
            status="warn",
        )
    sync_state = session.sync_state
    count = sync_state.step_counts.get(step_id) if sync_state else None
    thresholds = exported_thresholds(request)
    check = StudyStepCheck(
        step_id=step_id,
        search_name=step.search_name,
        dataset_id=request.eda_dataset_id,
        record_count=count,
        thresholds=thresholds,
        checks=(
            []
            if thresholds is None
            else _threshold_checks(
                thresholds,
                requested_fold_change=requested_fold_change,
                requested_significance=requested_significance,
            )
        ),
    )
    return with_summary(
        check,
        _study_step_summary(check),
        ctx=ctx,
        status="ok" if count else "empty",
    )


def _study_step_summary(check: StudyStepCheck) -> str:
    records = "unknown" if check.record_count is None else f"{check.record_count:,}"
    if check.thresholds is None:
        return f"{records} records, whole subset"
    fold = _number(_fold_change(check.thresholds.effect_size_threshold))
    significance = _number(check.thresholds.significance_threshold)
    return f"{records} records at {fold}-fold and p {significance}"
