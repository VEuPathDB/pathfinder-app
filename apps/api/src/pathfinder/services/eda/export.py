"""The open analysis, turned into the two WDK parameters a step carries, and
those parameters read back as the analysis they select."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaComputation,
    EdaFilter,
    EdaNewAnalysis,
    EdaVisualization,
    EdaVisualizationDescriptor,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
    differential_expression_computations,
)
from veupathdb_mcp.catalog import EdaStepRequest

from pathfinder.domain.eda_parts import EdaComparison, EdaEffectDirection
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding, AnalysisKind
from pathfinder.services.eda.authoring import serialize_spec
from pathfinder.services.eda.compute import (
    VolcanoThresholds,
    analysis_computation,
    comparison_of,
)
from pathfinder.services.eda.description import filter_summaries
from pathfinder.services.eda.direction import direction_sentence


def _volcano(
    computation: EdaComputation, thresholds: VolcanoThresholds
) -> EdaVisualization:
    """The computation's first volcano at this cut, or a new one.

    The volcano keeps the plot settings the site stored beside the thresholds.
    """
    cut = thresholds.model_dump()
    for visualization in computation.visualizations:
        match visualization.descriptor:
            case EdaVolcanoDescriptor() as volcano:
                configuration = volcano.configuration.model_copy(update=cut)
                return visualization.model_copy(
                    update={
                        "descriptor": volcano.model_copy(
                            update={"configuration": configuration}
                        )
                    }
                )
            case _:
                continue
    return EdaVisualization(
        visualization_id=f"{computation.computation_id}-volcano",
        descriptor=EdaVolcanoDescriptor(
            configuration=EdaVolcanoConfiguration.model_validate(cut)
        ),
    )


def _compute_export(
    analysis: EdaAnalysisDetail, thresholds: VolcanoThresholds
) -> EdaAnalysisDescriptor:
    """The comparison first, with one volcano, then every other computation.

    The bridge plugin takes the first computation holding a volcano with both
    thresholds and reads the cut from that computation's first visualization.
    """
    held = analysis_computation(analysis).computation
    exported = held.model_copy(update={"visualizations": [_volcano(held, thresholds)]})
    others = list(analysis.descriptor.computations)
    del others[others.index(held)]
    return analysis.descriptor.model_copy(update={"computations": [exported, *others]})


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
        descriptor = _compute_export(
            analysis,
            VolcanoThresholds(
                effect_size_threshold=effect_size_threshold,
                significance_threshold=significance_threshold,
                effect_direction=effect_direction,
            ),
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


def exported_subset(request: EdaStepRequest) -> list[EdaFilter]:
    """The subset filters a step's parameters carry, as the export wrote them."""
    spec = EdaNewAnalysis.model_validate_json(request.eda_analysis_spec)
    return list(spec.descriptor.subset.descriptor)


def study_step_request(parameters: Mapping[str, ParamValue]) -> EdaStepRequest | None:
    """The two EDA parameters a step carries, or None when it carries none."""
    try:
        return EdaStepRequest.model_validate(
            {name: to_wire(value) for name, value in parameters.items()},
        )
    except ValidationError:
        return None


def exported_analysis(
    kind: AnalysisKind | None, parameters: Mapping[str, ParamValue]
) -> AnalysisBinding | None:
    """What a step's analysis document selects, as the plugin of its kind reads it.

    None when the step has no kind, exports no analysis, or carries no document.
    """
    if kind is None or kind is AnalysisKind.NONE:
        return None
    request = study_step_request(parameters)
    if request is None or not request.eda_analysis_spec:
        return None
    try:
        spec = EdaNewAnalysis.model_validate_json(request.eda_analysis_spec)
    except ValidationError:
        return None
    return analysis_binding(
        request.eda_dataset_id,
        spec,
        parameters,
        reads_a_volcano=kind is AnalysisKind.COMPUTE,
    )


def analysis_binding(
    dataset_id: str,
    spec: EdaNewAnalysis,
    parameters: Mapping[str, ParamValue],
    *,
    reads_a_volcano: bool,
) -> AnalysisBinding:
    """What an analysis document selects, beside the parameters that carry it."""
    subset = filter_summaries(spec.descriptor.subset.descriptor, display_names={})
    stated = AnalysisBinding(
        dataset_id=dataset_id,
        subset=subset,
        words=_subset_words(spec.display_name, subset),
        step_parameters=dict(parameters),
    )
    computation = _volcano_computation(spec.descriptor) if reads_a_volcano else None
    cut = None if computation is None else _volcano_cut(computation)
    if computation is None or cut is None:
        return stated
    compared = next(
        (
            held
            for held in differential_expression_computations(spec.descriptor)
            if held.computation == computation
        ),
        None,
    )
    comparison = (
        None if compared is None else comparison_of(compared.descriptor.configuration)
    )
    method = (
        None
        if compared is None
        else compared.descriptor.configuration.differential_expression_method
    )
    return stated.model_copy(
        update={
            "comparison": comparison,
            "method": method,
            "effect_direction": cut.effect_direction,
            "effect_size_threshold": cut.effect_size_threshold,
            "significance_threshold": cut.significance_threshold,
            "words": _cut_words(spec.display_name, comparison, method, cut),
        }
    )


def _subset_words(display_name: str, subset: list[str]) -> str:
    named = f"The genes of the analysis {display_name!r}"
    return f"{named}: {'; '.join(subset)}" if subset else named


def _cut_words(
    display_name: str,
    comparison: EdaComparison | None,
    method: str | None,
    cut: VolcanoThresholds,
) -> str:
    """The genes a volcano cut keeps, named by its groups when it compares two."""
    bounds = f"|effect| >= {cut.effect_size_threshold:g}, p <= {cut.significance_threshold:g}"
    if comparison is None:
        return (
            f"The genes past the volcano cut of the analysis {display_name!r} "
            f"({cut.effect_direction}, {bounds})"
        )
    return (
        f"{direction_sentence(comparison, cut.effect_direction)} ({method}, {bounds})"
    )


def _volcano_computation(descriptor: EdaAnalysisDescriptor) -> EdaComputation | None:
    """The computation the compute plugin reads: the first holding a volcano.

    A volcano descriptor carries both thresholds, which is what the plugin
    requires of the one it looks for.
    """
    return next(
        (
            computation
            for computation in descriptor.computations
            if any(_is_a_volcano(v.descriptor) for v in computation.visualizations)
        ),
        None,
    )


def _is_a_volcano(descriptor: EdaVisualizationDescriptor) -> bool:
    match descriptor:
        case EdaVolcanoDescriptor():
            return True
        case _:
            return False


def _volcano_cut(computation: EdaComputation) -> VolcanoThresholds | None:
    """The cut the plugin reads: that computation's first visualization.

    A first visualization that is no volcano is one the plugin cannot read.
    """
    match computation.visualizations[0].descriptor:
        case EdaVolcanoDescriptor(configuration=configuration):
            return VolcanoThresholds.model_validate(configuration, from_attributes=True)
        case _:
            return None
