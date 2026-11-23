from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp

from strategist.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from strategist.ai.lead.build_messages import structure_does_not_convert_message
from strategist.ai.lead.edit_messages import (
    delta_disagrees_with_the_strategy_message,
    edit_bound_nothing_message,
    edit_operation_refused_message,
    unsupported_edit_message,
    wdk_refused_the_written_step_message,
)
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.ai.tools.standalone import eda_catalog
from strategist.ai.tools.standalone._eda_models import EdaStudySearchResult
from strategist.domain.strategy.edit_plan import UnsupportedEditError
from strategist.domain.strategy.operational_spec import SpecStructure
from strategist.services.eda.catalog import StudySearch
from strategist.tests._support.recorded_vdi import no_own_datasets
from strategist.tests._support.run_context import lead_run_context
from strategist.tests._support.tool_names import foreign_names
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.domain.strategy._builders import (
    graph_of,
    plan,
    spec_joined,
    spec_leaf,
    spec_of,
    three_step_root,
)


def test_a_structure_that_does_not_convert_names_the_leads_route() -> None:
    message = structure_does_not_convert_message("x")

    assert foreign_names(message, build_lead_agent()) == []
    assert "frame_problem" in message


@pytest.mark.parametrize(
    "message",
    [
        edit_bound_nothing_message(),
        edit_operation_refused_message("x"),
        wdk_refused_the_written_step_message(
            "x", steps=["step_1"], params=["organism"]
        ),
        delta_disagrees_with_the_strategy_message(["c1"]),
        unsupported_edit_message("x"),
    ],
    ids=["bound_nothing", "refused", "wdk_refused", "disagrees", "unsupported"],
)
def test_an_edit_refusal_names_no_framing_tool(message: str) -> None:
    assert foreign_names(message, build_lead_agent()) == []
    assert "edit_strategy" in message


def test_a_removal_the_edit_did_not_state_names_no_framing_tool() -> None:
    root = three_step_root()
    before = spec_of(root)
    before.criteria = [c for c in before.criteria if c.id != "step_expr"]
    after = before.model_copy(deep=True)
    after.structure = SpecStructure(
        root=spec_joined(
            CombineOp.INTERSECT, spec_leaf("step_go"), spec_leaf("step_text")
        )
    )

    with pytest.raises(UnsupportedEditError) as refused:
        plan(before, after, graph_of(root))

    assert "take ['step_expr'] off the strategy" in str(refused.value)
    assert foreign_names(str(refused.value), build_lead_agent()) == []


async def _no_study(_site: str, _query: str, limit: int = 5) -> StudySearch:
    del limit
    return StudySearch(cards=[], catalog_size=0)


async def test_an_eda_search_with_no_match_names_no_catalog_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(eda_catalog, "search_studies", _no_study)
    monkeypatch.setattr(eda_catalog, "own_dataset_cards", no_own_datasets)

    result = returned(
        await eda_catalog.search_eda_studies(lead_run_context(), query="kinases"),
        EdaStudySearchResult,
    )

    assert foreign_names(result.guidance, build_lead_agent()) == []
    assert "No EDA study" in result.guidance


def test_the_lead_is_told_what_a_stale_line_means() -> None:
    assert "get_live_strategy_state" in LEAD_INSTRUCTIONS
    assert "STALE" in LEAD_INSTRUCTIONS
