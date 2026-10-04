"""Worker-side impl for ``run_eda_dimensionality_reduction``.

The impl drives the reduction to a terminal state, reads the samples on its
first two components, keeps the computation on the analysis and returns the
statistic the Lead resumes with.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from assistant_core.memory.store import MemoryStore
from assistant_core.tasks.progress import TaskProgressEmitter
from veupathdb.eda import EdaDimensionalityReductionConfig, EdaVariableSpec

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.tools.standalone.eda_statistics import EdaStatisticResult
from pathfinder.ai.tools.standalone.eda_stream_parts import eda_pca_chunk
from pathfinder.domain.eda_parts import EdaPcaPart
from pathfinder.domain.statistic_facts import pca_fact, statistic_id
from pathfinder.jobs.impls.eda_thread_io import (
    announce_analysis,
    append_part,
    bound_study,
)
from pathfinder.services.eda.compute_jobs import refusal_of, settled_job
from pathfinder.services.eda.reduction import (
    REDUCTION,
    apply_reduction,
    pca_axes,
    pca_series,
    read_components,
    read_samples,
    reduction_computation,
    reduction_errors,
)


async def run_eda_dimensionality_reduction_impl(
    *,
    context: Context,
    task_id: UUID,
    conversation_id: UUID,
    progress: TaskProgressEmitter,
    memory_store: MemoryStore | None,
    identifier_variable: dict[str, str],
    value_variable: dict[str, str],
    data_format: str = "normalizedValues",
    color_by_variable: dict[str, str] | None = None,
    caption: str = "",
    **_extra: Any,
) -> dict[str, Any]:
    """Drive one reduction job and place the samples on its components."""
    del context, task_id, memory_store
    bound = await bound_study(conversation_id=conversation_id)
    config = EdaDimensionalityReductionConfig.model_validate(
        {
            "identifier_variable": identifier_variable,
            "value_variable": value_variable,
            "data_format": data_format,
        }
    )
    color_by = (
        None
        if color_by_variable is None
        else EdaVariableSpec.model_validate(color_by_variable)
    )
    errors = reduction_errors(bound.study, config, color_by)
    if errors:
        raise ValueError(" ".join(errors))

    site_id, study_id = bound.binding.site_id, bound.entry.study_id
    job = await settled_job(
        site_id,
        compute_name=REDUCTION,
        study_id=study_id,
        config=config,
        filters=bound.filters,
        progress=progress,
    )
    if job.status != "complete":
        raise refusal_of(job, job_name="dimensionality-reduction")

    await progress.update(percent=0.9, message="Reading the components")
    components = await read_components(
        site_id, study_id=study_id, config=config, filters=bound.filters
    )
    samples = await read_samples(
        site_id,
        study_id=study_id,
        config=config,
        filters=bound.filters,
        components=components,
        color_by=color_by,
    )
    updated = await apply_reduction(
        site_id,
        analysis_id=bound.binding.analysis_id,
        computation=reduction_computation(job.job_id, config, color_by),
    )
    part = EdaPcaPart(
        statistic_id=statistic_id(
            "pca",
            [
                f"{spec.entity_id}.{spec.variable_id}"
                for spec in (
                    config.value_variable,
                    *([] if color_by is None else [color_by]),
                )
            ],
        ),
        dataset_id=bound.binding.dataset_id,
        analysis_id=bound.binding.analysis_id,
        axes=pca_axes(components),
        series=pca_series(samples, study_label=bound.entry.display_name),
        caption=caption,
    )
    await announce_analysis(
        conversation_id=conversation_id, bound=bound, analysis=updated
    )
    await append_part(conversation_id=conversation_id, chunk=eda_pca_chunk(part))
    await progress.update(percent=1.0, message="Reduction complete")
    return EdaStatisticResult(statistic=pca_fact(part)).model_dump(
        by_alias=True, mode="json"
    )


__all__ = ["run_eda_dimensionality_reduction_impl"]
