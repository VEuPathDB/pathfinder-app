"""The check that reads a study step's cut and compares it with the request."""

import math
from collections.abc import Callable

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.eda import EdaForbiddenError, EdaServerError
from veupathdb_mcp import ToolErrorPayload, tool_error

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._validation_helpers import (
    get_graph,
    graph_not_found,
    step_not_found,
)
from pathfinder.domain.constraint_check import ConstraintCheck, agrees
from pathfinder.domain.eda_parts import EdaComparison, EdaEffectDirection
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.eda.analysis_kinds import (
    read_the_unread_kinds,
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
    # The measurement the compute ran on, by the study's name for it.
    value_variable: str | None = None
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


def _same(value: float) -> float:
    return value


def _constraint_check(
    step_id: str,
    label: str,
    requested: float | None,
    bound: float,
    *,
    to_bound: Callable[[float], float] = _same,
    to_requested: Callable[[float], float] = _same,
) -> ConstraintCheck | None:
    if requested is None:
        return None
    return ConstraintCheck(
        step_id=step_id,
        label=label,
        requested=_number(requested),
        realized=_number(to_requested(bound)),
        honored=agrees(requested, bound, to_bound=to_bound, to_requested=to_requested),
    )


def _threshold_checks(
    step_id: str,
    thresholds: VolcanoThresholds,
    *,
    requested_fold_change: float | None,
    requested_significance: float | None,
) -> list[ConstraintCheck]:
    found = (
        _constraint_check(
            step_id,
            "fold change",
            requested_fold_change,
            thresholds.effect_size_threshold,
            to_bound=math.log2,
            to_requested=_fold_change,
        ),
        _constraint_check(
            step_id,
            "significance",
            requested_significance,
            thresholds.significance_threshold,
        ),
    )
    return [check for check in found if check is not None]


async def _variable_names(site_id: str, dataset_id: str) -> dict[tuple[str, str], str]:
    """The names the researcher knows a study's variables by.

    A study the check cannot read now names none, so each variable reads as its
    id. The step's own document still states what ran.
    """
    try:
        _entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    except UnknownEdaDatasetError, EdaForbiddenError, EdaServerError:
        return {}
    return display_names(study)


def _measured(
    binding: AnalysisBinding, names: dict[tuple[str, str], str]
) -> str | None:
    """The study's name for the variable the compute ran on, else its id."""
    if binding.value_variable is None:
        return None
    key = (binding.value_entity_id or "", binding.value_variable)
    return names.get(key, binding.value_variable)


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
    compute step states it as volcano thresholds, and ``value_variable`` names
    the measurement the compute ran on, such as a sense or an antisense count.

    Pass ``requested_fold_change`` as a fold change (2 for "at least
    2-fold") and ``requested_significance`` as the p-value the user asked for.
    Each one you pass comes back in ``checks``, compared at the decimals each
    value is written with; the runtime records them as the digest's report.

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
    filters = exported_subset(request)
    names = (
        await _variable_names(ctx.deps.site_id, request.eda_dataset_id)
        if filters or binding.value_variable is not None
        else {}
    )
    check = StudyStepCheck(
        step_id=step_id,
        search_name=step.search_name,
        dataset_id=request.eda_dataset_id,
        record_count=count,
        thresholds=thresholds,
        comparison=binding.comparison,
        method=binding.method,
        value_variable=_measured(binding, names),
        effect_direction=binding.effect_direction,
        subset_filters=filter_summaries(filters, display_names=names),
        checks=(
            []
            if thresholds is None
            else _threshold_checks(
                step_id,
                thresholds,
                requested_fold_change=requested_fold_change,
                requested_significance=requested_significance,
            )
        ),
    )
    ctx.deps.turn_markers.study_checks[step_id] = check.checks
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
    measured = "" if check.value_variable is None else f" on {check.value_variable}"
    return f", {check.method}{measured}: {kept[0].lower()}{kept[1:]}"


def _not_met(check: StudyStepCheck) -> str:
    """Each requested value the step was not built at, first, so the capped
    summary line keeps it."""
    unmet = [c for c in check.checks if not c.honored]
    if not unmet:
        return ""
    asked = "; ".join(c.shortfall() for c in unmet)
    return f"Not met: {asked}. "


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
        cut = cut if not filters else f"{cut}, {filters}"
        return _not_met(check) + cut
    if not filters:
        return f"{records} records, whole subset"
    return f"{records} records, {filters}: {check.subset_filters[0]}"
