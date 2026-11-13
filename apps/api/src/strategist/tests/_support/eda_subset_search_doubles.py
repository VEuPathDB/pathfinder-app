from __future__ import annotations

import json
from pathlib import Path

import pytest
from veupathdb.domain import SearchContext
from veupathdb.wdk import WDKSearch, WDKSearchResponse
from veupathdb_mcp.catalog import EdaBackedSearch, eda_backed_search

from strategist.services.eda import dataset_searches
from strategist.tests._support.qa_recording import qa_recording

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "wdk"

PHENOTYPE_SUBSET_SEARCH = "GenesByPhenotypeEdaSubset_PlasmoDB_Rod_Mal_Phenotype_RSRC"


class _Definitions:
    def __init__(self, by_name: dict[str, WDKSearch]) -> None:
        self.by_name = by_name
        self.asked: list[str] = []

    async def get_search_details(self, ctx: SearchContext) -> WDKSearchResponse:
        self.asked.append(ctx.search_name)
        return WDKSearchResponse.model_validate(
            {
                "searchData": self.by_name[ctx.search_name].model_dump(
                    by_alias=True, mode="json"
                ),
                "validation": {"level": "DISPLAYABLE", "isValid": True},
            }
        )


def serve_plasmodb_subset_searches(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    raw = json.loads(
        qa_recording(_FIXTURES / "eda_subset_searches_plasmodb.json").read_text()
    )
    by_name = {e["urlSegment"]: WDKSearch.model_validate(e) for e in raw}
    definitions = _Definitions(by_name)

    async def listed(site_id: str) -> list[EdaBackedSearch]:
        del site_id
        return [
            found
            for search in by_name.values()
            if (found := eda_backed_search(search)) is not None
        ]

    monkeypatch.setattr(dataset_searches, "list_eda_backed", listed)
    monkeypatch.setattr(dataset_searches, "get_discovery_service", lambda: definitions)
    return definitions.asked
