from __future__ import annotations

from datetime import date

import pytest
from veupathdb.domain.parameters import InputDatasetValue, ParamValue, StringValue
from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.wdk import WDKStepTree, WDKStrategyDetails, build_wdk_step_tree

from pathfinder.domain.strategy.computed_groups import (
    SNAPSHOT_NOTE,
    HeldComparison,
    noted_description,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import spec_build, sync
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.computed_comparison import PATTERN, held_comparison
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)

_DATASET = "202394260"
_MINE = "Groups for the grant figure."
_IDS = {"step_a": 440537303, "step_b": 440537313, "step_join": 440537323}


def _spec(value: ParamValue) -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_groups",
                text="groups with more proteins per genome in the left set",
                search_name="GroupsByNameList",
                resolved_params={
                    "group_names": BoundValue(value=value, source="chosen")
                },
            )
        ]
    )


def _held(dataset_id: str | None) -> dict[str, HeldComparison]:
    held = held_comparison(PATTERN, date(2026, 10, 25)).model_copy(
        update={"dataset_id": dataset_id}
    )
    return {held.handle: held}


_SAVED = _spec(InputDatasetValue(dataset_id=_DATASET))


@pytest.mark.parametrize(
    ("described", "noted"),
    [
        (None, SNAPSHOT_NOTE),
        ("  ", SNAPSHOT_NOTE),
        (_MINE, f"{_MINE} {SNAPSHOT_NOTE}"),
        (f"{_MINE} {SNAPSHOT_NOTE}", f"{_MINE} {SNAPSHOT_NOTE}"),
    ],
)
def test_a_saved_comparison_adds_the_note_once(
    described: str | None, noted: str
) -> None:
    assert noted_description(described, _held(_DATASET), _SAVED) == noted


@pytest.mark.parametrize(
    ("dataset_id", "spec"),
    [
        (None, _spec(StringValue(value="OG7_0000001"))),
        (_DATASET, _spec(InputDatasetValue(dataset_id="1"))),
    ],
)
def test_a_spec_on_no_saved_comparison_keeps_the_description(
    dataset_id: str | None, spec: OperationalSpec
) -> None:
    assert noted_description(_MINE, _held(dataset_id), spec) == _MINE


async def test_the_build_creates_the_strategy_with_its_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = install_stub_api(monkeypatch)

    async def _quiet(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(spec_build, "defer_the_gene_set_refresh", _quiet)
    monkeypatch.setattr(
        spec_build, "sync_strategy_for_site", sync.sync_strategy_for_site
    )
    graph = StrategyGraph("g1", "Groups", "plasmodb")
    graph.record_type = "transcript"
    session = StrategySession(site_id="plasmodb")
    session.graph = graph

    await build_strategy_from_spec(
        deps=StrategyMutationContext(site_id="plasmodb", strategy_session=session),
        root=leaf("step_a", {"organism": StringValue(value="P. falciparum 3D7")}),
        description=SNAPSHOT_NOTE,
    )

    assert [c.kwargs["description"] for c in api.named("create_strategy")] == [
        SNAPSHOT_NOTE
    ]


class _RefusedUpdate(StubAPI):
    async def update_strategy(
        self,
        strategy_id: int,
        step_tree: WDKStepTree | None = None,
        name: str | None = None,
        user_id: str | None = None,
    ) -> WDKStrategyDetails:
        del strategy_id, step_tree, name, user_id
        raise VEuPathDBError(VEuPathDBErrorCode.WDK_ERROR, "strategy is gone")


async def _pushed(
    monkeypatch: pytest.MonkeyPatch, api: StubAPI, state: WDKSyncState
) -> list[object]:
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site: api)
    session = session_with(combine("step_join", leaf("step_a"), leaf("step_b")), _IDS)
    assert session.graph is not None
    session.graph.description = SNAPSHOT_NOTE
    for step in session.graph.steps.values():
        step.record_class = "transcript"
    await sync.sync_strategy_for_site(
        graph=session.graph, sync_state=state, site_id="plasmodb", strategy_name="G"
    )
    return [c.kwargs["description"] for c in api.named("create_strategy")]


async def test_a_first_push_sends_the_graphs_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = WDKSyncState(wdk_step_ids=dict(_IDS))

    assert await _pushed(monkeypatch, StubAPI(), state) == [SNAPSHOT_NOTE]


async def test_a_create_after_a_refused_update_sends_the_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = combine("step_join", leaf("step_b"), leaf("step_a"))
    state = WDKSyncState(
        wdk_step_ids=dict(_IDS),
        wdk_strategy_id=42,
        wdk_step_tree=build_wdk_step_tree(other, _IDS),
    )

    assert await _pushed(monkeypatch, _RefusedUpdate(), state) == [SNAPSHOT_NOTE]
