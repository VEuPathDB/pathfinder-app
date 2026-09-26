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
SENSE_COUNT = "SEQUENCE_READ_COUNT_SENSE"
ANTISENSE_COUNT = "SEQUENCE_READ_COUNT_ANTISENSE"
WORDS = "Genes higher in 24h than in 18h (DESeq, |effect| >= 1, p <= 0.05)"
E2_STEP = "step_7c16d398"
# The document the plasmodb E2 export wrote on its step, as the site stored it.
E2_DOCUMENT = (
    '{"studyId":"DS_e973eadd57","displayName":"Wild type versus DHC mutant '
    'differential expressio","description":"","isPublic":false,"descriptor":'
    '{"subset":{"descriptor":[],"uiSettings":{}},"computations":[{"computationId":'
    '"53d5b59e6417e9ae31a3464f9ef7e9cf","descriptor":{"type":'
    '"differentialexpression","configuration":{"identifierVariable":{"entityId":'
    '"ENT_fd574cd6","variableId":"VEUPATHDB_GENE_ID"},"valueVariable":{"entityId":'
    '"ENT_fd574cd6","variableId":"SEQUENCE_READ_COUNT_SENSE"},"comparator":'
    '{"variable":{"entityId":"ENT_8151325d","variableId":"VAR_84f17484"},"groupA":'
    '[{"label":"wildtype"}],"groupB":[{"label":"delta-DHC mutant"}]},'
    '"differentialExpressionMethod":"DESeq","pValueFloor":"1e-200"}},'
    '"visualizations":[{"visualizationId":"53d5b59e6417e9ae31a3464f9ef7e9cf",'
    '"descriptor":{"type":"volcanoplot","configuration":{"effectSizeThreshold":1.0,'
    '"significanceThreshold":0.05,"effectDirection":"upAndDown"},'
    '"currentPlotFilters":[]}}]}],"starredVariables":[],"dataTableConfig":{},'
    '"derivedVariables":[]}}'
)


def e2_document(value_variable: str = SENSE_COUNT) -> StringValue:
    """The E2 document, its compute run on ``value_variable``."""
    return StringValue(value=E2_DOCUMENT.replace(SENSE_COUNT, value_variable))


def e2_step(value_variable: str = SENSE_COUNT) -> StrategyStepNode:
    """The step the E2 export wrote."""
    return StrategyStepNode(
        id=E2_STEP,
        search_name=COMPUTE_SEARCH,
        display_name="Genes that differ between wildtype and delta-DHC mutant",
        parameters={
            "eda_dataset_id": StringValue(value=DATASET),
            "eda_analysis_spec": e2_document(value_variable),
        },
    )


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
        value_entity_id="ENT_fd574cd6",
        value_variable=SENSE_COUNT,
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
