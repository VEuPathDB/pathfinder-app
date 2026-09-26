"""An exported compute states the measurement it ran on, read from the E2 document.

The binding names the variable by its entity and its id. The words a researcher
reads name no column id, since only a read of the study names the column.
"""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.step_rationale import AnalysisRationale
from pathfinder.services.eda.export import exported_analysis
from pathfinder.tests.unit.domain.strategy._analysis import (
    ANTISENSE_COUNT,
    DATASET,
    SENSE_COUNT,
    e2_document,
)

_COUNTS_ENTITY = "ENT_fd574cd6"
_WORDS = (
    "Genes that differ between wildtype and delta-DHC mutant "
    "(DESeq, |effect| >= 1, p <= 0.05)"
)


def _parameters(value_variable: str) -> dict[str, StringValue]:
    return {
        "eda_dataset_id": StringValue(value=DATASET),
        "eda_analysis_spec": e2_document(value_variable),
    }


def test_the_e2_export_states_the_sense_count_column() -> None:
    binding = exported_analysis(AnalysisKind.COMPUTE, _parameters(SENSE_COUNT))

    assert binding is not None
    assert (binding.value_entity_id, binding.value_variable) == (
        _COUNTS_ENTITY,
        SENSE_COUNT,
    )


def test_a_compute_on_the_antisense_column_states_that_column() -> None:
    binding = exported_analysis(AnalysisKind.COMPUTE, _parameters(ANTISENSE_COUNT))

    assert binding is not None
    assert (binding.value_entity_id, binding.value_variable) == (
        _COUNTS_ENTITY,
        ANTISENSE_COUNT,
    )


def test_two_measurements_are_two_meanings() -> None:
    sense = exported_analysis(AnalysisKind.COMPUTE, _parameters(SENSE_COUNT))
    antisense = exported_analysis(AnalysisKind.COMPUTE, _parameters(ANTISENSE_COUNT))

    assert sense is not None
    assert antisense is not None
    assert sense.meaning() != antisense.meaning()


def test_the_step_reason_names_no_column_id() -> None:
    binding = exported_analysis(AnalysisKind.COMPUTE, _parameters(SENSE_COUNT))

    assert binding is not None
    assert (binding.words, AnalysisRationale.of(binding).reason) == (_WORDS, _WORDS)


def test_a_subset_export_states_no_measurement() -> None:
    """The subset plugin reads the subset alone, so no compute decides its genes."""
    binding = exported_analysis(AnalysisKind.SUBSET, _parameters(SENSE_COUNT))

    assert binding is not None
    assert (binding.method, binding.value_entity_id, binding.value_variable) == (
        None,
        None,
        None,
    )
