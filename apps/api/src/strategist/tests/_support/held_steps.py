from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from veupathdb.domain.parameters import wire_map
from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

BOOLEAN_SEARCH = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"
SPAN_SEARCH = "GenesBySpanLogic"
LEAF_DEFAULT = {
    "name": "matched_transcript_filter_array",
    "value": {"values": ["Y"]},
    "disabled": False,
}
BOOLEAN_DEFAULTS = {
    "INTERSECT": {"values": ["YY"]},
    "UNION": {"values": ["YY", "YN", "NY"]},
    "MINUS": {"values": ["YN"]},
}


def default_filters(
    search_name: str, parameters: dict[str, str]
) -> list[dict[str, Any]]:
    if search_name == BOOLEAN_SEARCH:
        value = BOOLEAN_DEFAULTS.get(parameters.get("bq_operator", ""))
        if value is None:
            return []
        return [
            {"name": "gene_boolean_filter_array", "value": value, "disabled": False}
        ]
    if search_name == SPAN_SEARCH:
        return []
    return [copy.deepcopy(LEAF_DEFAULT)]


def held_config(search_name: str, config: dict[str, Any]) -> dict[str, Any]:
    sent = list(config.get("filters") or [])
    named = {f["name"] for f in sent}
    parameters = dict(config.get("parameters") or {})
    defaults = default_filters(search_name, parameters)
    return {
        "parameters": parameters,
        "filters": sent + [f for f in defaults if f["name"] not in named],
        "wdkWeight": config.get("wdkWeight", 0),
    }


def held_step(wdk_id: int, step: StrategyStep) -> dict[str, Any]:
    if step.kind is StepKind.COMBINE and step.operator is CombineOp.COLOCATE:
        search = SPAN_SEARCH
        parameters = (
            step.colocation_params.to_wdk_params() if step.colocation_params else {}
        )
    elif step.kind is StepKind.COMBINE:
        search = BOOLEAN_SEARCH
        parameters = {"bq_operator": step.operator.value if step.operator else ""}
    else:
        search = step.search_name or ""
        parameters = wire_map(step.parameters)
    config = {
        "parameters": parameters,
        "filters": [f.model_dump(by_alias=True, mode="json") for f in step.filters],
        "wdkWeight": step.wdk_weight or 0,
    }
    return {
        "id": wdk_id,
        "searchName": search,
        "searchConfig": held_config(search, config),
        "customName": step.display_name,
        "expanded": step.expanded_strategy_id is not None,
        "expandedName": step.expanded_name,
        "displayPreferences": {},
    }


def tree_of(
    step_id: str, steps: Mapping[str, StrategyStep], ids: Mapping[str, int]
) -> dict[str, Any] | None:
    step = steps[step_id]
    inputs = [
        tree_of(sid, steps, ids)
        for sid in (step.primary_input_id, step.secondary_input_id)
        if sid is not None
    ]
    if step_id not in ids:
        return next((tree for tree in inputs if tree is not None), None)
    slots = zip(("primaryInput", "secondaryInput"), inputs, strict=False)
    return {"stepId": ids[step_id]} | {
        slot: sub for slot, sub in slots if sub is not None
    }
