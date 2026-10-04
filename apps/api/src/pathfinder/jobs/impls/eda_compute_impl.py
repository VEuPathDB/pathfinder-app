"""Worker-side impl for ``run_eda_compute``.

The impl drives the compute to a terminal state and returns its statistics
summary. It creates no step: a worker context has no strategy session, and the
agent creates the step after the resume, when the job's cache is warm.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from assistant_core.memory.store import MemoryStore
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.tasks.progress import TaskProgressEmitter
from veupathdb.domain import validate_compute_config
from veupathdb.eda import (
    EdaComputation,
    EdaDifferentialExpressionComputation,
    EdaDifferentialExpressionConfig,
    EdaDifferentialExpressionDescriptor,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
    VolcanoStatsResponse,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.tools.standalone.eda_stream_parts import eda_viz_chunk
from pathfinder.domain.eda_parts import (
    EdaComparison,
    EdaVolcanoPoint,
)
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.jobs.impls.eda_thread_io import (
    announce_analysis,
    append_part,
    bound_study,
)
from pathfinder.services.eda.comparison import apply_computation
from pathfinder.services.eda.compute import (
    DEFAULT_VOLCANO_CUT,
    RetainedSummary,
    comparison_of,
    read_statistics,
    retained_summary,
    volcano_view,
)
from pathfinder.services.eda.compute_jobs import refusal_of, settled_job
from pathfinder.services.eda.direction import sign_sentence

_COMPUTE_NAME = "differentialexpression"


def _config(
    *,
    identifier_variable: dict[str, str],
    value_variable: dict[str, str],
    comparator_variable: dict[str, str],
    group_a_labels: list[str],
    group_b_labels: list[str],
    method: str,
) -> EdaDifferentialExpressionConfig:
    """The compute's configuration, through the model that refuses a bad one."""
    return EdaDifferentialExpressionConfig.model_validate(
        {
            "identifier_variable": identifier_variable,
            "value_variable": value_variable,
            "comparator": {
                "variable": comparator_variable,
                "group_a": [{"label": label} for label in group_a_labels],
                "group_b": [{"label": label} for label in group_b_labels],
            },
            "differential_expression_method": method,
        },
    )


def compared_computation(
    job_id: str,
    config: EdaDifferentialExpressionConfig,
    *,
    effect_size_label: str,
) -> EdaDifferentialExpressionComputation:
    """The comparison the analysis carries, with the volcano the step reads.

    The volcano stores the label of the compute's effect size, so a step keeps its unit.
    """
    descriptor = EdaDifferentialExpressionDescriptor(configuration=config)
    computation = EdaComputation(
        computation_id=job_id,
        descriptor=descriptor,
        visualizations=[
            EdaVisualization(
                visualization_id=job_id,
                descriptor=EdaVolcanoDescriptor(
                    configuration=EdaVolcanoConfiguration(
                        effect_size_threshold=DEFAULT_VOLCANO_CUT.effect_size_threshold,
                        significance_threshold=DEFAULT_VOLCANO_CUT.significance_threshold,
                        effect_size_label=effect_size_label,
                    ),
                ),
            ),
        ],
    )
    return EdaDifferentialExpressionComputation(
        computation=computation, descriptor=descriptor
    )


async def _announce_volcano(
    *,
    conversation_id: UUID,
    binding: ConversationAnalysisView,
    statistics: VolcanoStatsResponse,
    config: EdaDifferentialExpressionConfig,
    summary: RetainedSummary,
    caption: str,
) -> None:
    """Put the plot of the default cut on the thread, beside the state."""
    view = volcano_view(statistics, thresholds=DEFAULT_VOLCANO_CUT)
    chunk = eda_viz_chunk(
        dataset_id=binding.dataset_id,
        analysis_id=binding.analysis_id,
        effect_size_label=statistics.effect_size_label,
        effect_size_threshold=DEFAULT_VOLCANO_CUT.effect_size_threshold,
        significance_threshold=DEFAULT_VOLCANO_CUT.significance_threshold,
        effect_direction=DEFAULT_VOLCANO_CUT.effect_direction,
        summary=summary,
        points=[
            EdaVolcanoPoint.model_validate(point, from_attributes=True)
            for point in view.points
        ],
        retained_point_ids=view.retained_point_ids,
        comparison=comparison_of(config),
        caption=caption,
    )
    await append_part(conversation_id=conversation_id, chunk=chunk)


