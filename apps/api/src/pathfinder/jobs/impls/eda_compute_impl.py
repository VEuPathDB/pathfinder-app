"""Worker-side impl for ``run_eda_compute``.

The impl drives the compute to a terminal state and returns its statistics
summary. It creates no step: a worker context has no strategy session, and the
agent creates the step after the resume, when the job's cache is warm.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from assistant_core.conversation.event_writer import append_chunk
from assistant_core.memory.store import MemoryStore
from assistant_core.tasks.progress import TaskProgressEmitter
from veupathdb.domain import validate_compute_config
from veupathdb.eda import (
    EdaAnalysisDetail,
    EdaComputation,
    EdaComputeJob,
    EdaDifferentialExpressionComputation,
    EdaDifferentialExpressionConfig,
    EdaDifferentialExpressionDescriptor,
    EdaFilter,
    EdaPermissionEntry,
    EdaStudyDetail,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
    VolcanoStatsResponse,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.tools.standalone.eda_stream_parts import (
    eda_analysis_state_chunk,
    eda_viz_chunk,
)
from pathfinder.domain.eda_parts import (
    EdaComparison,
    EdaEffectDirection,
    EdaVolcanoPoint,
)
from pathfinder.persistence.models import ConversationAnalysisView
from pathfinder.services.eda.binding import (
    analysis_state,
    bound_conversation_analysis,
    bump_analysis_revision,
    read_analysis,
)
from pathfinder.services.eda.catalog import get_study_detail_for_dataset
from pathfinder.services.eda.comparison import apply_computation
from pathfinder.services.eda.compute import (
    RUNNING_STATUSES,
    RetainedSummary,
    VolcanoThresholds,
    comparison_of,
    lookup_job,
    poll_job,
    read_statistics,
    retained_summary,
    submit_compute,
    volcano_view,
)
from pathfinder.services.eda.description import (
    permission_facts,
)
from pathfinder.services.eda.direction import sign_sentence

_COMPUTE_NAME = "differentialexpression"
_POLL_SECONDS = 3.0
_MAX_POLLS = 200

# The thresholds the review card defaults to upstream.
_DEFAULT_EFFECT_SIZE = 1.0
_DEFAULT_SIGNIFICANCE = 0.05
_DEFAULT_DIRECTION: EdaEffectDirection = "upAndDown"

# A queued job has no position most of the time, so the percent is a floor
# rather than a measurement: the poll count moves it, never past the ceiling.
_QUEUED_PERCENT = 0.1
_RUNNING_CEILING = 0.85


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


def _computation(
    job_id: str,
    config: EdaDifferentialExpressionConfig,
) -> EdaDifferentialExpressionComputation:
    """The comparison the analysis carries, with the volcano the step reads."""
    descriptor = EdaDifferentialExpressionDescriptor(configuration=config)
    computation = EdaComputation(
        computation_id=job_id,
        descriptor=descriptor,
        visualizations=[
            EdaVisualization(
                visualization_id=job_id,
                descriptor=EdaVolcanoDescriptor(
                    configuration=EdaVolcanoConfiguration(
                        effect_size_threshold=_DEFAULT_EFFECT_SIZE,
                        significance_threshold=_DEFAULT_SIGNIFICANCE,
                    ),
                ),
            ),
        ],
    )
    return EdaDifferentialExpressionComputation(
        computation=computation, descriptor=descriptor
    )


async def _announce_analysis(
    *,
    conversation_id: UUID,
    binding: ConversationAnalysisView,
    entry: EdaPermissionEntry,
    study: EdaStudyDetail,
    analysis: EdaAnalysisDetail,
) -> None:
    """Put the mutated analysis on the thread, under a fresh revision."""
    revision = await bump_analysis_revision(conversation_id=conversation_id)
    chunk = eda_analysis_state_chunk(
        await analysis_state(
            site_id=binding.site_id,
            dataset_id=binding.dataset_id,
            entry=permission_facts(entry),
            study=study,
            analysis=analysis,
            revision=revision,
        )
    )
    await append_chunk(
        conversation_id=conversation_id,
        chunk=chunk.model_dump(by_alias=True, mode="json", exclude_none=True),
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
    view = volcano_view(
        statistics,
        thresholds=VolcanoThresholds(
            effect_size_threshold=_DEFAULT_EFFECT_SIZE,
            significance_threshold=_DEFAULT_SIGNIFICANCE,
            effect_direction=_DEFAULT_DIRECTION,
        ),
    )
    chunk = eda_viz_chunk(
        dataset_id=binding.dataset_id,
        analysis_id=binding.analysis_id,
        effect_size_label=statistics.effect_size_label,
        effect_size_threshold=_DEFAULT_EFFECT_SIZE,
        significance_threshold=_DEFAULT_SIGNIFICANCE,
        effect_direction=_DEFAULT_DIRECTION,
        summary=summary,
        points=[
            EdaVolcanoPoint.model_validate(point, from_attributes=True)
            for point in view.points
        ],
        comparison=comparison_of(config),
        caption=caption,
    )
    await append_chunk(
        conversation_id=conversation_id,
        chunk=chunk.model_dump(by_alias=True, mode="json", exclude_none=True),
    )


def _submit_message(job: EdaComputeJob) -> str:
    if job.status != "queued":
        return "Starting the compute"
    if job.queue_position is None:
        return "The job is queued"
    return f"The job is queued at position {job.queue_position}"


def _running_message(job: EdaComputeJob) -> str:
    if job.status == "queued":
        return _submit_message(job)
    return "The compute is running"


def _running_percent(polls: int) -> float:
    return _QUEUED_PERCENT + (_RUNNING_CEILING - _QUEUED_PERCENT) * polls / _MAX_POLLS


async def _settled(
    site_id: str,
    *,
    study_id: str,
    config: EdaDifferentialExpressionConfig,
    filters: list[EdaFilter],
    progress: TaskProgressEmitter,
) -> EdaComputeJob:
    """The job for this configuration, driven to a terminal status."""
    await progress.update(percent=0.0, message="Checking for a cached result")
    job = await lookup_job(
        site_id,
        compute_name=_COMPUTE_NAME,
        study_id=study_id,
        config=config,
        filters=filters,
    )
    if job.status == "complete":
        return job
    await progress.update(percent=_QUEUED_PERCENT, message=_submit_message(job))
    job = await submit_compute(
        site_id,
        compute_name=_COMPUTE_NAME,
        study_id=study_id,
        config=config,
        filters=filters,
    )
    polls = 0
    while job.status in RUNNING_STATUSES and polls < _MAX_POLLS:
        await progress.update(
            percent=_running_percent(polls),
            message=_running_message(job),
        )
        await asyncio.sleep(_POLL_SECONDS)
        job = await poll_job(site_id, job_id=job.job_id)
        polls += 1
    return job


def _refuse(job: EdaComputeJob) -> RuntimeError:
    match job.status:
        case "failed":
            meaning = "the configuration is wrong for this study"
        case "expired":
            meaning = "the result is gone and the job needs a resubmit"
        case "no-such-job":
            meaning = "the inputs changed, so no job addresses them"
        case _:
            meaning = f"the job did not settle in {_MAX_POLLS} polls"
    return RuntimeError(
        f"The differential-expression job {job.job_id} is {job.status}: {meaning}.",
    )


def compute_result(
    *,
    job_id: str,
    status: str,
    method: str,
    effect_size_label: str,
    summary: RetainedSummary,
    comparison: EdaComparison,
) -> dict[str, Any]:
    """The summary the agent resumes with, each side named by its group."""
    higher_in_b = ", ".join(comparison.group_b)
    higher_in_a = ", ".join(comparison.group_a)
    return {
        "jobId": job_id,
        "status": status,
        "computeName": _COMPUTE_NAME,
        "method": method,
        "effectSizeLabel": effect_size_label,
        "genesTested": summary.total_rows,
        "genesUnreadable": summary.unparseable_rows,
        "effectSizeThreshold": _DEFAULT_EFFECT_SIZE,
        "significanceThreshold": _DEFAULT_SIGNIFICANCE,
        "retained": summary.retained,
        "retainedUp": summary.retained_up,
        "retainedDown": summary.retained_down,
        "comparison": comparison.model_dump(by_alias=True, mode="json"),
        "signRule": sign_sentence(comparison),
        "guidance": (
            f"{summary.retained} of {summary.total_rows} genes pass an effect "
            f"size of {_DEFAULT_EFFECT_SIZE} and a p-value of "
            f"{_DEFAULT_SIGNIFICANCE}: {summary.retained_up} higher in "
            f"{higher_in_b} and {summary.retained_down} higher in {higher_in_a}. "
            f"upOnly keeps the {summary.retained_up}, downOnly the "
            f"{summary.retained_down}. Call create_eda_step with those "
            f"thresholds to export them, or with different ones to change the "
            f"cut."
        ),
    }


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
    binding = await bound_conversation_analysis(conversation_id=conversation_id)
    if binding is None:
        msg = (
            "This thread has no open EDA analysis, so there is nothing to "
            "compute on. Call open_eda_analysis first."
        )
        raise ValueError(msg)

    config = _config(
        identifier_variable=identifier_variable,
        value_variable=value_variable,
        comparator_variable=comparator_variable,
        group_a_labels=group_a_labels,
        group_b_labels=group_b_labels,
        method=method,
    )
    entry, study = await get_study_detail_for_dataset(
        binding.site_id,
        binding.dataset_id,
    )
    errors = validate_compute_config(study, config)
    if errors:
        raise ValueError(" ".join(errors))

    # The job id hashes the filters, so the compute runs on the subset the
    # analysis holds and the step's later read addresses the same job.
    analysis = await read_analysis(binding.site_id, analysis_id=binding.analysis_id)
    filters = list(analysis.descriptor.subset.descriptor)

    job = await _settled(
        binding.site_id,
        study_id=entry.study_id,
        config=config,
        filters=filters,
        progress=progress,
    )
    if job.status != "complete":
        raise _refuse(job)

    await progress.update(percent=0.9, message="Reading the statistics")
    statistics = await read_statistics(
        binding.site_id,
        compute_name=_COMPUTE_NAME,
        study_id=entry.study_id,
        config=config,
        filters=filters,
    )
    summary = retained_summary(
        statistics,
        effect_size_threshold=_DEFAULT_EFFECT_SIZE,
        significance_threshold=_DEFAULT_SIGNIFICANCE,
    )
    updated = await apply_computation(
        binding.site_id,
        analysis_id=binding.analysis_id,
        dataset_id=binding.dataset_id,
        computation=_computation(job.job_id, config),
    )
    await _announce_analysis(
        conversation_id=conversation_id,
        binding=binding,
        entry=entry,
        study=study,
        analysis=updated,
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
    )
