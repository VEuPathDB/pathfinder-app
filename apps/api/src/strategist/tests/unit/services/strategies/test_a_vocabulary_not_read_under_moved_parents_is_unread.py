from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.errors import WDKError

from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.strategy.spec_hydration import StepRead
from strategist.domain.unread import Unread
from strategist.platform.errors import SiteUnavailableError
from strategist.services.strategies import sheet_params
from strategist.services.strategies.sheet_params import (
    criterion_sheets,
    read_or_refuse,
    sheets_under_their_parents,
)
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


async def test_a_step_whose_vocabulary_was_not_read_is_unread_and_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sheet_params, "vocabularies_under", _down)
    monkeypatch.setattr(sheet_params, "parents_moved", lambda *_args: True)
    monkeypatch.setattr(sheet_params, "_listed_under", _transcript)
    published = sheet_of(
        suite_search("search_genes_by_ortholog_pattern").parameters or []
    )
    step = StepRead(
        node=StrategyStepNode(id="step_profile", search_name=_PATTERN),
        names=frozenset({"organism"}),
    )

    reads = await sheets_under_their_parents(
        site_id="plasmodb", steps=[step], sheets={_PATTERN: published}
    )

    assert reads == {"step_profile": _NOT_READ}
    with pytest.raises(SiteUnavailableError) as refused:
        read_or_refuse("plasmodb", reads)
    assert refused.value.detail == (
        f"Could not connect to plasmodb (step_profile: {_NOT_READ.reason})."
    )


async def _transcript(_site: str, _search: str) -> str:
    return "transcript"


_NOT_READ = Unread(
    reason=(
        "the vocabulary under the values it holds was not read: HTTP 503: "
        "VEuPathDB service error: Service Unavailable"
    )
)
