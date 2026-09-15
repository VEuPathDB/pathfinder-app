"""A leaf that leaves its EDA analysis empty is refused before the WDK call."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import StrategyStep, StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKIdentifier, WDKSearchConfig, WDKStep
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM, EDA_DATASET_ID_PARAM

from pathfinder.services.strategies import step_wdk_push
from pathfinder.services.strategies.sync_state import WDKSyncState

_DATASET_ID = "DS_70dd50fed7"
_SEARCH = (
    "GenesByPhenotypeEdaSubset_PlasmoDB_pfal3D7_pB_mutagenesis_MIS_MFS_Phenotype_RSRC"
)
_ANALYSIS = '{"studyId":"DS_70dd50fed7","descriptor":{"subset":{"descriptor":[]}}}'
_WDK_STEP_ID = 440185943
_REFUSAL = "EDA-backed step without an analysis"


@dataclass
class RecordingAPI:
    """Records every WDK write and hands back one step id."""

    calls: list[str] = field(default_factory=list)

    async def create_step(self, *_args: Any, **_kw: Any) -> WDKIdentifier:
        self.calls.append("create_step")
        return WDKIdentifier(id=_WDK_STEP_ID)

    async def update_step_search_config(self, **_kw: Any) -> None:
        self.calls.append("update_step_search_config")

    async def update_step_properties(self, **_kw: Any) -> None:
        self.calls.append("update_step_properties")

    async def find_step(self, step_id: int, **_kw: Any) -> WDKStep:
        return WDKStep(
            id=step_id,
            search_name=_SEARCH,
            search_config=WDKSearchConfig(parameters={}),
        )


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> RecordingAPI:
    recorder = RecordingAPI()
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site: recorder)
    return recorder


def _step(spec: str) -> StrategyStep:
    parameters: dict[str, ParamValue] = {
        EDA_DATASET_ID_PARAM: StringValue(value=_DATASET_ID),
        EDA_ANALYSIS_SPEC_PARAM: StringValue(value=spec),
    }
    node = StrategyStepNode(id="step_eda", search_name=_SEARCH, parameters=parameters)
    return flatten_tree(node)["step_eda"]


class TestTheCreateCall:
    async def test_an_empty_analysis_is_refused_and_creates_nothing(
        self, api: RecordingAPI
    ) -> None:
        step = _step("")

        wdk_id, _validation, failure = await step_wdk_push.push_step_to_wdk(
            sync_state=WDKSyncState(),
            step=step,
            site_id="plasmodb",
            record_type="transcript",
            search_name=_SEARCH,
            parameters=step.parameters,
        )

        assert wdk_id is None
        assert failure is not None
        assert failure.step_id == "step_eda"
        assert _REFUSAL in failure.error
        assert "create_eda_step" in failure.error
        assert api.calls == []

    async def test_an_authored_analysis_reaches_the_site(
        self, api: RecordingAPI
    ) -> None:
        step = _step(_ANALYSIS)

        wdk_id, _validation, failure = await step_wdk_push.push_step_to_wdk(
            sync_state=WDKSyncState(),
            step=step,
            site_id="plasmodb",
            record_type="transcript",
            search_name=_SEARCH,
            parameters=step.parameters,
        )

        assert wdk_id == _WDK_STEP_ID
        assert failure is None
        assert api.calls == ["create_step"]


class TestThePatchCall:
    def _sync_state(self) -> WDKSyncState:
        return WDKSyncState(wdk_step_ids={"step_eda": _WDK_STEP_ID})

    async def test_an_empty_analysis_is_refused_and_patches_nothing(
        self, api: RecordingAPI
    ) -> None:
        sync_state = self._sync_state()

        failure = await step_wdk_push._execute_patch(
            sync_state, "plasmodb", _step(""), "transcript", name_moved=False
        )

        assert failure is not None
        assert _REFUSAL in failure.error
        assert sync_state.wdk_push_errors["step_eda"] == failure.error
        assert api.calls == []

    async def test_an_authored_analysis_is_patched(self, api: RecordingAPI) -> None:
        failure = await step_wdk_push._execute_patch(
            self._sync_state(),
            "plasmodb",
            _step(_ANALYSIS),
            "transcript",
            name_moved=False,
        )

        assert failure is None
        assert api.calls == ["update_step_search_config"]
