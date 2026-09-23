"""``set_criterion`` shows the search it binds by its name and its summary."""

from __future__ import annotations

import pytest

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import pinned_frame_sheets
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    KINASE_PARAMS,
    bind,
    frame_ctx,
    genes_by_text,
    serve_definition,
    serve_search,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec_sheet import genes_by_text_wdk

_NAME = "Exported Protein"
_SUMMARY = "Find genes whose protein is predicted by ExportPred to be <i>exported</i>."
_PLAIN = "Find genes whose protein is predicted by ExportPred to be exported."


async def test_the_sheet_call_names_the_search_it_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_definition(
        monkeypatch, genes_by_text_wdk(), display_name=_NAME, summary=_SUMMARY
    )
    state = AgentToolState()

    result = await bind(state, "GenesByText", text="a predicted GPI anchor")

    assert result.what_runs == _NAME


async def test_the_pinned_sheet_is_headed_by_what_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_definition(
        monkeypatch, genes_by_text_wdk(), display_name=_NAME, summary=_SUMMARY
    )
    state = AgentToolState()
    await bind(state, "GenesByText", text="a predicted GPI anchor")

    pinned = pinned_frame_sheets(frame_ctx(state)) or ""

    heading = next(line for line in pinned.splitlines() if line.startswith("###"))
    assert heading == f"### sheet for c1 -> GenesByText ({_NAME}: {_PLAIN})"


async def test_a_bound_criterion_records_the_name_of_its_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text, display_name=_NAME, summary=_SUMMARY)
    state = AgentToolState()

    result = await bind(state, "GenesByText", KINASE_PARAMS)

    (criterion,) = state.operational_spec_draft.criteria
    assert criterion.search_display_name == _NAME
    assert result.what_runs == f"{_NAME}: {_PLAIN}"


async def test_a_tagged_search_name_is_recorded_as_plain_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(
        monkeypatch,
        genes_by_text,
        display_name="<i>Exported</i> Protein",
        summary=_SUMMARY,
    )
    state = AgentToolState()

    result = await bind(state, "GenesByText", KINASE_PARAMS)

    (criterion,) = state.operational_spec_draft.criteria
    assert (criterion.search_display_name, result.what_runs) == (
        _NAME,
        f"{_NAME}: {_PLAIN}",
    )
