"""What a step's analysis document selects, read as its kind's plugin reads it.

The subset plugin reads the subset alone. The compute plugin takes the first
computation holding a volcano with both thresholds, and the cut from that
computation's first visualization. A search that never reads the document
exports no analysis.
"""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.eda import (
    EdaAnalysisDetail,
    EdaComputation,
    EdaDifferentialExpressionDescriptor,
    EdaNewAnalysis,
    EdaOtherVisualizationDescriptor,
    EdaStringSetFilter,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
)

from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.services.eda.export import eda_step_request, exported_analysis
from pathfinder.tests._support.eda_wire import fixture

_DATASET = "DS_e973eadd57"


def _recorded() -> EdaAnalysisDetail:
    """A pass compute, then a DESeq comparison of normal against febrile."""
    return EdaAnalysisDetail.model_validate(fixture("analysis_detail_pass_and_de"))


def _parameters(
    detail: EdaAnalysisDetail,
    *,
    effect_size_threshold: float | None = None,
    significance_threshold: float | None = None,
) -> dict[str, StringValue]:
    request = eda_step_request(
        detail,
        dataset_id=_DATASET,
        effect_size_threshold=effect_size_threshold,
        significance_threshold=significance_threshold,
    )
    return {
        name: StringValue(value=value)
        for name, value in request.wdk_parameters().items()
    }


def test_a_compute_export_reads_as_its_comparison_and_its_cut() -> None:
    parameters = _parameters(
        _recorded(), effect_size_threshold=1.0, significance_threshold=0.05
    )

    binding = exported_analysis(AnalysisKind.COMPUTE, parameters)

    assert binding is not None
    assert binding.dataset_id == _DATASET
    assert binding.comparison == EdaComparison(group_a=["normal"], group_b=["febrile"])
    assert (binding.method, binding.effect_direction) == ("DESeq", "upAndDown")
    assert (binding.effect_size_threshold, binding.significance_threshold) == (
        1.0,
        0.05,
    )
    assert binding.words == (
        "Genes that differ between normal and febrile (DESeq, |effect| >= 1, p <= 0.05)"
    )
    assert binding.step_parameters == parameters


def test_a_one_sided_export_names_the_group_it_keeps() -> None:
    detail = _recorded()
    request = eda_step_request(
        detail,
        dataset_id=_DATASET,
        effect_size_threshold=1.0,
        significance_threshold=0.01,
        effect_direction="upOnly",
    )

    binding = exported_analysis(
        AnalysisKind.COMPUTE,
        {name: StringValue(value=v) for name, v in request.wdk_parameters().items()},
    )

    assert binding is not None
    assert binding.effect_direction == "upOnly"
    assert binding.words == (
        "Genes higher in febrile than in normal (DESeq, |effect| >= 1, p <= 0.01)"
    )


def test_a_subset_export_carries_no_cut_though_its_comparison_stores_one() -> None:
    """The subset plugin reads the subset alone, whatever the document holds."""
    binding = exported_analysis(AnalysisKind.SUBSET, _parameters(_recorded()))

    assert binding is not None
    assert (binding.comparison, binding.method, binding.significance_threshold) == (
        None,
        None,
        None,
    )
    assert binding.words == (
        "The genes of the analysis 'veupathdb-py fixture analysis_detail_pass_and_de'"
    )


def test_a_subset_export_states_its_filters() -> None:
    recorded = _recorded()
    subset = recorded.descriptor.subset.model_copy(
        update={
            "descriptor": [
                EdaStringSetFilter(
                    entity_id="ENT_8151325d",
                    variable_id="VAR_081ab087",
                    string_set=["febrile"],
                )
            ]
        }
    )
    detail = recorded.model_copy(
        update={"descriptor": recorded.descriptor.model_copy(update={"subset": subset})}
    )

    binding = exported_analysis(AnalysisKind.SUBSET, _parameters(detail))

    assert binding is not None
    assert binding.subset == ["VAR_081ab087 is one of febrile"]
    assert binding.words.endswith(": VAR_081ab087 is one of febrile")


def test_a_step_with_no_analysis_document_reads_as_none() -> None:
    read = [
        exported_analysis(
            AnalysisKind.SUBSET,
            {"min_expression_percentile": NumberValue(value=80)},
        ),
        exported_analysis(
            AnalysisKind.SUBSET,
            {
                "eda_dataset_id": StringValue(value=_DATASET),
                "eda_analysis_spec": StringValue(value=""),
            },
        ),
    ]

    assert read == [None, None]


def _reordered(spec: EdaNewAnalysis) -> EdaNewAnalysis:
    """The document with its two computations in the other order."""
    computations = list(spec.descriptor.computations)
    return spec.model_copy(
        update={
            "descriptor": spec.descriptor.model_copy(
                update={"computations": computations[::-1]}
            )
        }
    )


def _document(spec: EdaNewAnalysis) -> dict[str, StringValue]:
    return {
        "eda_dataset_id": StringValue(value=_DATASET),
        "eda_analysis_spec": StringValue(
            value=spec.model_dump_json(by_alias=True, exclude_none=True)
        ),
    }


