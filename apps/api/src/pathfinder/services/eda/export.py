"""The open analysis, turned into the two WDK parameters a step carries, and
those parameters read back as the analysis they select."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

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

from pathfinder.domain.eda_parts import EdaEffectDirection
from pathfinder.domain.strategy.analysis_binding import (
    AnalysisBinding,
    AnalysisKind,
    CutTallies,
)
from pathfinder.services.eda.authoring import serialize_spec
from pathfinder.services.eda.catalog import get_study_detail_for_dataset
from pathfinder.services.eda.compute import (
    VolcanoThresholds,
    analysis_computation,
    comparison_of,
    read_cut_tallies,
)
from pathfinder.services.eda.description import display_names, filter_summaries
from pathfinder.services.eda.direction import direction_sentence

type VariableNames = Mapping[tuple[str, str], str]


@dataclass(frozen=True, slots=True)
class ExportReading:
    """What an export reads beside the analysis: the study's name for each
    variable, by entity and variable id, and the counts of a compute's cut."""

    display_names: VariableNames = field(default_factory=dict)
    tallies: CutTallies | None = None


async def read_the_export(
    site_id: str,
    *,
    dataset_id: str,
    analysis: EdaAnalysisDetail,
    thresholds: VolcanoThresholds | None,
) -> ExportReading:
    """The study's names for the analysis's variables, and the counts of the cut."""
    entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    tallies = (
        None
        if thresholds is None
        else await read_cut_tallies(
            site_id, study_id=entry.study_id, analysis=analysis, cut=thresholds
        )
    )
    return ExportReading(display_names=display_names(study), tallies=tallies)


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
        reading=ExportReading(),
    )


def analysis_binding(
    dataset_id: str,
    spec: EdaNewAnalysis,
    parameters: Mapping[str, ParamValue],
    *,
    reads_a_volcano: bool,
    reading: ExportReading,
) -> AnalysisBinding:
    """What an analysis document selects, beside the parameters that carry it,
    and what the export read of its study and its compute.

    ``subset`` names each variable by its id; the words name it as the study
    does when the export read the study.
    """
    filters = spec.descriptor.subset.descriptor
    shown = filter_summaries(filters, display_names=reading.display_names)
    stated = AnalysisBinding(
        dataset_id=dataset_id,
        subset=filter_summaries(filters, display_names={}),
        words=_subset_words(spec.display_name, shown),
        step_parameters=dict(parameters),
        shown_subset=shown,
    )
    computation = _volcano_computation(spec.descriptor) if reads_a_volcano else None
    cut = None if computation is None else _volcano_cut(computation)
    if computation is None or cut is None:
        return stated
    stated = stated.model_copy(
        update={
            "effect_size_label": _effect_size_label(computation),
            "tallies": reading.tallies,
        }
    )
    compared = next(
        (
            held
            for held in differential_expression_computations(spec.descriptor)
            if held.computation == computation
        ),
        None,
    )
    if compared is None:
        return stated.model_copy(
            update={
                **cut.model_dump(),
                "words": _uncompared_words(spec.display_name, cut),
            }
        )
    configuration = compared.descriptor.configuration
    comparison = comparison_of(configuration)
    method = configuration.differential_expression_method
    measured = configuration.value_variable
    return stated.model_copy(
        update={
            **cut.model_dump(),
            "comparison": comparison,
            "method": method,
            "value_entity_id": measured.entity_id,
            "value_variable": measured.variable_id,
            "value_variable_name": reading.display_names.get(
                (measured.entity_id, measured.variable_id), ""
            ),
            "words": (
                f"{direction_sentence(comparison, cut.effect_direction)} "
                f"({method}, {_bounds(cut)})"
            ),
        }
    )


def _subset_words(display_name: str, subset: list[str]) -> str:
    named = f"The genes of the analysis {display_name!r}"
    return f"{named}: {'; '.join(subset)}" if subset else named


def _bounds(cut: VolcanoThresholds) -> str:
    return f"|effect| >= {cut.effect_size_threshold:g}, p <= {cut.significance_threshold:g}"


def _uncompared_words(display_name: str, cut: VolcanoThresholds) -> str:
    """The genes a volcano cut keeps when no comparison names its groups."""
    return (
        f"The genes past the volcano cut of the analysis {display_name!r} "
        f"({cut.effect_direction}, {_bounds(cut)})"
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


def _effect_size_label(computation: EdaComputation) -> str:
    """The unit the compute stored beside the cut, or nothing when it stored none."""
    match computation.visualizations[0].descriptor:
        case EdaVolcanoDescriptor(configuration=configuration):
            return configuration.effect_size_label or ""
        case _:
            return ""


def _volcano_cut(computation: EdaComputation) -> VolcanoThresholds | None:
    """The cut the plugin reads: that computation's first visualization.

    A first visualization that is no volcano is one the plugin cannot read.
    """
    match computation.visualizations[0].descriptor:
        case EdaVolcanoDescriptor(configuration=configuration):
            return VolcanoThresholds.model_validate(configuration, from_attributes=True)
        case _:
            return None
