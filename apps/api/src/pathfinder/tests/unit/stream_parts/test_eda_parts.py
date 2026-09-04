"""The three data-eda parts, their payloads, and their registration."""

from __future__ import annotations

import pytest
from assistant_core.conversation.stream_parts.core_parts import (
    register_core_stream_parts,
)
from assistant_core.conversation.stream_parts.registry import StreamPartRegistry
from pydantic import BaseModel, ValidationError

from pathfinder.ai.eda_stream_parts import register_eda_stream_parts
from pathfinder.ai.strategy_stream_parts import register_strategy_stream_parts
from pathfinder.domain.eda_parts import (
    EdaAnalysisState,
    EdaDistributionSeries,
    EdaEntityCount,
    EdaSubsetPreviewPart,
    EdaVizPart,
    EdaVolcanoPoint,
)

_KINDS = {
    "data-eda.analysis-state",
    "data-eda.subset-preview",
    "data-eda.viz",
}

_ANALYSIS_STATE_KEYS = [
    "siteId",
    "datasetId",
    "studyId",
    "analysisId",
    "revision",
    "studyDisplayName",
    "displayName",
    "numFilters",
    "numComputations",
    "filters",
    "filterSummaries",
    "entityCounts",
    "canExportRows",
]


def test_the_three_kinds_register() -> None:
    registry = StreamPartRegistry()
    register_eda_stream_parts(registry)
    assert registry.kinds() == _KINDS


def test_the_dotted_kinds_map_to_python_identifiers() -> None:
    registry = StreamPartRegistry()
    register_eda_stream_parts(registry)
    names = {entry.schema_name for entry in registry.entries()}
    assert names == {"eda_analysis_state", "eda_subset_preview", "eda_viz"}


def test_the_eda_kinds_do_not_collide_with_the_runtime_or_the_strategy_parts() -> None:
    registry = StreamPartRegistry()
    register_core_stream_parts(registry)
    register_strategy_stream_parts(registry)
    register_eda_stream_parts(registry)
    assert registry.kinds() >= _KINDS


def test_the_schema_index_exposes_every_eda_payload() -> None:
    registry = StreamPartRegistry()
    register_eda_stream_parts(registry)
    fields = set(registry.schema_index_model().model_fields)
    assert {"eda_analysis_state", "eda_subset_preview", "eda_viz"} <= fields


def test_every_analysis_state_field_is_required_on_the_wire() -> None:
    """The producer fills all thirteen, so the schema demands all thirteen."""
    schema = EdaAnalysisState.model_json_schema(by_alias=True)
    assert schema["required"] == _ANALYSIS_STATE_KEYS
    assert schema["properties"]["revision"]["anyOf"] == [
        {"type": "integer"},
        {"type": "null"},
    ]


# A plot's caption is written by the model, so a producer can have none.
_OPTIONAL_ON_THE_WIRE = {
    EdaSubsetPreviewPart: {"caption"},
    EdaVizPart: {"caption"},
}


@pytest.mark.parametrize(
    "part",
    [EdaDistributionSeries, EdaSubsetPreviewPart, EdaVizPart, EdaVolcanoPoint],
    ids=lambda model: model.__name__,
)
def test_every_eda_part_field_is_required_on_the_wire(
    part: type[BaseModel],
) -> None:
    """The producer fills every field a renderer must not default."""
    schema = part.model_json_schema(by_alias=True)
    optional = _OPTIONAL_ON_THE_WIRE.get(part, set())
    assert schema["required"] == [
        name for name in schema["properties"] if name not in optional
    ]


def test_a_plot_part_defaults_its_caption_to_the_empty_string() -> None:
    """A producer that writes no caption leaves the key present and empty."""
    viz = EdaVizPart(
        dataset_id="DS_e973eadd57",
        analysis_id="t4fszEJ",
        chart="volcano",
        effect_size_label="log2(Fold Change)",
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="upAndDown",
        total_points=0,
        retained_points=0,
        points=[],
    )
    preview = EdaSubsetPreviewPart(
        dataset_id="DS_53f554ec6a",
        analysis_id="t4fszEJ",
        entity_counts=[],
        distribution=None,
        distribution_note=None,
    )
    assert viz.model_dump(by_alias=True)["caption"] == ""
    assert preview.model_dump(by_alias=True)["caption"] == ""


def test_a_plot_part_carries_the_caption_the_model_wrote() -> None:
    preview = EdaSubsetPreviewPart(
        dataset_id="DS_53f554ec6a",
        analysis_id="t4fszEJ",
        entity_counts=[],
        distribution=None,
        distribution_note=None,
        caption="Distribution of per-gene sense counts across 12 samples",
    )
    assert preview.model_dump(by_alias=True)["caption"] == (
        "Distribution of per-gene sense counts across 12 samples"
    )


def test_a_volcano_point_names_its_p_value_key_even_with_no_p_value() -> None:
    schema = EdaVolcanoPoint.model_json_schema(by_alias=True)
    assert schema["properties"]["pValue"]["anyOf"] == [
        {"type": "number"},
        {"type": "null"},
    ]


def test_every_entity_count_field_is_required_on_the_wire() -> None:
    schema = EdaEntityCount.model_json_schema(by_alias=True)
    assert schema["required"] == [
        "entityId",
        "entityDisplayName",
        "count",
        "unfilteredCount",
    ]