def test_a_subset_export_of_a_comparison_stored_first_binds_no_cut() -> None:
    """The stored volcano is no cut of a step whose plugin reads the subset."""
    request = eda_step_request(_recorded(), dataset_id=_DATASET)
    comparison_first = _reordered(
        EdaNewAnalysis.model_validate_json(request.eda_analysis_spec)
    )

    binding = exported_analysis(AnalysisKind.SUBSET, _document(comparison_first))

    assert binding is not None
    assert (binding.significance_threshold, binding.comparison) == (None, None)


def test_a_compute_export_reads_the_comparison_stored_behind_a_pass() -> None:
    """The compute plugin scans for the volcano, so the order is not the cut."""
    request = eda_step_request(
        _recorded(),
        dataset_id=_DATASET,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    pass_first = _reordered(
        EdaNewAnalysis.model_validate_json(request.eda_analysis_spec)
    )

    binding = exported_analysis(AnalysisKind.COMPUTE, _document(pass_first))

    assert binding is not None
    assert (
        binding.comparison,
        binding.effect_size_threshold,
        binding.significance_threshold,
    ) == (EdaComparison(group_a=["normal"], group_b=["febrile"]), 1.0, 0.05)


def test_a_search_that_never_reads_the_document_exports_no_analysis() -> None:
    """A WGCNA module search declares the parameter and runs its own query."""
    parameters = _parameters(
        _recorded(), effect_size_threshold=1.0, significance_threshold=0.05
    )

    read = {
        kind: exported_analysis(kind, parameters) for kind in (AnalysisKind.NONE, None)
    }

    assert read == {AnalysisKind.NONE: None, None: None}


def _volcano(visualization_id: str, effect: float, p: float) -> EdaVisualization:
    return EdaVisualization(
        visualization_id=visualization_id,
        descriptor=EdaVolcanoDescriptor(
            configuration=EdaVolcanoConfiguration(
                effect_size_threshold=effect, significance_threshold=p
            )
        ),
    )


def _with(spec: EdaNewAnalysis, computations: list[EdaComputation]) -> EdaNewAnalysis:
    return spec.model_copy(
        update={
            "descriptor": spec.descriptor.model_copy(
                update={"computations": computations}
            )
        }
    )


def _compute_export() -> EdaNewAnalysis:
    request = eda_step_request(
        _recorded(),
        dataset_id=_DATASET,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    return EdaNewAnalysis.model_validate_json(request.eda_analysis_spec)


def test_a_pass_compute_with_a_volcano_first_is_the_one_the_plugin_takes() -> None:
    spec = _compute_export()
    comparison, passed = spec.descriptor.computations
    pass_volcano = passed.model_copy(
        update={"visualizations": [_volcano("pv", 2.0, 0.01)]}
    )

    binding = exported_analysis(
        AnalysisKind.COMPUTE, _document(_with(spec, [pass_volcano, comparison]))
    )

    assert binding is not None
    assert (
        binding.effect_size_threshold,
        binding.significance_threshold,
        binding.comparison,
        binding.method,
    ) == (2.0, 0.01, None, None)


def test_of_two_comparisons_with_a_volcano_the_first_is_read() -> None:
    spec = _compute_export()
    comparison, passed = spec.descriptor.computations
    assert isinstance(comparison.descriptor, EdaDifferentialExpressionDescriptor)
    config = comparison.descriptor.configuration
    swapped = config.model_copy(
        update={
            "comparator": config.comparator.model_copy(
                update={
                    "group_a": config.comparator.group_b,
                    "group_b": config.comparator.group_a,
                }
            )
        }
    )
    second = comparison.model_copy(
        update={
            "computation_id": "de2",
            "descriptor": comparison.descriptor.model_copy(
                update={"configuration": swapped}
            ),
            "visualizations": [_volcano("v2", 2.0, 0.01)],
        }
    )

    binding = exported_analysis(
        AnalysisKind.COMPUTE, _document(_with(spec, [second, comparison, passed]))
    )

    assert binding is not None
    assert (
        binding.comparison,
        binding.effect_size_threshold,
        binding.significance_threshold,
    ) == (EdaComparison(group_a=["febrile"], group_b=["normal"]), 2.0, 0.01)


def test_a_volcano_without_both_thresholds_is_skipped_as_the_plugin_skips_it() -> None:
    spec = _compute_export()
    comparison, passed = spec.descriptor.computations
    bare = passed.model_copy(
        update={
            "visualizations": [
                EdaVisualization(
                    visualization_id="bare",
                    descriptor=EdaOtherVisualizationDescriptor(
                        type="volcanoplot", configuration={"effectSizeThreshold": 3}
                    ),
                )
            ]
        }
    )

    binding = exported_analysis(
        AnalysisKind.COMPUTE, _document(_with(spec, [bare, comparison]))
    )

    assert binding is not None
    assert (binding.effect_size_threshold, binding.significance_threshold) == (
        1.0,
        0.05,
    )
