from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode
from veupathdb.errors import WDKError
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails
from veupathdb_mcp.wdk import WireStep

from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.unread import Unread
from strategist.services.strategies import live_counts, site_changes
from strategist.services.strategies.live_counts import read_the_live_strategy
from strategist.services.strategies.site_changes import (
    SiteEdits,
    take_the_sites_edits,
    take_what_the_site_holds,
)
from strategist.services.strategies.sync_state import WDKSyncState

_DOWN = WDKError("Service Unavailable", status=503)
_SAID = "HTTP 503: VEuPathDB service error: Service Unavailable"


class _Unanswering:
    async def get_strategy(self, strategy_id: int) -> NoReturn:
        del strategy_id
        raise _DOWN


def _synced() -> WDKSyncState:
    return WDKSyncState(wdk_strategy_id=9, wdk_step_ids={"step_a": 77})


def _live() -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 9,
            "name": "kinases",
            "rootStepId": 77,
            "recordClassName": "transcript",
            "stepTree": {"stepId": 77},
            "steps": {},
        }
    )


async def test_an_unanswered_read_is_unread_and_no_strategy_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_counts, "get_strategy_api", lambda _site: _Unanswering())

    assert (
        await read_the_live_strategy(_synced(), "plasmodb"),
        await read_the_live_strategy(WDKSyncState(), "plasmodb"),
    ) == (Unread(reason=f"the strategy was not read from the site: {_SAID}"), None)


async def test_edits_the_site_did_not_answer_are_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_counts, "get_strategy_api", lambda _site: _Unanswering())

    edits = await take_the_sites_edits(
        graph=StrategyGraph("g1", "kinases", "plasmodb"),
        sync_state=_synced(),
        site_id="plasmodb",
    )

    assert edits == SiteEdits(
        not_read=Unread(reason=f"the strategy was not read from the site: {_SAID}")
    )


def _unreadable(_live: WDKStrategyDetails) -> NoReturn:
    msg = "a step kind the snapshot does not read"
    raise ValueError(msg)


async def test_a_site_tree_the_snapshot_cannot_read_is_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(site_changes, "build_snapshot_from_wdk", _unreadable)

    edits = await take_what_the_site_holds(
        graph=StrategyGraph("g1", "kinases", "plasmodb"),
        sync_state=_synced(),
        site_id="plasmodb",
        live=_live(),
    )

    assert edits == SiteEdits(
        not_read=Unread(
            reason="the site's tree was not read: a step kind the snapshot does not read"
        )
    )


async def _undecoded(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, WireStep]
) -> NoReturn:
    del payload, api, wire
    raise _DOWN


async def test_steps_the_site_added_that_do_not_decode_are_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _undecoded)
    monkeypatch.setattr(site_changes, "get_strategy_api", lambda _site: None)
    node = StrategyStepNode(id="77", search_name="GenesByText")
    tree = site_changes._SiteTree(
        ast=StrategyAst(record_type="transcript", root=node),
        wire={"77": WireStep(record_class="transcript", parameters={"q": "kinase"})},
    )

    decoded = await site_changes._arrivals_decoded(tree, {"77": node}, "plasmodb")

    assert decoded == Unread(reason=f"the steps the site added did not decode: {_SAID}")
