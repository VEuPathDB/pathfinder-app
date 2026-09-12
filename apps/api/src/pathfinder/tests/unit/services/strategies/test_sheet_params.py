"""The parameter names a search's sheet shows, read from the catalog."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKSearch

from pathfinder.services.strategies import sheet_params
from pathfinder.services.strategies.sheet_params import sheet_params_for_searches

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
                    "initialDisplayValue": "https://plasmodb.org/a/app/record/x",
                },
            ],
        }
    )


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _record_type(*_args: Any, **_kwargs: Any) -> str:
        return "transcript"

    async def _definition(*_args: Any, **_kwargs: Any) -> WDKSearch:
        return _search_with_a_hidden_parameter()

    monkeypatch.setattr(sheet_params, "resolve_search_record_type", _record_type)
    monkeypatch.setattr(sheet_params, "read_search_definition", _definition)


@pytest.mark.usefixtures("catalog")
async def test_the_sheet_names_the_visible_parameters_only() -> None:
    sheets = await sheet_params_for_searches(
        site_id="plasmodb", record_type="transcript", search_names=[_SEARCH]
    )

    assert sheets == {_SEARCH: frozenset({"profileset_generic"})}


async def test_a_search_the_catalog_cannot_read_is_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _record_type(*_args: Any, **_kwargs: Any) -> str:
        return "transcript"

    async def _refused(*_args: Any, **_kwargs: Any) -> WDKSearch:
        raise _NO_SUCH_SEARCH

    monkeypatch.setattr(sheet_params, "resolve_search_record_type", _record_type)
    monkeypatch.setattr(sheet_params, "read_search_definition", _refused)

    sheets = await sheet_params_for_searches(
        site_id="plasmodb", record_type="transcript", search_names=[_SEARCH]
    )

    assert sheets == {}
