"""The parameters a search's sheet shows, read from the catalog."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKSearch

from pathfinder.services.strategies import sheet_params
from pathfinder.services.strategies.sheet_params import sheet_params_for_searches
from pathfinder.tests._support.record_classes import list_searches_under

_SEARCH = "GenesByRNASeqpfal3D7_Su_seven_stages_rnaSeq_RSRC"
_NO_SUCH_SEARCH = WDKError("no such search", status=404)


def _search_with_a_hidden_parameter() -> WDKSearch:
    return WDKSearch.model_validate(
        {
            "urlSegment": _SEARCH,
            "displayName": "RNA-seq evidence",
            "shortDisplayName": "RNA-seq",
            "parameters": [
                {
                    "name": "profileset_generic",
                    "displayName": "Data set",
                    "type": "string",
                    "isVisible": True,
                    "initialDisplayValue": "",
                },
                {
                    "name": "dataset_url",
                    "displayName": "Data set URL",
                    "type": "string",
                    "isVisible": False,
                    "initialDisplayValue": "https://qa.plasmodb.org/a/app/record/x",
                },
            ],
        }
    )


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _definition(*_args: Any, **_kwargs: Any) -> WDKSearch:
        return _search_with_a_hidden_parameter()

    list_searches_under(monkeypatch, "transcript", [_SEARCH])
    monkeypatch.setattr(sheet_params, "read_search_definition", _definition)


@pytest.mark.usefixtures("catalog")
async def test_the_sheet_names_the_visible_parameters_only() -> None:
    sheets = await sheet_params_for_searches(site_id="plasmodb", search_names=[_SEARCH])

    assert {name: [i.name for i in infos] for name, infos in sheets.items()} == {
        _SEARCH: ["profileset_generic"]
    }


async def test_a_search_the_catalog_cannot_read_is_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refused(*_args: Any, **_kwargs: Any) -> WDKSearch:
        raise _NO_SUCH_SEARCH

    list_searches_under(monkeypatch, "transcript", [_SEARCH])
    monkeypatch.setattr(sheet_params, "read_search_definition", _refused)

    sheets = await sheet_params_for_searches(site_id="plasmodb", search_names=[_SEARCH])

    assert sheets == {}


async def test_a_search_listed_under_no_record_type_has_no_sheet_and_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read: list[str] = []
    warned: list[tuple[str, str]] = []

    async def _definition(_site: str, record_type: str, name: str) -> WDKSearch:
        read.append(record_type)
        return _search_with_a_hidden_parameter()

    class _Logger:
        def warning(self, event: str, **fields: str) -> None:
            warned.append((event, fields["search_name"]))

    list_searches_under(monkeypatch, "transcript", [])
    monkeypatch.setattr(sheet_params, "read_search_definition", _definition)
    monkeypatch.setattr(sheet_params, "logger", _Logger())

    sheets = await sheet_params_for_searches(site_id="plasmodb", search_names=[_SEARCH])

    assert (sheets, read, warned) == (
        {},
        [],
        [("the site lists no record type for the search", _SEARCH)],
    )
