"""Strategy ASTs the thread-surgery tests build threads from."""

from __future__ import annotations

from assistant_core.platform.types import JSONObject
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.strategy_ast import StrategyAst

ORGANISM = "Plasmodium falciparum 3D7"


def leaf(step_id: str, text: str) -> StrategyStepNode:
    return StrategyStepNode.model_validate(
        {
            "id": step_id,
            "searchName": "GenesByText",
            "parameters": {
                "text_expression": {"type": "string", "value": text},
                "text_search_organism": {
                    "type": "multi-pick-vocabulary",
                    "values": [ORGANISM],
                },
            },
        },
    )


def three_step_ast(wdk_step_ids: JSONObject | None = None) -> StrategyAst:
    """An INTERSECT over two leaves: three steps, root ``combine``."""
    payload: JSONObject = {
        "recordType": "transcript",
        "name": "protease work",
        "root": {
            "id": "combine",
            "operator": "INTERSECT",
            "primaryInput": leaf("protease", "protease").model_dump(by_alias=True),
            "secondaryInput": leaf("gameto", "gametocyte").model_dump(by_alias=True),
        },
    }
    if wdk_step_ids is not None:
        payload["wdkStepIds"] = wdk_step_ids
        payload["stepCounts"] = dict.fromkeys(wdk_step_ids, 15)
    return StrategyAst.model_validate(payload)


def four_step_ast(wdk_step_ids: JSONObject | None = None) -> StrategyAst:
    """The three-step tree under a P. vivax ortholog transform: four steps."""
    three = three_step_ast()
    payload: JSONObject = {
        "recordType": "transcript",
        "name": "protease work",
        "root": {
            "id": "orthologs",
            "searchName": "GenesByOrthologs",
            "parameters": {
                "organism": {
                    "type": "multi-pick-vocabulary",
                    "values": ["Plasmodium vivax"],
                },
            },
            "primaryInput": three.root.model_dump(by_alias=True),
        },
    }
    if wdk_step_ids is not None:
        payload["wdkStepIds"] = wdk_step_ids
        payload["stepCounts"] = dict.fromkeys(wdk_step_ids, 16)
    return StrategyAst.model_validate(payload)
