from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.errors import WDKError

from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.unread import Unread
from strategist.services.strategies import sheet_params
from strategist.services.strategies.sheet_params import criterion_sheets
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.recorded_searches import suite_search

_PATTERN = "GenesByOrthologPattern"
_DOWN = WDKError("Service Unavailable", status=503)


async def _down(*_args: object) -> NoReturn:
    raise _DOWN


async def test_a_vocabulary_the_site_did_not_read_under_moved_parents_is_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sheet_params, "vocabularies_under", _down)
    monkeypatch.setattr(sheet_params, "parents_moved", lambda *_args: True)
    published = sheet_of(
        suite_search("search_genes_by_ortholog_pattern").parameters or []
    )
    criterion = Criterion(
        id="c_profile", text="t", search_name=_PATTERN, record_class="transcript"
    )

    sheets = await criterion_sheets("plasmodb", [criterion], {_PATTERN: published})

    assert sheets == {
        "c_profile": Unread(
            reason=(
                "the vocabulary under the values it holds was not read: HTTP 503: "
                "VEuPathDB service error: Service Unavailable"
            )
        )
    }
