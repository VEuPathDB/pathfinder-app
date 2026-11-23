from __future__ import annotations

from typing import Any

from veupathdb.domain.strategy import StrategyAst

from strategist.domain.eda_parts import EdaAnalysisState

PRIVATE_DATASET_ID = "330713643"
WDK_STRATEGY_ID = 40123
UPLOADED_STUDY = "EDAUD_sF88g1cwo00gw"

SHARED_AST = StrategyAst.model_validate(
    {
        "recordType": "transcript",
        "root": {
            "id": "s-both",
            "operator": "INTERSECT",
            "primaryInput": {
                "id": "s-list",
                "searchName": "GeneByLocusTag",
                "displayName": "Gene set: 3D7 strain gaps",
                "parameters": {
                    "ds_gene_ids": {
                        "type": "input-dataset",
                        "datasetId": PRIVATE_DATASET_ID,
                    }
                },
            },
            "secondaryInput": {
                "id": "s-text",
                "searchName": "GenesByText",
                "parameters": {
                    "text_expression": {"type": "string", "value": "kinase"}
                },
            },
        },
        "stepCounts": {"s-list": 41, "s-text": 1204, "s-both": 12},
        "wdkStepIds": {"s-list": 900117, "s-text": 900118, "s-both": 900119},
    }
)

STATE = EdaAnalysisState(
    site_id="plasmodb",
    dataset_id="DS_53f554ec6a",
    study_id="STUDY_53f554ec6a",
    analysis_id="a-1",
    revision=1,
    study_display_name="Rodent malaria phenotypes",
    display_name="berghei subset",
    num_filters=0,
    num_computations=0,
    filters=[],
    filter_summaries=[],
    entity_counts=[],
    can_export_rows=False,
)


def state_chunk(
    analysis_id: str, *, revision: int, dataset_id: str = STATE.dataset_id
) -> dict[str, Any]:
    state = STATE.model_copy(
        update={
            "analysis_id": analysis_id,
            "revision": revision,
            "dataset_id": dataset_id,
            "analysis_url": f"https://qa.plasmodb.org/eda/{analysis_id}",
        }
    )
    return {
        "type": "data-eda.analysis-state",
        "id": analysis_id,
        "data": state.model_dump(by_alias=True, mode="json"),
    }
