"""A step tree WDK accepts is not a strategy WDK can run.

The tree write validates structure only. Whether the steps run is answered by
the read that follows it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.graph_model import flatten_tree
from veupathdb.domain.strategy.validation import StepValidation
from veupathdb.wdk.site_router import SiteInfo
from veupathdb.wdk.strategy_api import StrategyAPI
from veupathdb.wdk.wdk_models import (
    WDKIdentifier,
    WDKStep,
    WDKStrategyDetails,
)

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import sync
from pathfinder.services.strategies.sync import SyncResult, sync_strategy_for_site
from pathfinder.services.strategies.sync_state import WDKSyncState

_WDK_STEP_ID = 1001
_SITE = SiteInfo(
    id="plasmodb",
    name="plasmodb",
    display_name="PlasmoDB",
    base_url="https://plasmodb.org/plasmo/service",
    project_id="PlasmoDB",
    is_portal=False,
)


def _invalid_step() -> WDKStep:
    return WDKStep.model_validate(
        {
            "id": _WDK_STEP_ID,
            "searchName": "GenesByMolecularWeight",
            "searchConfig": {"parameters": {"min_molecular_weight": "abc"}},
            "estimatedSize": None,
            "validation": {
                "level": "RUNNABLE",
                "isValid": False,
                "errors": {
                    "general": [],
                    "byKey": {"min_molecular_weight": ["Not a number."]},
                },
            },
        }
    )


def _details() -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 77,
            "rootStepId": _WDK_STEP_ID,
            "name": "test",
            "stepTree": {"stepId": _WDK_STEP_ID},
            "steps": {str(_WDK_STEP_ID): _invalid_step().model_dump(by_alias=True)},
            "recordClassName": "transcript",
        }
    )


def _recording_api(calls: list[str]) -> StrategyAPI:
    """Accepts any tree and answers the read with an invalid step."""
    api = Mock(spec=StrategyAPI)

    async def create_strategy(*_args: object, **_kwargs: object) -> WDKIdentifier:
        calls.append("create_strategy")
        return WDKIdentifier(id=77)

    async def get_strategy(*_args: object, **_kwargs: object) -> WDKStrategyDetails:
        calls.append("get_strategy")
        return _details()

    api.create_strategy = AsyncMock(side_effect=create_strategy)
    api.get_strategy = AsyncMock(side_effect=get_strategy)
    api.update_strategy = AsyncMock(side_effect=NotImplementedError)
    return api


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    recorded: list[str] = []
    api = _recording_api(recorded)
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(sync, "get_site", lambda _site_id: _SITE)
    return recorded


def _graph() -> StrategyGraph:
    graph = StrategyGraph("g1", "test", "plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(id="A", search_name="GenesByMolecularWeight")
    )
    graph.steps["A"].record_class = "transcript"
    graph.record_type = "transcript"
    graph.recompute_roots()
    return graph


async def _sync(sync_state: WDKSyncState | None = None) -> SyncResult:
    return await sync_strategy_for_site(
        graph=_graph(),
        sync_state=sync_state or WDKSyncState(wdk_step_ids={"A": _WDK_STEP_ID}),
        site_id="plasmodb",
    )


class TestTheWriteIsFollowedByARead:
    @pytest.mark.asyncio
    async def test_the_strategy_is_read_back(self, calls: list[str]) -> None:
        await _sync()

        assert "get_strategy" in calls

    @pytest.mark.asyncio
    async def test_the_read_happens_after_the_write(self, calls: list[str]) -> None:
        await _sync()

        assert calls.index("create_strategy") < calls.index("get_strategy")


class TestTheReadIsWhatReportsValidity:
    @pytest.mark.asyncio
    async def test_an_accepted_tree_can_still_hold_an_invalid_step(
        self, calls: list[str]
    ) -> None:
        # The write raised nothing; the step is unrunnable all the same.
        del calls
        sync_state = WDKSyncState(wdk_step_ids={"A": _WDK_STEP_ID})

        await _sync(sync_state)

        assert sync_state.step_validations["A"].rejects()

    @pytest.mark.asyncio
    async def test_the_rejection_message_is_kept(self, calls: list[str]) -> None:
        del calls
        sync_state = WDKSyncState(wdk_step_ids={"A": _WDK_STEP_ID})

        await _sync(sync_state)

        assert "Not a number." in " ".join(sync_state.step_validations["A"].messages())

    def test_a_validation_that_was_never_checked_does_not_claim_validity(self) -> None:
        assert StepValidation(level="NONE", is_valid=False).was_checked() is False
