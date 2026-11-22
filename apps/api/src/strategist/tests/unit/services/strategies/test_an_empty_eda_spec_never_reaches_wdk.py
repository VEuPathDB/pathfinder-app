"""A leaf that leaves its EDA analysis empty is refused before the WDK call."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import (
    StrategyStepNode,
)
from veupathdb.wdk import WDKIdentifier, WDKSearchConfig, WDKStep
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM, EDA_DATASET_ID_PARAM

from strategist.services.strategies.step_push_planner import PatchAction
from strategist.tests._support.wdk_write_stubs import commit_against

_VALUES = PatchAction(search_config=True, name=False)

_DATASET_ID = "DS_70dd50fed7"
_SEARCH = (
    "GenesByPhenotypeEdaSubset_PlasmoDB_pfal3D7_pB_mutagenesis_MIS_MFS_Phenotype_RSRC"
)
_ANALYSIS = '{"studyId":"DS_70dd50fed7","descriptor":{"subset":{"descriptor":[]}}}'
_WDK_STEP_ID = 440185943
_REFUSAL = "A step without an analysis"


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
def api() -> RecordingAPI:
    return RecordingAPI()


def _step(spec: str) -> StrategyStepNode:
    parameters: dict[str, ParamValue] = {
        EDA_DATASET_ID_PARAM: StringValue(value=_DATASET_ID),
        EDA_ANALYSIS_SPEC_PARAM: StringValue(value=spec),
    }
    return StrategyStepNode(id="step_eda", search_name=_SEARCH, parameters=parameters)


class TestTheCreateCall:
    async def test_an_empty_analysis_is_refused_and_creates_nothing(
        self, api: RecordingAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        committed, _ = await commit_against(
            monkeypatch, api, _step(""), before=None, held={}
        )

        (failure,) = committed.failures
        assert failure.step_id == "step_eda"
        assert _REFUSAL in failure.error
        assert "Export the step again from an analysis" in failure.error
        assert api.calls == []

    async def test_an_authored_analysis_reaches_the_site(
        self, api: RecordingAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        committed, sync_state = await commit_against(
            monkeypatch, api, _step(_ANALYSIS), before=None, held={}
        )

        assert sync_state.wdk_step_ids == {"step_eda": _WDK_STEP_ID}
        assert committed.failures == []
        assert api.calls == ["create_step"]


class TestThePatchCall:
    async def test_an_empty_analysis_is_refused_and_patches_nothing(
        self, api: RecordingAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        committed, sync_state = await commit_against(
            monkeypatch,
            api,
            _step(""),
            before=_step(_ANALYSIS),
            held={"step_eda": _WDK_STEP_ID},
        )

        (failure,) = committed.failures
        assert _REFUSAL in failure.error
        assert sync_state.wdk_push_errors["step_eda"] == failure.error
        assert api.calls == []

    async def test_an_authored_analysis_is_patched(
        self, api: RecordingAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        committed, _ = await commit_against(
            monkeypatch,
            api,
            _step(_ANALYSIS),
            before=_step(""),
            held={"step_eda": _WDK_STEP_ID},
        )

        assert committed.failures == []
        assert api.calls == ["update_step_search_config"]
