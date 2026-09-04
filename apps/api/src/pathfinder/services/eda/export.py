"""The open analysis, turned into the two WDK parameters a step carries."""

from __future__ import annotations

from pathfinder.domain.eda_parts import EdaEffectDirection
from pathfinder.integrations.eda.models import (
    EdaAnalysisDetail,
    EdaComputation,
    EdaNewAnalysis,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
)
from pathfinder.services.catalog.eda_backed import EdaStepRequest
from pathfinder.services.eda.authoring import serialize_spec
from pathfinder.services.eda.compute import NoComputationError, VolcanoThresholds


def _volcano(
    computation: EdaComputation,
    configuration: EdaVolcanoConfiguration,
) -> EdaVisualization:
    """One volcano, because the bridge plugin reads the first one only."""
    existing = computation.visualizations[0] if computation.visualizations else None
    if existing is None:
        return EdaVisualization(
            visualization_id=f"{computation.computation_id}-volcano",
            descriptor=EdaVolcanoDescriptor(configuration=configuration),
        )
    return existing.model_copy(
        update={
            "descriptor": existing.descriptor.model_copy(
                update={"configuration": configuration}
            )
        }
    )


def eda_step_request(
    analysis: EdaAnalysisDetail,
    *,
    dataset_id: str,
    effect_size_threshold: float | None = None,
    significance_threshold: float | None = None,
    effect_direction: EdaEffectDirection = "upAndDown",
) -> EdaStepRequest:
    """The step parameters for this analysis, with or without a volcano cut.

    Both thresholds together select the compute export; neither selects the
    subset export.
    """
    descriptor = analysis.descriptor
    if effect_size_threshold is not None or significance_threshold is not None:
        if effect_size_threshold is None or significance_threshold is None:
            msg = (
                "A volcano export needs both effectSizeThreshold and "
                "significanceThreshold."
            )
            raise ValueError(msg)
        if not descriptor.computations:
            msg = (
                f"Analysis {analysis.analysis_id} has no comparison yet; run the "
                f"differential expression first."
            )
            raise NoComputationError(msg)
        computation = descriptor.computations[0]
        configuration = EdaVolcanoConfiguration(
            effect_size_threshold=effect_size_threshold,
            significance_threshold=significance_threshold,
            effect_direction=effect_direction,
        )
        descriptor = descriptor.model_copy(
            update={
                "computations": [
                    computation.model_copy(
                        update={
                            "visualizations": [_volcano(computation, configuration)]
                        }
                    )
                ]
            }
        )
    spec = EdaNewAnalysis(
        study_id=dataset_id,
        display_name=analysis.display_name,
        description=analysis.description or "",
        is_public=analysis.is_public,
        descriptor=descriptor,
    )
    return EdaStepRequest(
        eda_dataset_id=dataset_id,
        eda_analysis_spec=serialize_spec(spec),
    )


def exported_thresholds(request: EdaStepRequest) -> VolcanoThresholds | None:
    """The volcano cut a step's parameters carry, or None for a subset export.

    The bridge plugin reads the first visualization of the first computation,
    so this reads the same one.
    """
    spec = EdaNewAnalysis.model_validate_json(request.eda_analysis_spec)
    volcanoes = [
        visualization
        for computation in spec.descriptor.computations
        for visualization in computation.visualizations
    ]
    if not volcanoes:
        return None
    configuration = volcanoes[0].descriptor.configuration
    return VolcanoThresholds(
        effect_size_threshold=configuration.effect_size_threshold,
        significance_threshold=configuration.significance_threshold,
        effect_direction=configuration.effect_direction,
    )
