"""The open analysis becomes the two WDK parameters an EDA-backed step takes."""

from __future__ import annotations

import json

import pytest
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaComparator,
    EdaComputation,
    EdaDifferentialExpressionConfig,
    EdaDifferentialExpressionDescriptor,
    EdaLabeledRange,
    EdaStringSetFilter,
    EdaSubsetDescriptor,
    EdaVariableSpec,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
)

from pathfinder.services.eda.authoring import EmptyAnalysisError
from pathfinder.services.eda.compute import NoComputationError
from pathfinder.services.eda.export import eda_step_request

_DATASET = "DS_53f554ec6a"
_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"


def _filter() -> EdaStringSetFilter:
    return EdaStringSetFilter(
        entity_id=_ENTITY, variable_id="VAR_035294d0", string_set=["P. berghei"]
    )


def _computation(*, visualizations: list[EdaVisualization]) -> EdaComputation:
    return EdaComputation(
        computation_id="c1",
        display_name="DESeq",
        descriptor=EdaDifferentialExpressionDescriptor(
            configuration=EdaDifferentialExpressionConfig(
                identifier_variable=EdaVariableSpec(
                    entity_id=_ENTITY, variable_id="VAR_gene"
                ),
                value_variable=EdaVariableSpec(
                    entity_id=_ENTITY, variable_id="VAR_counts"
                ),
                comparator=EdaComparator(
                    variable=EdaVariableSpec(
                        entity_id=_ENTITY, variable_id="VAR_state"
                    ),
                    group_a=[EdaLabeledRange(label="febrile")],
                    group_b=[EdaLabeledRange(label="normal")],
                ),
            )
        ),
        visualizations=visualizations,
    )


def _volcano(*, effect_size: float, significance: float) -> EdaVisualization:
    return EdaVisualization(
        visualization_id="v1",
        display_name="Volcano",
        descriptor=EdaVolcanoDescriptor(
            configuration=EdaVolcanoConfiguration(
                effect_size_threshold=effect_size,
                significance_threshold=significance,
            ),
            current_plot_filters=[_filter()],
        ),
    )


def _detail(*, computations: list[EdaComputation] | None = None) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id="t4fszEJ",
        display_name="berghei subset",
        study_id=_DATASET,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(descriptor=[_filter()]),
            computations=computations or [],
        ),
    )


def test_a_subset_export_carries_the_filters_and_names_the_dataset() -> None:
    request = eda_step_request(_detail(), dataset_id=_DATASET)
    spec = json.loads(request.eda_analysis_spec)
    assert spec["studyId"] == _DATASET
    assert spec["descriptor"]["subset"]["descriptor"][0]["stringSet"] == ["P. berghei"]
    assert spec["descriptor"]["computations"] == []
    assert request.eda_dataset_id == _DATASET


def test_an_analysis_with_no_filter_and_no_computation_exports_no_step() -> None:
    """The step would carry an empty spec, which selects nothing."""
    detail = _detail()
    empty = detail.model_copy(update={"descriptor": EdaAnalysisDescriptor()})
    with pytest.raises(EmptyAnalysisError) as refusal:
        eda_step_request(empty, dataset_id=_DATASET)
    assert refusal.value.detail == (
        "The analysis holds no filter and no computation, so it selects no "
        "genes and exports no step."
    )


def test_a_compute_export_writes_the_requested_thresholds_into_the_volcano() -> None:
    request = eda_step_request(
        _detail(
            computations=[
                _computation(
                    visualizations=[_volcano(effect_size=1.0, significance=0.05)]
                )
            ]
        ),
        dataset_id=_DATASET,
        effect_size_threshold=2.0,
        significance_threshold=0.01,
        effect_direction="upOnly",
    )
    spec = json.loads(request.eda_analysis_spec)
    viz = spec["descriptor"]["computations"][0]["visualizations"][0]["descriptor"]
    assert viz["type"] == "volcanoplot"
    assert viz["configuration"]["effectSizeThreshold"] == 2.0
    assert viz["configuration"]["significanceThreshold"] == 0.01
    assert viz["configuration"]["effectDirection"] == "upOnly"


def test_a_compute_export_keeps_the_computation_the_document_already_holds() -> None:
    request = eda_step_request(
        _detail(
            computations=[
                _computation(
                    visualizations=[_volcano(effect_size=1.0, significance=0.05)]
                )
            ]
        ),
        dataset_id=_DATASET,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    spec = json.loads(request.eda_analysis_spec)
    computation = spec["descriptor"]["computations"][0]
    assert computation["computationId"] == "c1"
    assert computation["descriptor"]["type"] == "differentialexpression"
    comparator = computation["descriptor"]["configuration"]["comparator"]
    assert comparator["groupA"][0]["label"] == "febrile"
    assert spec["descriptor"]["subset"]["descriptor"][0]["stringSet"] == ["P. berghei"]


def test_a_compute_export_replaces_a_second_visualization() -> None:
    """The plugin reads the FIRST visualization, so only one may survive."""
    request = eda_step_request(
        _detail(
            computations=[
                _computation(
                    visualizations=[
                        _volcano(effect_size=1.0, significance=0.05),
                        _volcano(effect_size=9.0, significance=0.9),
                    ]
                )
            ]
        ),
        dataset_id=_DATASET,
        effect_size_threshold=1.5,
        significance_threshold=0.02,
    )
    spec = json.loads(request.eda_analysis_spec)
    visualizations = spec["descriptor"]["computations"][0]["visualizations"]
    assert len(visualizations) == 1
    assert visualizations[0]["visualizationId"] == "v1"
    assert (
        visualizations[0]["descriptor"]["configuration"]["effectSizeThreshold"] == 1.5
    )


def test_a_computation_with_no_visualization_gets_one() -> None:
    """findVolcanoComputation needs a volcanoplot, so the export supplies it."""
    request = eda_step_request(
        _detail(computations=[_computation(visualizations=[])]),
        dataset_id=_DATASET,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    spec = json.loads(request.eda_analysis_spec)
    visualization = spec["descriptor"]["computations"][0]["visualizations"][0]
    assert visualization["visualizationId"]
    assert visualization["descriptor"]["type"] == "volcanoplot"


def test_a_compute_export_with_no_computation_is_refused() -> None:
    with pytest.raises(NoComputationError):
        eda_step_request(
            _detail(),
            dataset_id=_DATASET,
            effect_size_threshold=1.0,
            significance_threshold=0.05,
        )


def test_a_half_specified_threshold_pair_is_refused() -> None:
    """findVolcanoComputation requires both keys, so one alone is a bug."""
    with pytest.raises(ValueError, match="both"):
        eda_step_request(
            _detail(computations=[_computation(visualizations=[])]),
            dataset_id=_DATASET,
            effect_size_threshold=1.0,
        )


def test_the_spec_names_the_dataset_the_step_names() -> None:
    """The bridge plugin compares the two, and a mismatch is a 422."""
    detail = _detail()
    mismatched = detail.model_copy(update={"study_id": "STUDY_53f554ec6a"})
    request = eda_step_request(mismatched, dataset_id=_DATASET)
    spec = json.loads(request.eda_analysis_spec)
    assert spec["studyId"] == _DATASET
