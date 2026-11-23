from __future__ import annotations

from typing import Any

from veupathdb.domain.strategy import StrategyAst

from strategist.domain.eda_parts import EdaAnalysisState
from strategist.tests.unit.domain.strategy._analysis import (
    COMPUTE_SEARCH,
    DATASET,
    E2_DOCUMENT,
)

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
                "filters": [
                    {"name": "gene_list_filter", "value": {"ids": PRIVATE_DATASET_ID}}
                ],
                "analyses": [
                    {
                        "analysisType": "go-enrichment",
                        "parameters": {"background": PRIVATE_DATASET_ID},
                    }
                ],
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
        "stepValidations": {
            "s-list": {
                "level": "SEMANTIC",
                "isValid": False,
                "errors": {
                    "general": [f"Dataset {PRIVATE_DATASET_ID} does not exist."],
                    "byKey": {"ds_gene_ids": [f"'{PRIVATE_DATASET_ID}' is invalid."]},
                },
            }
        },
        "wdkPushErrors": {"s-list": f"Dataset {PRIVATE_DATASET_ID} was not found."},
        "metadata": {
            "rationales": {
                "s-list": {
                    "kind": "search",
                    "searchName": "GeneByLocusTag",
                    "basis": "parameter",
                    "term": "Gene ID list",
                    "reason": f"It reads the saved list {PRIVATE_DATASET_ID}.",
                    "toolCallId": "c-1",
                    "derivedFrom": {"ds_gene_ids": PRIVATE_DATASET_ID},
                }
            }
        },
    }
)

UPLOAD_AST = StrategyAst.model_validate(
    {
        "recordType": "transcript",
        "root": {
            "id": "s-upload",
            "searchName": COMPUTE_SEARCH,
            "displayName": "Genes up in my upload",
            "parameters": {
                "eda_dataset_id": {"type": "string", "value": UPLOADED_STUDY},
                "eda_analysis_spec": {
                    "type": "string",
                    "value": E2_DOCUMENT.replace(DATASET, UPLOADED_STUDY),
                },
            },
        },
        "stepCounts": {"s-upload": 230},
        "metadata": {
            "analysisKinds": {
                "s-upload": {"searchName": COMPUTE_SEARCH, "kind": "compute"}
            }
        },
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
