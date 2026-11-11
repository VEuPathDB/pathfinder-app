from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from veupathdb.eda import EdaPermissionEntry, EdaStudyDetail

from pathfinder.ai.lead.lead_pins import pinned_eda_sheet
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    no_description,
    permission_entry,
    study_of,
)
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET, PHENOTYPE_ENTITY

_RANK_DEFINITION = "Order/Rank of the Mean Phenotype Score"
_ESSENTIAL = (
    "Genes that cannot be disrupted are consided Essential - in other words "
    "essential genes are defined as those coding sequences from which no "
    "insertions are recovered."
)


async def _ranked_study(
    _site: str, _dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    variables: list[dict[str, Any]] = [
        {
            "id": "VAR_rank",
            "type": "integer",
            "displayName": "Phenotype Rank",
            "dataShape": "continuous",
            "definition": _RANK_DEFINITION,
            "distributionDefaults": {"rangeMin": 1, "rangeMax": 8151},
        },
        {
            "id": "VAR_score",
            "type": "number",
            "displayName": "Mean Phenotype Score",
            "dataShape": "continuous",
            "distributionDefaults": {"rangeMin": -6.89, "rangeMax": 2.96},
        },
    ]
    return permission_entry(), study_of(variables, entity_id=PHENOTYPE_ENTITY)


async def _bound(_ctx: object) -> ConversationAnalysisView:
    return ConversationAnalysisView(
        site_id="toxodb",
        dataset_id=PHENOTYPE_DATASET,
        analysis_id=ANALYSIS_ID,
        revision=1,
    )


async def test_a_sheet_entry_carries_the_definition_the_site_gives_its_variable(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", _ranked_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    monkeypatch.setattr(eda_analysis, "study_description", no_description)
    await eda_analysis.set_eda_filters(lead_ctx, dataset_id=PHENOTYPE_DATASET)
    sheet = lead_ctx.deps.state.domain.open_eda_sheet
    assert sheet is not None
    dumped = {
        entry.variable_id: entry.model_dump(by_alias=True, mode="json")
        for entry in sheet.entries
    }

    assert dumped["VAR_rank"]["definition"] == _RANK_DEFINITION
    assert "definition" not in dumped["VAR_score"]


async def _essential_definition(_site: str, study_id: str) -> str:
    assert study_id == permission_entry().study_id
    return _ESSENTIAL


async def test_the_sheet_carries_the_studys_description(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", _ranked_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    monkeypatch.setattr(eda_analysis, "study_description", _essential_definition)
    await eda_analysis.set_eda_filters(lead_ctx, dataset_id=PHENOTYPE_DATASET)
    sheet = lead_ctx.deps.state.domain.open_eda_sheet
    assert sheet is not None

    assert sheet.study_description == _ESSENTIAL
    pinned = pinned_eda_sheet(lead_ctx)
    assert pinned is not None
    assert f"Study description: {_ESSENTIAL}" in pinned


async def test_a_study_with_no_description_pins_no_description_line(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", _ranked_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    monkeypatch.setattr(eda_analysis, "study_description", no_description)
    await eda_analysis.set_eda_filters(lead_ctx, dataset_id=PHENOTYPE_DATASET)

    pinned = pinned_eda_sheet(lead_ctx)
    assert pinned is not None
    assert "Study description" not in pinned
    assert "Phenotype Rank" in pinned
