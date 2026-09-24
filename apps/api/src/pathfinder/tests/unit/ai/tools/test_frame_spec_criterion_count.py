"""``set_criterion`` reports how many records the binding it just made matches.

The count is faked here; the service that reads it has its own tests.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue, to_wire
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ResolvedParams

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import _frame_count
from pathfinder.domain.strategy.operational_spec import OpenSlot
from pathfinder.tests.unit.ai.tools.conftest import summary_of
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    Proposals,
    bind,
    frame_ctx,
    genes_by_text,
    serve_resolution,
    serve_search,
    set_criterion_as_read,
)

_GIARDIA: Proposals = {
    "text_expression": '"variant surface protein"',
    "text_search_organism": ["Plasmodium"],
    "document_type": None,
    "text_fields": None,
}


def _serve_count(
    monkeypatch: pytest.MonkeyPatch, count: int | None
) -> list[dict[str, object]]:
    """Answer one fixed count, and record every read it was asked for."""
    asked: list[dict[str, object]] = []

    async def _count(
        site_id: str,
        record_type: str,
        search_name: str,
        params: Mapping[str, ParamValue],
    ) -> int | None:
        asked.append(
            {
                "siteId": site_id,
                "recordType": record_type,
                "searchName": search_name,
                "params": dict(params),
            }
        )
        return count

    monkeypatch.setattr(_frame_count, "count_bound_criterion", _count)
    return asked


@pytest.mark.asyncio
async def test_a_completed_binding_carries_its_own_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    asked = _serve_count(monkeypatch, 3)
    state = AgentToolState()

    result = await bind(state, "GenesByText", _GIARDIA)

    assert result.result_count == 3
    assert [(a["siteId"], a["recordType"], a["searchName"]) for a in asked] == [
        ("plasmodb", "transcript", "GenesByText")
    ]


@pytest.mark.asyncio
async def test_the_count_reads_the_configuration_the_criterion_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counted parameters are the ones the spec records and BUILD pushes."""
    serve_search(monkeypatch, genes_by_text)
    asked = _serve_count(monkeypatch, 3)
    state = AgentToolState()

    result = await bind(state, "GenesByText", _GIARDIA)

    counted = asked[0]["params"]
    stored = state.operational_spec_draft.criteria[0].resolved_params
    assert counted == stored
    assert {name: to_wire(v) for name, v in stored.items()} == result.resolved_params
    assert stored["text_expression"].to_wire() == '"variant surface protein"'
    assert set(stored) == {
        "text_expression",
        "text_search_organism",
        "document_type",
        "text_fields",
    }


@pytest.mark.asyncio
async def test_the_binding_costs_exactly_one_read_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    asked = _serve_count(monkeypatch, 3)
    state = AgentToolState()

    await bind(state, "GenesByText", _GIARDIA)

    assert len(asked) == 1


@pytest.mark.asyncio
async def test_an_unbound_parameter_costs_no_count_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    asked = _serve_count(monkeypatch, 3)
    serve_resolution(
        monkeypatch,
        {"text_expression": StringValue(value='"variant surface protein"')},
        open_slots=[OpenSlot(param_name="text_search_organism", question="which")],
        unresolved=["text_search_organism"],
    )
    state = AgentToolState()

    result = await bind(state, "GenesByText", _GIARDIA)

    assert result.result_count is None
    assert asked == []


def _search(*, takes_an_input_step: bool) -> WDKSearch:
    return WDKSearch(
        url_segment="GenesByOrthologs",
        allowed_primary_input_record_class_names=["transcript"]
        if takes_an_input_step
        else None,
    )


@pytest.mark.asyncio
async def test_a_search_that_runs_on_another_step_is_not_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A search with no input step of its own answers nothing to count."""
    asked = _serve_count(monkeypatch, 3)
    resolved = ResolvedParams(params={"gene_result": StringValue(value="")})

    count = await _frame_count.bound_count(
        frame_ctx(AgentToolState()),
        resolved,
        "transcript",
        "GenesByOrthologs",
        _search(takes_an_input_step=True),
    )

    assert count is None
    assert asked == []


@pytest.mark.asyncio
async def test_a_search_that_runs_on_its_own_is_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _serve_count(monkeypatch, 3)
    resolved = ResolvedParams(params={"text_expression": StringValue(value="kinase")})

    count = await _frame_count.bound_count(
        frame_ctx(AgentToolState()),
        resolved,
        "transcript",
        "GenesByText",
        _search(takes_an_input_step=False),
    )

    assert count == 3
    assert len(asked) == 1


@pytest.mark.asyncio
async def test_the_criterion_binds_whatever_the_count_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    _serve_count(monkeypatch, 3)
    state = AgentToolState()

    await bind(state, "GenesByText", _GIARDIA)

    criterion = state.operational_spec_draft.criteria[0]
    assert criterion.search_name == "GenesByText"
    assert criterion.resolved_params["text_expression"].to_wire() == (
        '"variant surface protein"'
    )


@pytest.mark.asyncio
async def test_the_trace_line_states_the_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    _serve_count(monkeypatch, 3)
    state = AgentToolState()

    returned = await set_criterion_as_read(
        frame_ctx(state),
        criterion_id="c1",
        text="variant surface proteins",
        search_name="GenesByText",
        params=_GIARDIA,
    )

    chunk = summary_of(returned)
    assert chunk.data["summary"] == (
        "c1 set to GenesByText, 3 transcripts, sets text_expression"
    )
    assert chunk.data["status"] == "ok"


@pytest.mark.asyncio
async def test_a_binding_that_matches_nothing_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    _serve_count(monkeypatch, 0)
    state = AgentToolState()

    returned = await set_criterion_as_read(
        frame_ctx(state),
        criterion_id="c1",
        text="variant surface proteins",
        search_name="GenesByText",
        params=_GIARDIA,
    )

    chunk = summary_of(returned)
    assert chunk.data["summary"] == (
        "c1 set to GenesByText, 0 transcripts; text_search_organism has 2 "
        "options, sets text_expression"
    )
    assert chunk.data["status"] == "empty"


@pytest.mark.asyncio
async def test_a_count_that_did_not_arrive_leaves_the_plain_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    asked = _serve_count(monkeypatch, None)
    state = AgentToolState()

    returned = await set_criterion_as_read(
        frame_ctx(state),
        criterion_id="c1",
        text="variant surface proteins",
        search_name="GenesByText",
        params=_GIARDIA,
    )

    chunk = summary_of(returned)
    assert chunk.data["summary"] == "c1 set to GenesByText, sets text_expression"
    assert chunk.data["status"] == "ok"
    assert len(asked) == 1, "the count was asked for and did not answer"


def test_one_record_is_not_written_as_a_plural() -> None:
    line, status = _frame_count.criterion_line("c1", "GenesByText", "transcript", 1, [])

    assert line == "c1 set to GenesByText, 1 transcript"
    assert status == "ok"


def test_the_noun_is_the_record_type_the_criterion_binds() -> None:
    line, _ = _frame_count.criterion_line("c1", "PathwaysByText", "pathway", 16, [])

    assert line == "c1 set to PathwaysByText, 16 pathways"


def test_a_large_count_is_written_for_a_reader() -> None:
    line, status = _frame_count.criterion_line(
        "c1", "GenesByText", "transcript", 9_667, []
    )

    assert line == "c1 set to GenesByText, 9,667 transcripts"
    assert status == "ok"


def test_a_binding_with_no_record_type_still_names_what_it_counted() -> None:
    line, _ = _frame_count.criterion_line("c1", "GenesByText", "", 5, [])

    assert line == "c1 set to GenesByText, 5 records"
