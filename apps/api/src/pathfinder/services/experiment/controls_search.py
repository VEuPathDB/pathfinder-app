"""The search that reads a control id list on the record type of a tested step."""

from __future__ import annotations

from veupathdb_mcp.controls import ControlsSearch

from pathfinder.services.gene_sets.homes import ID_LIST_SEARCHES, IdListSearch

_BY_RECORD_TYPE = {
    search.record_type: search
    for search in [
        *ID_LIST_SEARCHES.values(),
        IdListSearch("group", "GroupsByNameList", "group_names"),
    ]
}


def controls_search(record_type: str) -> ControlsSearch:
    held = _BY_RECORD_TYPE.get(record_type)
    if held is None:
        return ControlsSearch()
    return ControlsSearch(
        search_name=held.search_name,
        param_name=held.param_name,
        record_type=held.record_type,
    )


__all__ = ["controls_search"]
