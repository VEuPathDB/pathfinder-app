"""The write that sets an analysis's comparison and keeps its other computations."""

from __future__ import annotations

from veupathdb.domain import validate_compute_config
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaComputation,
    EdaDifferentialExpressionComputation,
    differential_expression_computations,
)

from pathfinder.services.eda.authoring import SubsetRejectedError, patch_analysis
from pathfinder.services.eda.catalog import get_study_detail_for_dataset


def with_comparison(
    descriptor: EdaAnalysisDescriptor, computation: EdaComputation
) -> EdaAnalysisDescriptor:
    """Replace the first complete differential expression, or append one.

    Every other computation stays as the site stored it.
    """
    held = differential_expression_computations(descriptor)
    computations = list(descriptor.computations)
    if held:
        computations[computations.index(held[0].computation)] = computation
    else:
        computations.append(computation)
    return descriptor.model_copy(update={"computations": computations})


async def apply_computation(
    site_id: str,
    *,
    analysis_id: str,
    dataset_id: str,
    computation: EdaDifferentialExpressionComputation,
) -> EdaAnalysisDetail:
    """Write the analysis's comparison, after checking its config."""
    _entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    errors = validate_compute_config(study, computation.descriptor.configuration)
    if errors:
        raise SubsetRejectedError(errors)
    return await patch_analysis(
        site_id,
        analysis_id=analysis_id,
        mutate=lambda current: with_comparison(current, computation.computation),
    )
