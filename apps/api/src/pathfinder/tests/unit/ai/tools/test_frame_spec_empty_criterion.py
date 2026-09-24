"""A criterion that counts zero names the choices its own parameters hold."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, VocabOption
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_count import MAX_LISTED_OPTIONS
from pathfinder.ai.tools.standalone.frame_spec import SetCriterionResult
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import summary_of
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    Proposals,
    bind,
    frame_ctx,
    param_info,
    serve_resolution,
    serve_search,
    set_criterion_as_read,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec_criterion_count import _serve_count

_VERSIONS = [
    VocabOption(value="v3", display="v3"),
    VocabOption(value="v2", display="v2"),
    VocabOption(value="v1", display="v1"),
]
_ONE_SOURCE = [VocabOption(value="curated", display="curated")]
_TISSUES = [VocabOption(value=f"t{n}", display=f"t{n}") for n in range(40)]
_SPECIES = [VocabOption(value=f"sp{n}", display=f"sp{n}") for n in (1, 2, 3)]

_PICK_V3: Proposals = {"method_version": "v3"}


def versioned(_context: dict[str, str]) -> list[ParameterInfo]:
    """A search with one flat single-pick vocabulary of three values."""
    return [
        param_info(
            "method_version",
            "single-pick-vocabulary",
            vocab_leaves=_VERSIONS,
            default_value="v3",
        ),
    ]


def single_option(_context: dict[str, str]) -> list[ParameterInfo]:
    """A search whose only vocabulary parameter accepts one value."""
    return [
        param_info(
            "source",
            "single-pick-vocabulary",
            vocab_leaves=_ONE_SOURCE,
            default_value="curated",
        ),
    ]


def wide_vocabulary(_context: dict[str, str]) -> list[ParameterInfo]:
    """A search with one vocabulary too large to list."""
    return [param_info("tissue", "multi-pick-vocabulary", vocab_leaves=_TISSUES)]


def small_multi_pick(_context: dict[str, str]) -> list[ParameterInfo]:
    """A small multi-pick vocabulary the caller can select whole."""
    return [param_info("source", "multi-pick-vocabulary", vocab_leaves=_VERSIONS)]


def tree_vocabulary(_context: dict[str, str]) -> list[ParameterInfo]:
    """A small tree whose parent terms stand outside the leaf list."""
    return [
        param_info(
            "clade",
            "multi-pick-vocabulary",
            vocab_leaves=_SPECIES,
            allowed_values_tree="every-species\n  sp1\n  sp2\n  sp3",
        )
    ]


@pytest.mark.asyncio
async def test_an_empty_binding_names_the_values_its_parameter_did_not_take(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, versioned)
    _serve_count(monkeypatch, 0)

    result = await bind(AgentToolState(), "RecordsByMethod", _PICK_V3)

    assert result.result_count == 0
    assert len(result.alternatives) == 1
    choice = result.alternatives[0]
    assert choice.param_name == "method_version"
    assert choice.bound == ["v3"]
    assert choice.option_count == 3
    assert choice.other_options == ["v2", "v1"]


@pytest.mark.asyncio
async def test_a_parameter_with_one_value_offers_no_choice_and_says_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, single_option)
    _serve_count(monkeypatch, 0)

    call = await set_criterion_as_read(
        frame_ctx(AgentToolState()),
        criterion_id="c1",
        text="curated records",
        search_name="RecordsBySource",
        params={"source": "curated"},
    )

    assert returned(call, SetCriterionResult).alternatives == []
    assert summary_of(call).data["summary"] == (
        "c1 set to RecordsBySource, 0 transcripts, sets source"
    )


@pytest.mark.asyncio
async def test_a_vocabulary_too_large_to_list_reports_its_bound_value_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, wide_vocabulary)
    _serve_count(monkeypatch, 0)

    result = await bind(AgentToolState(), "RecordsByTissue", {"tissue": ["t7"]})

    choice = result.alternatives[0]
    assert choice.param_name == "tissue"
    assert choice.bound == ["t7"]
    assert choice.option_count == 40
    assert choice.other_options == [], "40 options is past the listing bound"
    assert MAX_LISTED_OPTIONS < 40


@pytest.mark.asyncio
async def test_a_multi_pick_that_took_every_value_has_nothing_else_to_offer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, small_multi_pick)
    _serve_count(monkeypatch, 0)

    result = await bind(
        AgentToolState(), "RecordsBySource", {"source": ["v3", "v2", "v1"]}
    )

    assert result.alternatives == []


@pytest.mark.asyncio
async def test_a_multi_pick_reports_the_values_it_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, small_multi_pick)
    _serve_count(monkeypatch, 0)

    result = await bind(AgentToolState(), "RecordsBySource", {"source": ["v3"]})

    choice = result.alternatives[0]
    assert choice.bound == ["v3"]
    assert choice.other_options == ["v2", "v1"]


@pytest.mark.asyncio
async def test_a_parameter_the_binding_left_empty_states_no_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parameter holding no value has no value to swap."""
    serve_search(monkeypatch, small_multi_pick)
    _serve_count(monkeypatch, 0)
    serve_resolution(monkeypatch, {"source": MultiPickValue(values=[])})

    result = await bind(AgentToolState(), "RecordsBySource", {"source": None})

    assert result.alternatives == []


@pytest.mark.asyncio
async def test_a_value_the_option_list_does_not_name_reports_the_size_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tree parent stands for leaves it is not listed among, so the rest of
    the list is not the complement of what the binding took."""
    serve_search(monkeypatch, tree_vocabulary)
    _serve_count(monkeypatch, 0)
    serve_resolution(monkeypatch, {"clade": MultiPickValue(values=["every-species"])})

    result = await bind(AgentToolState(), "RecordsByClade", {"clade": ["sp1"]})

    choice = result.alternatives[0]
    assert choice.bound == ["every-species"]
    assert choice.option_count == 3
    assert choice.other_options == []


@pytest.mark.asyncio
async def test_a_binding_that_matched_records_gains_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, versioned)
    _serve_count(monkeypatch, 12)

    call = await set_criterion_as_read(
        frame_ctx(AgentToolState()),
        criterion_id="c1",
        text="records",
        search_name="RecordsByMethod",
        params=_PICK_V3,
    )

    assert returned(call, SetCriterionResult).alternatives == []
    assert summary_of(call).data["summary"] == (
        "c1 set to RecordsByMethod, 12 transcripts, sets method_version"
    )


@pytest.mark.asyncio
async def test_a_count_that_did_not_arrive_reports_no_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No count is not a count of zero, so nothing is offered."""
    serve_search(monkeypatch, versioned)
    _serve_count(monkeypatch, None)

    result = await bind(AgentToolState(), "RecordsByMethod", _PICK_V3)

    assert result.result_count is None
    assert result.alternatives == []


@pytest.mark.asyncio
async def test_the_summary_line_says_where_the_choices_are(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, versioned)
    _serve_count(monkeypatch, 0)

    call = await set_criterion_as_read(
        frame_ctx(AgentToolState()),
        criterion_id="c1",
        text="records",
        search_name="RecordsByMethod",
        params=_PICK_V3,
    )

    chunk = summary_of(call)
    assert chunk.data["summary"] == (
        "c1 set to RecordsByMethod, 0 transcripts; method_version has 3 options, "
        "sets method_version"
    )
    assert chunk.data["status"] == "empty"
