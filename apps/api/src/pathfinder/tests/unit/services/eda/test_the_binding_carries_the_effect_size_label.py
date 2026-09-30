"""A completed compute writes its effect-size label into the step's document, and
the binding read back from that document names it."""

from __future__ import annotations

from veupathdb.eda import (
    EdaAnalysisDetail,
    EdaComparator,
    EdaDifferentialExpressionConfig,
    EdaLabeledRange,
    EdaVariableSpec,
    VolcanoStatsResponse,
)

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.jobs.impls.eda_compute_impl import compared_computation
from pathfinder.services.eda.comparison import with_comparison
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.export import ExportReading, exported_analysis
from pathfinder.services.eda.steps import eda_step_node
from pathfinder.tests._support.eda_wire import fixture

_DATASET = "DS_e973eadd57"
_COUNTS = "ENT_fd574cd6"


def _config() -> EdaDifferentialExpressionConfig:
    return EdaDifferentialExpressionConfig(
        identifier_variable=EdaVariableSpec(
            entity_id=_COUNTS, variable_id="VEUPATHDB_GENE_ID"
        ),
        value_variable=EdaVariableSpec(
            entity_id=_COUNTS, variable_id="SEQUENCE_READ_COUNT_SENSE"
        ),
        comparator=EdaComparator(
            variable=EdaVariableSpec(
                entity_id="ENT_8151325d", variable_id="VAR_081ab087"
            ),
            group_a=[EdaLabeledRange(label="normal")],
            group_b=[EdaLabeledRange(label="febrile")],
        ),
    )


def _computed() -> EdaAnalysisDetail:
    """The recorded analysis, holding the comparison the recorded compute wrote."""
    statistics = VolcanoStatsResponse.model_validate(fixture("volcano_statistics"))
    detail = EdaAnalysisDetail.model_validate(fixture("analysis_detail_pass_and_de"))
    computation = compared_computation(
        "job-1", _config(), effect_size_label=statistics.effect_size_label
    )
    return detail.model_copy(
        update={
            "descriptor": with_comparison(detail.descriptor, computation.computation)
        }
    )


def test_a_computed_export_binds_the_computes_label() -> None:
    plan = eda_step_node(
        _computed(),
        dataset_id=_DATASET,
        thresholds=VolcanoThresholds(
            effect_size_threshold=1.5, significance_threshold=0.05
        ),
        reading=ExportReading(),
    )

    assert plan.binding.effect_size_label == "log2(Fold Change)"
    assert plan.binding.effect_size_threshold == 1.5


def test_the_binding_read_back_from_the_step_keeps_the_label() -> None:
    plan = eda_step_node(
        _computed(),
        dataset_id=_DATASET,
        thresholds=VolcanoThresholds(
            effect_size_threshold=1.5, significance_threshold=0.05
        ),
        reading=ExportReading(),
    )

    read_back = exported_analysis(AnalysisKind.COMPUTE, plan.node.parameters)

    assert (read_back, plan.binding.effect_size_label) == (
        plan.binding,
        "log2(Fold Change)",
    )


def test_a_subset_export_names_no_effect_size_label() -> None:
    plan = eda_step_node(
        _computed(), dataset_id=_DATASET, thresholds=None, reading=ExportReading()
    )

    assert plan.binding.effect_size_label == ""
