"""The dimensionality-reduction compute: its checks, its components, its samples,
and the computation the analysis keeps."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import JsonValue
from veupathdb.domain import GENE_EXPRESSION_VALUE_IDS, VEUPATHDB_GENE_ID
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaComputation,
    EdaDimensionalityReductionConfig,
    EdaDimensionalityReductionDescriptor,
    EdaFilter,
    EdaOtherVisualizationDescriptor,
    EdaScatterplotConfig,
    EdaScatterplotSeries,
    EdaStudyDetail,
    EdaVariableMapping,
    EdaVariableSpec,
    EdaVisualization,
    get_eda_client,
)

from pathfinder.domain.eda_parts import EdaPcaAxis, EdaPcaSeries
from pathfinder.services.eda.authoring import patch_analysis
from pathfinder.services.eda.statistics import declared, lineage

REDUCTION = "dimensionalityreduction"
_AXES = 2


def reduction_errors(
    study: EdaStudyDetail,
    config: EdaDimensionalityReductionConfig,
    color_by: EdaVariableSpec | None,
) -> list[str]:
    """Every reason the compute or its plot would fail or mislead.

    The gene column and an expression measurement share one entity, and the
    color is a sample variable on an ancestor of it.
    """
    identifier, value = config.identifier_variable, config.value_variable
    errors = [
        f"{name} names {spec.entity_id}.{spec.variable_id}, which study {study.id} "
        f"does not declare."
        for name, spec in (("identifierVariable", identifier), ("valueVariable", value))
        if not declared(study, spec)
    ]
    if identifier.variable_id != VEUPATHDB_GENE_ID:
        errors.append(
            f"identifierVariable names {identifier.variable_id}, and the compute "
            f"accepts only {VEUPATHDB_GENE_ID}."
        )
    if value.variable_id not in GENE_EXPRESSION_VALUE_IDS:
        errors.append(
            f"valueVariable names {value.variable_id}, and the compute reads only an "
            f"expression measurement: {', '.join(sorted(GENE_EXPRESSION_VALUE_IDS))}."
        )
    if identifier.entity_id != value.entity_id:
        errors.append(
            f"identifierVariable is on entity {identifier.entity_id} and "
            f"valueVariable on {value.entity_id}. The compute needs both on one."
        )
    if (
        color_by is not None
        and color_by.entity_id not in lineage(study, identifier.entity_id)[:-1]
    ):
        errors.append(
            f"color_by_variable is on entity {color_by.entity_id}, and a sample's "
            f"color is read from an ancestor entity of {identifier.entity_id}."
        )
    if color_by is not None and not declared(study, color_by):
        errors.append(
            f"color_by_variable names {color_by.variable_id}, which entity "
            f"{color_by.entity_id} does not declare."
        )
    return errors


async def read_components(
    site_id: str,
    *,
    study_id: str,
    config: EdaDimensionalityReductionConfig,
    filters: Sequence[EdaFilter],
) -> list[EdaVariableMapping]:
    """The first two components the completed job generated, in its order."""
    meta = await get_eda_client(site_id).compute_meta(
        compute_name=REDUCTION, study_id=study_id, config=config, filters=filters
    )
    if len(meta.variables) < _AXES:
        msg = f"The compute generated {len(meta.variables)} components, not two."
        raise RuntimeError(msg)
    return meta.variables[:_AXES]


def pca_axes(components: Sequence[EdaVariableMapping]) -> list[EdaPcaAxis]:
    """Each component by the name the compute gives it, which states its variance.

    A component the compute names no variance for fails the read.
    """
    return [
        EdaPcaAxis.model_validate(
            {"variable_id": c.variable_spec.variable_id, "display_name": c.display_name}
        )
        for c in components
    ]


async def read_samples(
    site_id: str,
    *,
    study_id: str,
    config: EdaDimensionalityReductionConfig,
    filters: Sequence[EdaFilter],
    components: Sequence[EdaVariableMapping],
    color_by: EdaVariableSpec | None,
) -> list[EdaScatterplotSeries]:
    """Every sample on the first two components, one series per color value."""
    x, y = (c.variable_spec for c in components)
    plot = await get_eda_client(site_id).scatterplot(
        app=REDUCTION,
        study_id=study_id,
        filters=filters,
        config=EdaScatterplotConfig(
            output_entity_id=x.entity_id,
            value_spec="raw",
            x_axis_variable=x,
            y_axis_variable=y,
            overlay_variable=color_by,
            return_point_ids=True,
        ),
        compute_config=config,
    )
    return plot.data


def pca_series(
    series: Sequence[EdaScatterplotSeries], *, study_label: str
) -> list[EdaPcaSeries]:
    """Each series under its color value, or under the study when none colors it."""
    return [
        EdaPcaSeries.model_validate(
            {
                "label": study_label
                if s.overlay_variable_details is None
                else s.overlay_variable_details.value,
                "x": s.series_x,
                "y": s.series_y,
                "sample_ids": s.point_ids,
            }
        )
        for s in series
    ]


def reduction_computation(
    job_id: str,
    config: EdaDimensionalityReductionConfig,
    color_by: EdaVariableSpec | None,
) -> EdaComputation:
    """The reduction the analysis keeps, with the scatterplot of its samples."""
    plot: dict[str, JsonValue] = {"valueSpecConfig": "Raw"}
    if color_by is not None:
        plot["overlayVariable"] = color_by.model_dump(by_alias=True, mode="json")
    return EdaComputation(
        computation_id=job_id,
        descriptor=EdaDimensionalityReductionDescriptor(configuration=config),
        visualizations=[
            EdaVisualization(
                visualization_id=job_id,
                descriptor=EdaOtherVisualizationDescriptor(
                    type="scatterplot", configuration=plot
                ),
            )
        ],
    )


def with_reduction(
    descriptor: EdaAnalysisDescriptor, computation: EdaComputation
) -> EdaAnalysisDescriptor:
    """Replace the analysis's first reduction, or append one. Every other
    computation stays as the site stored it."""
    computations = list(descriptor.computations)
    held = next(
        (
            index
            for index, c in enumerate(computations)
            if c.descriptor.type == REDUCTION
        ),
        None,
    )
    if held is None:
        computations.append(computation)
    else:
        computations[held] = computation
    return descriptor.model_copy(update={"computations": computations})


async def apply_reduction(
    site_id: str, *, analysis_id: str, computation: EdaComputation
) -> EdaAnalysisDetail:
    """Write the reduction into the analysis."""
    return await patch_analysis(
        site_id,
        analysis_id=analysis_id,
        mutate=lambda current: with_reduction(current, computation),
    )


__all__ = [
    "REDUCTION",
    "apply_reduction",
    "pca_axes",
    "pca_series",
    "read_components",
    "read_samples",
    "reduction_computation",
    "reduction_errors",
    "with_reduction",
]
