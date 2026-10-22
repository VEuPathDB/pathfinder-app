from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM, EDA_DATASET_ID_PARAM

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.eda import analysis_kinds
from pathfinder.services.eda.analysis_kinds import analysis_kinds_of
from pathfinder.services.strategies import sheet_params
from pathfinder.services.strategies.sheet_params import sheet_params_for_searches
from pathfinder.tests._support.eda_step_doubles import DE_DATASET
from pathfinder.tests._support.orthomcl_site import OrthoSite
from pathfinder.tests.unit.ai.lead._analysis_thread import document


def _serve(monkeypatch: pytest.MonkeyPatch) -> OrthoSite:
    site = OrthoSite()

    async def _definition(_site: str, record_type: str, name: str) -> WDKSearch:
        return site.read(record_type, name)

    monkeypatch.setattr(sheet_params, "read_search_definition", _definition)
    monkeypatch.setattr(analysis_kinds, "read_search_definition", _definition)
    return site


async def test_a_protein_search_of_a_group_strategy_has_its_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch)

    sheets = await sheet_params_for_searches(
        site_id="orthomcl",
        record_type="group",
        search_names=["ByIdList", "GroupsFromSequences"],
    )

    assert site.reads == [("sequence", "ByIdList"), ("group", "GroupsFromSequences")]
    assert {name: [i.name for i in infos] for name, infos in sheets.items()} == {
        "ByIdList": ["source_ids"],
        "GroupsFromSequences": [],
    }


async def test_a_protein_step_of_a_group_strategy_has_its_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch)
    node = StrategyStepNode(
        id="step_protein",
        search_name="ByIdList",
        parameters={
            EDA_DATASET_ID_PARAM: StringValue(value=DE_DATASET),
            EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05),
        },
    )

    kinds = await analysis_kinds_of(
        site_id="orthomcl", record_type="group", nodes=[node]
    )

    assert site.reads == [("sequence", "ByIdList")]
    assert kinds == {
        "step_protein": StampedKind(search_name="ByIdList", kind=AnalysisKind.NONE)
    }
