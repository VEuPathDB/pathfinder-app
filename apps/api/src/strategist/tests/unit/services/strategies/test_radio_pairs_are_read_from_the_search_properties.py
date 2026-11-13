"""The radio pairs of each search are read from the properties it publishes."""

from __future__ import annotations

from collections.abc import Collection

import pytest
from veupathdb.wdk import WDKSearch

from strategist.services.strategies import search_sheets
from strategist.services.strategies.search_sheets import radio_pairs_of
from strategist.tests._support.recorded_searches import suite_search

_INTERPRO = "GenesByInterproDomain"
_TEXT = "GenesByText"


@pytest.fixture(autouse=True)
def _catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _listed(_site_id: str, names: Collection[str]) -> dict[str, str]:
        return {name: "transcript" for name in names if name in (_INTERPRO, _TEXT)}

    async def _read(_site_id: str, _record_type: str, search_name: str) -> WDKSearch:
        fixture = {
            _INTERPRO: "search_genes_by_interpro_domain",
            _TEXT: "search_genes_by_text",
        }[search_name]
        return suite_search(fixture)

    monkeypatch.setattr(search_sheets, "search_record_types", _listed)
    monkeypatch.setattr(search_sheets, "read_search_definition", _read)


async def test_a_search_that_declares_a_pair_names_its_halves() -> None:
    pairs = await radio_pairs_of("plasmodb", [_INTERPRO, _TEXT, "GenesUnlisted"])

    assert pairs == {_INTERPRO: {"domain_typeahead": "domain_accession"}}
