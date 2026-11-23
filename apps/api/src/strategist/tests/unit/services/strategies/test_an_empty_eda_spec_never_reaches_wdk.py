"""A leaf that leaves its EDA analysis empty is refused before the WDK call."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import (
    StrategyStepNode,
)
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM, EDA_DATASET_ID_PARAM

from strategist.services.strategies.step_push_planner import PatchAction
from strategist.tests._support.recording_wdk import RecordingWDK
from strategist.tests._support.wdk_write_stubs import commit_against

_VALUES = PatchAction(search_config=True, name=False)

_DATASET_ID = "DS_70dd50fed7"
_SEARCH = (
    "GenesByPhenotypeEdaSubset_PlasmoDB_pfal3D7_pB_mutagenesis_MIS_MFS_Phenotype_RSRC"
)
_ANALYSIS = '{"studyId":"DS_70dd50fed7","descriptor":{"subset":{"descriptor":[]}}}'
_WDK_STEP_ID = 440185943
_REFUSAL = "A step without an analysis"


class RecordingAPI(RecordingWDK):
    def __init__(self) -> None:
        super().__init__(next_id=_WDK_STEP_ID - 1)

    @property
    def written(self) -> list[str]:
        return [call.name for call in self.step_writes()]


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
        assert api.written == []

    async def test_an_authored_analysis_reaches_the_site(
        self, api: RecordingAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        committed, sync_state = await commit_against(
            monkeypatch, api, _step(_ANALYSIS), before=None, held={}
        )

        assert sync_state.wdk_step_ids == {"step_eda": _WDK_STEP_ID}
        assert committed.failures == []
        assert api.written == ["create_step"]


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
        assert api.written == []

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
        assert api.written == ["update_step_search_config"]