class EdaComputeResult(CamelModel):
    """The summary the agent resumes with, counted at the default cut."""

    job_id: str
    status: str
    compute_name: str
    method: str
    effect_size_label: str
    genes_tested: int
    genes_unreadable: int
    effect_size_threshold: float
    significance_threshold: float
    retained: int
    retained_up: int
    retained_down: int
    comparison: EdaComparison
    sign_rule: str
    guidance: str


def compute_result(
    *,
    job_id: str,
    status: str,
    method: str,
    effect_size_label: str,
    summary: RetainedSummary,
    comparison: EdaComparison,
) -> EdaComputeResult:
    """The summary the agent resumes with, each side named by its group."""
    cut = DEFAULT_VOLCANO_CUT
    higher_in_b = ", ".join(comparison.group_b)
    higher_in_a = ", ".join(comparison.group_a)
    return EdaComputeResult(
        job_id=job_id,
        status=status,
        compute_name=_COMPUTE_NAME,
        method=method,
        effect_size_label=effect_size_label,
        genes_tested=summary.total_rows,
        genes_unreadable=summary.unparseable_rows,
        effect_size_threshold=cut.effect_size_threshold,
        significance_threshold=cut.significance_threshold,
        retained=summary.retained,
        retained_up=summary.retained_up,
        retained_down=summary.retained_down,
        comparison=comparison,
        sign_rule=sign_sentence(comparison),
        guidance=(
            f"{summary.retained} of {summary.total_rows} genes pass an effect "
            f"size of {cut.effect_size_threshold} and a p-value of "
            f"{cut.significance_threshold}: {summary.retained_up} higher in "
            f"{higher_in_b} and {summary.retained_down} higher in {higher_in_a}. "
            f"upOnly keeps the {summary.retained_up}, downOnly the "
            f"{summary.retained_down}. Call create_eda_step with those "
            f"thresholds to export them, or with different ones to change the "
            f"cut."
        ),
    )


async def run_eda_compute_impl(
    *,
    context: Context,
    task_id: UUID,
    conversation_id: UUID,
    progress: TaskProgressEmitter,
    memory_store: MemoryStore | None,
    identifier_variable: dict[str, str],
    value_variable: dict[str, str],
    comparator_variable: dict[str, str],
    group_a_labels: list[str],
    group_b_labels: list[str],
    method: str = "DESeq",
    caption: str = "",
    **_extra: Any,
) -> dict[str, Any]:
    """Drive one differential-expression job and summarise its statistics."""
    del context, task_id, memory_store
    bound = await bound_study(conversation_id=conversation_id)
    binding = bound.binding
    config = _config(
        identifier_variable=identifier_variable,
        value_variable=value_variable,
        comparator_variable=comparator_variable,
        group_a_labels=group_a_labels,
        group_b_labels=group_b_labels,
        method=method,
    )
    errors = validate_compute_config(bound.study, config)
    if errors:
        raise ValueError(" ".join(errors))

    job = await settled_job(
        binding.site_id,
        compute_name=_COMPUTE_NAME,
        study_id=bound.entry.study_id,
        config=config,
        filters=bound.filters,
        progress=progress,
    )
    if job.status != "complete":
        raise refusal_of(job, job_name="differential-expression")

    await progress.update(percent=0.9, message="Reading the statistics")
    statistics = await read_statistics(
        binding.site_id,
        compute_name=_COMPUTE_NAME,
        study_id=bound.entry.study_id,
        config=config,
        filters=bound.filters,
    )
    summary = retained_summary(
        statistics,
        effect_size_threshold=DEFAULT_VOLCANO_CUT.effect_size_threshold,
        significance_threshold=DEFAULT_VOLCANO_CUT.significance_threshold,
    )
    updated = await apply_computation(
        binding.site_id,
        analysis_id=binding.analysis_id,
        dataset_id=binding.dataset_id,
        computation=compared_computation(
            job.job_id, config, effect_size_label=statistics.effect_size_label
        ),
    )
    await announce_analysis(
        conversation_id=conversation_id, bound=bound, analysis=updated
    )
    await _announce_volcano(
        conversation_id=conversation_id,
        binding=binding,
        statistics=statistics,
        config=config,
        summary=summary,
        caption=caption,
    )
    await progress.update(percent=1.0, message="Compute complete")
    return compute_result(
        job_id=job.job_id,
        status=job.status,
        method=method,
        effect_size_label=statistics.effect_size_label,
        summary=summary,
        comparison=comparison_of(config),
    ).model_dump(by_alias=True, mode="json")
