"""Standalone strategy graph inspection tools for pydantic-ai migration.

Each function takes ``RunContext[AgentDeps]`` and mirrors the original
:class:`StrategyGraphOps` methods exactly.
"""

import math

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import Field, JsonValue
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp import ToolErrorPayload, tool_error
from veupathdb_mcp.catalog import EdaStepRequest

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import ConstraintCheck
from pathfinder.ai.tools.standalone._validation_helpers import (
    get_graph,
    graph_not_found,
    step_not_found,
)
from pathfinder.ai.tools.standalone.graph_helpers import (
    count_summary,
    serialize_step,
)
from pathfinder.domain.eda_parts import EdaComparison, EdaEffectDirection
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.build_outcome import citable_count
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph, strategy_root_id
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.eda.analysis_kinds import (
    read_the_unread_kinds,
    unread_analyses,
)
from pathfinder.services.eda.catalog import (
    UnknownEdaDatasetError,
    get_study_detail_for_dataset,
)
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.description import display_names, filter_summaries
from pathfinder.services.eda.direction import direction_sentence
from pathfinder.services.eda.export import (
    exported_analysis,
    exported_subset,
    study_step_request,
)
from pathfinder.services.strategies.schemas import StepResponse

logger = get_logger(__name__)


def _root_count(
    graph: StrategyGraph, sync_state: SyncStateProtocol | None
) -> int | None:
    """The strategy root's WDK count, or nothing when it carries none."""
    root_id = strategy_root_id(graph, sync_state)
    if sync_state is None or root_id is None:
        return None
    return citable_count(
        root_id,
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
    # What each study step selects, by step id, read from its analysis document.
    analyses: dict[str, str] = Field(default_factory=dict)
    # The study steps whose analysis the site did not describe: pending checks.
    unread_analyses: list[str] = Field(default_factory=list)


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
    await read_the_unread_kinds(site_id=deps.site_id, graph=graph)

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
        analyses={
            step_id: binding.words
            for step_id, step in graph.steps.items()
            if (
                binding := exported_analysis(
                    graph.analysis_kind_of(step_id), step.parameters
                )
            )
            is not None
        },
        unread_analyses=unread_analyses(graph),
    )
    if not graph.steps:
        return with_summary(summary, "No strategy yet", ctx=ctx, status="empty")
    line, status = count_summary(
        len(graph.steps), _root_count(graph, sync_state), graph.record_type
    )
    return with_summary(summary, line, ctx=ctx, status=status)


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
    # The groups a compute step compares, its method, and the side it keeps.
    comparison: EdaComparison | None = None
    method: str | None = None
    effect_direction: EdaEffectDirection | None = None
    # One sentence per subset filter the step carries, in the sheet's words.
    subset_filters: list[str] = Field(default_factory=list)
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


async def _subset_filters(site_id: str, request: EdaStepRequest) -> list[str]:
    """The sentences a study step's own subset filters read as.

    The study is read for the names the researcher knows the variables by, so
    a step that carries no filter needs no read. A study this account cannot
    reach costs the sentences those names and nothing else.
    """
    filters = exported_subset(request)
    if not filters:
        return []
    try:
        _entry, study = await get_study_detail_for_dataset(
            site_id, request.eda_dataset_id
        )
    except UnknownEdaDatasetError:
        return filter_summaries(filters, display_names={})
    return filter_summaries(filters, display_names=display_names(study))


async def check_study_step(
    ctx: RunContext[AgentDeps],
    step_id: str,
    requested_fold_change: float | None = None,
    requested_significance: float | None = None,
) -> ToolReturn[StudyStepCheck | ToolErrorPayload]:
    """Read the cut a study step was built with and compare it with the request.

    A study step exports an EDA analysis, so the cut it was built with lives in
    its ``eda_analysis_spec`` parameter rather than in a plain search
    parameter. This reads that cut and the step's record count, so a study step
    is verified by its own numbers instead of reported as unverified. A subset
    step states its cut as ``subset_filters``, one sentence per filter; a
    compute step states it as volcano thresholds.

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
    request = study_step_request(step.parameters)
    if request is not None:
        await read_the_unread_kinds(site_id=ctx.deps.site_id, graph=graph)
    kind = graph.analysis_kind_of(step_id)
    if request is not None and kind is None:
        return with_summary(
            tool_error(
                ErrorCode.VALIDATION_ERROR,
                f"Step {step_id} carries an EDA analysis, and the site did not "
                f"say which plugin reads it, so its cut cannot be read now. It "
                f"is read again on the next turn: set success from the other "
                f"checks and name this step in caveats as a pending check.",
                stepId=step_id,
            ),
            f"The site did not say how step {step_id} reads its analysis",
            ctx=ctx,
            status="warn",
        )
    binding = exported_analysis(kind, step.parameters)
    if request is None or binding is None:
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
    thresholds = _cut(binding)
    subset_filters = await _subset_filters(ctx.deps.site_id, request)
    check = StudyStepCheck(
        step_id=step_id,
        search_name=step.search_name,
        dataset_id=request.eda_dataset_id,
        record_count=count,
        thresholds=thresholds,
        comparison=binding.comparison,
        method=binding.method,
        effect_direction=binding.effect_direction,
        subset_filters=subset_filters,
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


def _cut(binding: AnalysisBinding) -> VolcanoThresholds | None:
    """The volcano cut a compute step's binding states, or None for a subset."""
    if (
        binding.effect_size_threshold is None
        or binding.significance_threshold is None
        or binding.effect_direction is None
    ):
        return None
    return VolcanoThresholds(
        effect_size_threshold=binding.effect_size_threshold,
        significance_threshold=binding.significance_threshold,
        effect_direction=binding.effect_direction,
    )


def _compared(check: StudyStepCheck) -> str:
    """The method and the genes the compute keeps, or nothing for a subset."""
    if check.comparison is None or check.effect_direction is None:
        return ""
    kept = direction_sentence(check.comparison, check.effect_direction)
    return f", {check.method}: {kept[0].lower()}{kept[1:]}"


def _study_step_summary(check: StudyStepCheck) -> str:
    records = "unknown" if check.record_count is None else f"{check.record_count:,}"
    filters = (
        ""
        if not check.subset_filters
        else count_noun(len(check.subset_filters), "filter")
    )
    if check.thresholds is not None:
        fold = _number(_fold_change(check.thresholds.effect_size_threshold))
        significance = _number(check.thresholds.significance_threshold)
        cut = f"{records} records at {fold}-fold and p {significance}{_compared(check)}"
        return cut if not filters else f"{cut}, {filters}"
    if not filters:
        return f"{records} records, whole subset"
    return f"{records} records, {filters}: {check.subset_filters[0]}"
