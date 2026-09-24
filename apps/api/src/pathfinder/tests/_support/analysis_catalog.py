"""The site's catalog as the analysis-kind stamp reads it: a search and its query."""

from __future__ import annotations

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    COMPUTE_QUERY,
    EDA_ANALYSIS_SPEC_PARAM,
    EDA_DATASET_ID_PARAM,
    SUBSET_QUERY,
)

from pathfinder.services.eda import analysis_kinds

DESEQ_SEARCH = "GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq"
WGCNA_SEARCH = (
    "GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCWGCNAModules"
)
UNREADABLE_SEARCH = "GenesByNothing"
# The query that declares the analysis parameter and never reads it.
_WGCNA_QUERY = "GenesByWGCNAModule"
_NO_SUCH_SEARCH = WDKError("no such search", status=404)

# The query each EDA-backed search runs, as the site's catalog lists it.
QUERIES = {
    DESEQ_SEARCH: COMPUTE_QUERY,
    COMPUTE_QUERY: COMPUTE_QUERY,
    SUBSET_QUERY: SUBSET_QUERY,
    WGCNA_SEARCH: _WGCNA_QUERY,
}


# The record type the catalog lists each search under.
RECORD_TYPES = {
    **dict.fromkeys(QUERIES, "transcript"),
    UNREADABLE_SEARCH: "transcript",
}


def definition_of(search_name: str) -> WDKSearch:
    """The catalog's definition: an EDA-backed search carries both parameters."""
    eda = search_name in QUERIES
    return WDKSearch.model_validate(
        {
            "urlSegment": search_name,
            "displayName": search_name,
            "queryName": QUERIES.get(search_name, search_name),
            "paramNames": (
                [EDA_DATASET_ID_PARAM, EDA_ANALYSIS_SPEC_PARAM] if eda else ["organism"]
            ),
        }
    )


def serve_the_catalog(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Serve each definition to the stamp, and record which searches it read."""
    read: list[str] = []

    async def _record_type(
        _site: str, search_name: str, record_type: str | None
    ) -> str:
        """A known record type answers; else the record type that lists the search."""
        if record_type:
            return record_type
        return RECORD_TYPES[search_name]

    async def _definition(_site: str, _record: str, search_name: str) -> WDKSearch:
        read.append(search_name)
        if search_name == UNREADABLE_SEARCH:
            raise _NO_SUCH_SEARCH
        return definition_of(search_name)

    monkeypatch.setattr(analysis_kinds, "resolve_search_record_type", _record_type)
    monkeypatch.setattr(analysis_kinds, "read_search_definition", _definition)
    return read
