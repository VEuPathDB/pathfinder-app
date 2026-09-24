"""A DESeq2 export of the 24 h versus 18 h comparison, as a spec states it."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.operational_spec import Criterion

DATASET = "DS_e973eadd57"
EXPORTED = "step_2c6dce8d"
COMPUTE_SEARCH = "GenesByEdaVizWithCompute"
WORDS = "Genes higher in 24h than in 18h (DESeq, |effect| >= 1, p <= 0.05)"


def document(significance: float = 0.05) -> StringValue:
    """The analysis document the step carries, at one significance cut."""
    return StringValue(
        value=(
            f'{{"studyId":"{DATASET}","displayName":"24h vs 18h",'
            f'"significanceThreshold":{significance}}}'
        )
    )


def binding(*, significance: float = 0.05) -> AnalysisBinding:
    return AnalysisBinding(
        dataset_id=DATASET,
        comparison=EdaComparison(group_a=["18h"], group_b=["24h"]),
        method="DESeq",
        effect_direction="upOnly",
        effect_size_threshold=1.0,
        significance_threshold=significance,
        words=WORDS,
        step_parameters={
            "eda_dataset_id": StringValue(value=DATASET),
            "eda_analysis_spec": document(significance),
        },
    )


def analysed(
    step_id: str = EXPORTED, *, bound: AnalysisBinding | None = None
) -> Criterion:
    """The criterion the export is, stated by its binding."""
    return Criterion(
        id=step_id,
        text=WORDS,
        search_name=COMPUTE_SEARCH,
        analysis=bound or binding(),
    )


def pending(criterion_id: str = "c_24h_vs_36_up") -> Criterion:
    """A comparison only the analysis workflow realizes, waiting for it."""
    return Criterion(
        id=criterion_id,
        text="genes higher at 24 h than at 36 h, significant",
        needs_analysis_on=DATASET,
    )


def exported_step(
    step_id: str = EXPORTED, *, significance: float = 0.05
) -> StrategyStepNode:
    """The step the export wrote, with the document the binding carries."""
    return StrategyStepNode(
        id=step_id,
        search_name=COMPUTE_SEARCH,
        display_name="Genes higher in 24h than in 18h",
        parameters=dict(binding(significance=significance).step_parameters),
    )
