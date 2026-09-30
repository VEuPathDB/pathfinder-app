"""An export shows its filters and its measured variable by the names the study
gives them, and carries the counts its compute holds for each reading of the cut."""

from __future__ import annotations

from veupathdb.eda import (
    EdaAnalysisDetail,
    EdaComparator,
    EdaDifferentialExpressionConfig,
    EdaLabeledRange,
    EdaStringSetFilter,
    EdaVariableSpec,
    VolcanoStatsResponse,
)

from pathfinder.domain.strategy.analysis_binding import AnalysisKind, CutTallies
from pathfinder.domain.strategy.step_rationale import AnalysisRationale
from pathfinder.jobs.impls.eda_compute_impl import compared_computation
from pathfinder.services.eda.comparison import with_comparison
from pathfinder.services.eda.compute import VolcanoThresholds, cut_tallies
from pathfinder.services.eda.export import ExportReading, exported_analysis
from pathfinder.services.eda.steps import eda_step_node
from pathfinder.tests._support.eda_wire import fixture

_DATASET = "DS_5b0caebb4c"
_SAMPLE = "ENT_samples"
_COUNTS = "ENT_counts"
# The C. neoformans study's own names for the variables the export reads.
_NAMES = {
    (_SAMPLE, "VAR_84f17484"): "genotype",
    (_SAMPLE, "VAR_ca3ad46f"): "fraction",
    (_COUNTS, "SEQUENCE_READ_COUNT"): "Count",
}
_CUT = VolcanoThresholds(
    effect_size_threshold=1.0, significance_threshold=0.05, effect_direction="upOnly"
)


def _config() -> EdaDifferentialExpressionConfig:
    return EdaDifferentialExpressionConfig(
        identifier_variable=EdaVariableSpec(
            entity_id=_COUNTS, variable_id="VEUPATHDB_GENE_ID"
        ),
        value_variable=EdaVariableSpec(
            entity_id=_COUNTS, variable_id="SEQUENCE_READ_COUNT"
        ),
        comparator=EdaComparator(
            variable=EdaVariableSpec(entity_id=_SAMPLE, variable_id="VAR_7033e90f"),
            group_a=[EdaLabeledRange(label="WT input 30C")],
            group_b=[EdaLabeledRange(label="WT input 37C")],
        ),
    )


def _filtered() -> EdaAnalysisDetail:
    """The recorded analysis, filtered to wild type input and compared 37 on 30."""
    detail = EdaAnalysisDetail.model_validate(fixture("analysis_detail_pass_and_de"))
    computation = compared_computation(
        "job-1", _config(), effect_size_label="log2(Fold Change)"
    )
    descriptor = with_comparison(detail.descriptor, computation.computation)
    subset = descriptor.subset.model_copy(
        update={
            "descriptor": [
                EdaStringSetFilter(
                    entity_id=_SAMPLE,
                    variable_id="VAR_84f17484",
                    string_set=["wild type"],
                ),
                EdaStringSetFilter(
                    entity_id=_SAMPLE, variable_id="VAR_ca3ad46f", string_set=["total"]
                ),
            ]
        }
    )
    return detail.model_copy(
        update={"descriptor": descriptor.model_copy(update={"subset": subset})}
    )


_TALLIES = CutTallies(
    tested=7884,
    retained=8,
    retained_up=8,
    retained_down=11,
    at_any_effect=41,
    at_any_significance=230,
)


def test_the_export_names_its_filters_and_measured_variable_as_the_study_does() -> None:
    plan = eda_step_node(
        _filtered(),
        dataset_id=_DATASET,
        thresholds=_CUT,
        reading=ExportReading(display_names=_NAMES, tallies=_TALLIES),
    )

    assert (
        plan.binding.subset_as_shown(),
        plan.binding.value_variable_name,
        plan.binding.tallies,
    ) == (
        ["genotype is one of wild type", "fraction is one of total"],
        "Count",
        _TALLIES,
    )


def test_the_names_and_the_counts_are_readings_no_document_holds() -> None:
    plan = eda_step_node(
        _filtered(),
        dataset_id=_DATASET,
        thresholds=_CUT,
        reading=ExportReading(display_names=_NAMES, tallies=_TALLIES),
    )

    read_back = exported_analysis(AnalysisKind.COMPUTE, plan.node.parameters)

    assert read_back is not None
    assert (read_back.meaning(), read_back.subset_as_shown()) == (
        plan.binding.meaning(),
        ["VAR_84f17484 is one of wild type", "VAR_ca3ad46f is one of total"],
    )


def test_the_cut_is_counted_at_each_reading_from_the_statistics() -> None:
    statistics = VolcanoStatsResponse.model_validate(
        {
            "effectSizeLabel": "log2(Fold Change)",
            "statistics": [
                {"pointID": "g_up_kept", "effectSize": "2.0", "pValue": "0.01"},
                {"pointID": "g_up_weak", "effectSize": "0.4", "pValue": "0.01"},
                {"pointID": "g_up_noisy", "effectSize": "3.0", "pValue": "0.2"},
                {"pointID": "g_down_kept", "effectSize": "-1.5", "pValue": "0.001"},
                {"pointID": "g_unread", "effectSize": "NA", "pValue": "0.01"},
            ],
        }
    )

    assert cut_tallies(statistics, _CUT) == CutTallies(
        tested=4,
        retained=1,
        retained_up=1,
        retained_down=1,
        at_any_effect=2,
        at_any_significance=2,
    )


def test_a_subset_export_s_reason_names_its_filters_as_the_study_does() -> None:
    analysis = _filtered()
    plan = eda_step_node(
        analysis,
        dataset_id=_DATASET,
        thresholds=None,
        reading=ExportReading(display_names=_NAMES),
    )

    read_back = exported_analysis(AnalysisKind.SUBSET, plan.node.parameters)

    assert read_back is not None
    assert (AnalysisRationale.of(plan.binding).line(), read_back.meaning()) == (
        (
            f"The genes of the analysis {analysis.display_name!r}: genotype is one "
            "of wild type; fraction is one of total"
        ),
        plan.binding.meaning(),
    )