def test_an_analysis_state_that_omits_a_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        EdaAnalysisState.model_validate(
            {
                "siteId": "plasmodb",
                "datasetId": "DS_53f554ec6a",
                "studyId": "STUDY_53f554ec6a",
                "analysisId": "t4fszEJ",
            }
        )


def test_the_analysis_state_carries_the_reference_and_a_summary() -> None:
    part = EdaAnalysisState(
        site_id="plasmodb",
        dataset_id="DS_53f554ec6a",
        study_id="STUDY_53f554ec6a",
        analysis_id="t4fszEJ",
        revision=None,
        study_display_name="Rodent malaria phenotypes",
        display_name="berghei subset",
        num_filters=1,
        num_computations=0,
        filters=[
            {
                "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
                "variableId": "VAR_035294d0",
                "type": "stringSet",
                "stringSet": ["P. berghei"],
            }
        ],
        filter_summaries=["Species is one of P. berghei"],
        entity_counts=[
            EdaEntityCount(
                entity_id="GENE_PHENOTYPE_DATA_ENTITY",
                entity_display_name="Gene phenotype",
                count=4011,
                unfiltered_count=4279,
            )
        ],
        can_export_rows=True,
    )
    dumped = part.model_dump(by_alias=True)
    assert dumped["datasetId"] == "DS_53f554ec6a"
    assert dumped["analysisId"] == "t4fszEJ"
    assert dumped["numFilters"] == 1
    assert dumped["revision"] is None
    assert dumped["filters"][0]["stringSet"] == ["P. berghei"]
    assert dumped["entityCounts"][0]["entityDisplayName"] == "Gene phenotype"


def test_the_subset_preview_carries_entity_counts_and_one_distribution() -> None:
    part = EdaSubsetPreviewPart(
        dataset_id="DS_53f554ec6a",
        analysis_id="t4fszEJ",
        entity_counts=[
            EdaEntityCount(
                entity_id="GENE_PHENOTYPE_DATA_ENTITY",
                entity_display_name="Gene phenotype",
                count=4011,
                unfiltered_count=4279,
            )
        ],
        distribution=EdaDistributionSeries(
            variable_id="VAR_035294d0",
            variable_display_name="Species",
            labels=["P. berghei", "P. falciparum", "P. yoelii"],
            values=[4011.0, 4130.0, 268.0],
            subset_size=4279,
            num_var_values=8409,
            num_missing_cases=0,
            is_multi_valued=True,
        ),
        distribution_note=None,
    )
    dumped = part.model_dump(by_alias=True)
    assert dumped["entityCounts"][0]["unfilteredCount"] == 4279
    assert dumped["distribution"]["isMultiValued"] is True
    assert dumped["distributionNote"] is None


def test_a_multi_valued_distribution_says_so_because_the_values_do_not_partition() -> (
    None
):
    """4011 + 4130 + 268 = 8409 over 4279 rows."""
    series = EdaDistributionSeries(
        variable_id="V",
        variable_display_name="Species",
        labels=["a", "b"],
        values=[4011.0, 4130.0],
        subset_size=4279,
        num_var_values=8409,
        num_missing_cases=0,
        is_multi_valued=True,
    )
    assert sum(series.values) > series.subset_size
    assert series.is_multi_valued is True


def test_the_viz_part_carries_the_chart_kind_and_its_series() -> None:
    part = EdaVizPart(
        dataset_id="DS_e973eadd57",
        analysis_id="t4fszEJ",
        chart="volcano",
        effect_size_label="log2(Fold Change)",
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="upAndDown",
        total_points=5511,
        retained_points=1543,
        points=[
            EdaVolcanoPoint(
                point_id="PF3D7_0100200",
                effect_size=3.94437533216012,
                p_value=1.95781599815607e-05,
                adjusted_p_value=0.000137772236907279,
                retained=True,
            )
        ],
    )
    dumped = part.model_dump(by_alias=True)
    assert dumped["chart"] == "volcano"
    assert dumped["retainedPoints"] == 1543
    assert dumped["points"][0]["pointId"] == "PF3D7_0100200"


def test_a_viz_point_may_have_no_p_value() -> None:
    point = EdaVolcanoPoint(
        point_id="PF3D7_MIT04200",
        effect_size=-1.49447459261845,
        p_value=None,
        adjusted_p_value=None,
        retained=False,
    )
    assert point.p_value is None


def test_the_labels_and_values_of_a_series_are_the_same_length() -> None:
    with pytest.raises(ValidationError):
        EdaDistributionSeries(
            variable_id="V",
            variable_display_name="V",
            labels=["a", "b"],
            values=[1.0],
            subset_size=1,
            num_var_values=1,
            num_missing_cases=0,
            is_multi_valued=False,
        )


def test_the_viz_chart_union_refuses_a_kind_no_renderer_draws() -> None:
    with pytest.raises(ValidationError):
        EdaVizPart(
            dataset_id="DS_x",
            analysis_id="a",
            chart="pie",
            effect_size_label="",
            effect_size_threshold=None,
            significance_threshold=None,
            effect_direction=None,
            total_points=0,
            retained_points=0,
            points=[],
        )
