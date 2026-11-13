from __future__ import annotations

from assistant_core.platform.types import JSONObject
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp, StrategyAst

MIXED_REFUSAL = (
    "The INTERSECT of step_protein (Proteins) and step_mammals (Ortholog Groups) "
    "joins two record types. WDK combines only steps of one record type, so the "
    "site refuses this combine. Transform Proteins to Groups (GroupsFromSequences) "
    "maps Proteins to Ortholog Groups: put it over step_protein. Transform Groups "
    "to Proteins (FromGroups) maps Ortholog Groups to Proteins: put it over "
    "step_mammals."
)


def mixed_snapshot() -> JSONObject:
    return StrategyAst.model_validate(
        {
            "recordType": "sequence",
            "name": "Trypanothione reductase",
            "root": {
                "id": "step_join",
                "searchName": COMBINE_SEARCH_NAME,
                "operator": CombineOp.INTERSECT,
                "primaryInput": {"id": "step_protein", "searchName": "ByIdList"},
                "secondaryInput": {
                    "id": "step_mammals",
                    "searchName": "GroupsByPhyleticPattern",
                },
            },
            "wdkStepIds": {
                "step_join": 227284910,
                "step_protein": 227284890,
                "step_mammals": 227284900,
            },
        }
    ).model_dump(by_alias=True, exclude_none=True, mode="json")
