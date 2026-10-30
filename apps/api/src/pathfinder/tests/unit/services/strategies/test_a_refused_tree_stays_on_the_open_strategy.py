from __future__ import annotations

from http import HTTPStatus

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStepTree, WDKStrategyDetails, build_wdk_step_tree

from pathfinder.domain.strategy.operations import DeleteResolution, DeleteStepOp
from pathfinder.services.strategies import commit, sync
from pathfinder.services.strategies.commit import CommitResult, apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)

_STRATEGY = 42
_IDS = {"step_a": 227290990, "step_b": 227291000, "step_join": 227291010}
_REFUSAL = "227291000 is not a valid step ID."


class _RefusingSite(StubAPI):
    async def update_strategy(
        self,
        strategy_id: int,
        step_tree: WDKStepTree | None = None,
        name: str | None = None,
        user_id: str | None = None,
    ) -> WDKStrategyDetails:
        del user_id
        self._record(
            "update_strategy", strategy_id=strategy_id, step_tree=step_tree, name=name
        )
        raise WDKError(_REFUSAL, status=HTTPStatus.UNPROCESSABLE_ENTITY)


class _ListingSite(StubAPI):
    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        survivor = _IDS["step_a"]
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": strategy_id,
                "name": "Test",
                "rootStepId": survivor,
                "stepTree": {"stepId": survivor},
                "steps": {
                    str(survivor): {
                        "id": survivor,
                        "searchName": "GenesWithSignalPeptide",
                        "searchConfig": {"parameters": {}},
                        "estimatedSize": 479,
                    }
                },
            }
        )


def _pushed_join() -> WDKSyncState:
    root = combine("step_join", leaf("step_a"), leaf("step_b"))
    return WDKSyncState(
        wdk_step_ids=dict(_IDS),
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=build_wdk_step_tree(root, _IDS),
    )


async def _delete_b(
    monkeypatch: pytest.MonkeyPatch, api: StubAPI
) -> tuple[CommitResult, WDKSyncState]:
    for module in (commit, sync):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr(commit, "sync_strategy_for_site", sync.sync_strategy_for_site)

    async def _no_marks(*_args: object) -> dict[str, str]:
        return {}

    monkeypatch.setattr(sync, "tree_organism_parameters", _no_marks)
    root = combine("step_join", leaf("step_a"), leaf("step_b"))
    session = session_with(root, dict(_IDS))
    state = ensure_sync_state(session)
    state.wdk_step_tree = build_wdk_step_tree(root, _IDS)
    assert session.graph is not None
    for step in session.graph.steps.values():
        step.record_class = "transcript"
    result = await apply_and_commit(
        deps=StrategyMutationContext(site_id="plasmodb", strategy_session=session),
        op=DeleteStepOp(step_id="step_b", resolution=DeleteResolution.COLLAPSE_COMBINE),
    )
    return result, state


async def test_a_delete_puts_the_tree_without_the_step_and_drops_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    api = _ListingSite()

    result, state = await _delete_b(monkeypatch, api)

    trees = [c.kwargs["step_tree"] for c in api.named("update_strategy")]
    assert trees == [WDKStepTree(step_id=_IDS["step_a"])]
    assert api.step_ids("delete_step") == {_IDS["step_b"], _IDS["step_join"]}
    assert (result.failures, state.wdk_strategy_id) == ([], _STRATEGY)


async def test_a_refused_delete_is_reported_against_the_open_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _RefusingSite()
    install_stub_api(monkeypatch)

    result, state = await _delete_b(monkeypatch, api)

    assert [(f.step_id, f.error) for f in result.failures] == [
        (
            "step_a",
            f"PlasmoDB (Plasmodium) did not take the strategy's steps: {_REFUSAL}",
        )
    ]
    assert api.named("create_strategy") == []
    assert state.wdk_strategy_id == _STRATEGY
    assert state.wdk_step_tree == _pushed_join().wdk_step_tree
