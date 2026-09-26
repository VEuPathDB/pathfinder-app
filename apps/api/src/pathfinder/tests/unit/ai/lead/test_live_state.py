"""The live read asks the site, so a hand edit cannot leave a stale count behind.

A researcher edits a step in the graph editor. The edited step's stored
estimate is blanked and every ancestor keeps the estimate it had before the
edit, so the counts the last build wrote describe a strategy that no longer
exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from veupathdb.domain.parameters import NumberValue, SinglePickValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails

from pathfinder.ai.lead.live_state import read_live_state
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import live_counts
from pathfinder.services.strategies.sync_state import WDKSyncState

_ROOT = "step_c42ab304"
_SU = "step_079c277b"
_TEXT = "step_2fc10a11"

_WDK_STRATEGY_ID = 330_423_363
_WDK_STEP_IDS = {_ROOT: 900_003, _TEXT: 900_001, _SU: 900_002}
# What the last build wrote, and what the editor's save left behind.
_STORED_COUNTS: dict[str, int | None] = {_ROOT: 15, _TEXT: 2122, _SU: None}
# What the site holds after the percentile moved from 80 to 90.
_SITE_SIZES: dict[int, int | None] = {900_003: 7, 900_001: 2122, 900_002: 752}


def _details(sizes: dict[int, int | None]) -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": _WDK_STRATEGY_ID,
            "name": "Gametocyte kinases",
            "rootStepId": _WDK_STEP_IDS[_ROOT],
            "stepTree": {"stepId": _WDK_STEP_IDS[_ROOT]},
            "steps": {
                str(wdk_id): {
                    "id": wdk_id,
                    "searchName": "GenesByText",
                    "searchConfig": {"parameters": {}},
                    "estimatedSize": size,
                }
                for wdk_id, size in sizes.items()
            },
        }
    )


_SITE_ID = "plasmodb"


def _install(monkeypatch: pytest.MonkeyPatch, api: StrategyAPI) -> None:
    monkeypatch.setattr(live_counts, "get_strategy_api", lambda _site_id: api)


def _site(sizes: dict[int, int | None]) -> StrategyAPI:
    api = Mock(spec=StrategyAPI)
    api.get_strategy = AsyncMock(return_value=_details(sizes))
    return api


def _unreachable_site() -> StrategyAPI:
    api = Mock(spec=StrategyAPI)
    api.get_strategy = AsyncMock(side_effect=OSError("site down"))
    return api


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Gametocyte kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    root = StrategyStepNode(
        id=_ROOT,
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id=_TEXT,
            search_name="GenesByText",
            display_name="Text search: kinase",
            parameters={"text_expression": SinglePickValue(value="kinase")},
        ),
        secondary_input=StrategyStepNode(
            id=_SU,
            search_name="GenesByRNASeqEvidence",
            # The editor changed the value and left the name it was built with.
            display_name="Su et al. RNA-Seq: top 20%",
            parameters={"min_expression_percentile": NumberValue(value=90)},
        ),
    )
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(_WDK_STEP_IDS),
        step_counts=dict(_STORED_COUNTS),
        wdk_strategy_id=_WDK_STRATEGY_ID,
    )
    return session


async def test_the_root_count_is_the_sites_count_not_the_stored_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _site(_SITE_SIZES))

    live = await read_live_state(_session(), _SITE_ID)

    assert live.root_count == 7
    assert live.wdk_strategy_id == _WDK_STRATEGY_ID
    assert live.step_count == 3


async def test_the_edited_step_reports_the_count_the_site_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _site(_SITE_SIZES))

    live = await read_live_state(_session(), _SITE_ID)

    sizes = {step.step_id: step.estimated_size for step in live.steps}
    assert sizes == {_ROOT: 7, _TEXT: 2122, _SU: 752}
    assert 15 not in sizes.values()


async def test_the_step_reports_the_parameter_value_that_is_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The step's name still says top 20%; its parameter says 90."""
    _install(monkeypatch, _site(_SITE_SIZES))

    live = await read_live_state(_session(), _SITE_ID)

    su = next(step for step in live.steps if step.step_id == _SU)
    assert su.parameters == {"min_expression_percentile": "90"}
    assert su.display_name == "Su et al. RNA-Seq: top 20%"


async def test_an_unanswered_site_leaves_every_count_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A count that cannot be read is unknown, never the count from last time."""
    _install(monkeypatch, _unreachable_site())

    live = await read_live_state(_session(), _SITE_ID)

    assert live.root_count is None
    assert [step.estimated_size for step in live.steps] == [None, None, None]


async def test_a_strategy_the_site_never_saw_has_no_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _site(_SITE_SIZES))
    session = _session()
    session.sync_state = WDKSyncState(step_counts=dict(_STORED_COUNTS))

    live = await read_live_state(session, _SITE_ID)

    assert live.root_count is None
    assert [step.estimated_size for step in live.steps] == [None, None, None]


async def test_a_step_wdk_refused_reports_no_count_and_no_root_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refused step's WDK id still runs the search the edit replaced."""
    _install(monkeypatch, _site(_SITE_SIZES))
    session = _session()
    sync_state = session.sync_state
    assert sync_state is not None
    sync_state.wdk_push_errors[_SU] = "422 min_expression_percentile: Invalid value"
    sync_state.wdk_push_errors[_ROOT] = "422 the join was not rebuilt"

    live = await read_live_state(session, _SITE_ID)

    sizes = {step.step_id: step.estimated_size for step in live.steps}
    assert sizes == {_ROOT: None, _TEXT: 2122, _SU: None}
    assert live.root_count is None


async def test_a_built_strategy_names_each_steps_wdk_id_and_one_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _site(_SITE_SIZES))

    live = await read_live_state(_session(), _SITE_ID)

    assert {step.step_id: step.wdk_step_id for step in live.steps} == _WDK_STEP_IDS
    assert [step.step_id for step in live.steps if step.is_root] == [_ROOT]


async def test_a_strategy_the_site_never_saw_names_no_wdk_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _site(_SITE_SIZES))
    session = _session()
    session.sync_state = WDKSyncState()

    live = await read_live_state(session, _SITE_ID)

    assert [step.wdk_step_id for step in live.steps] == [None, None, None]
    assert [step.step_id for step in live.steps if step.is_root] == [_ROOT]
