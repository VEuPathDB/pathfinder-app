from __future__ import annotations

import inspect
import json
import re
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic_ai import ModelRetry, RunContext, Tool
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import SearchMatch

from strategist.ai.explore import explore_tools
from strategist.ai.explore.explore_agent import build_explore_agent
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.tools.standalone import _catalog_elsewhere, catalog_discovery
from strategist.ai.tools.standalone._catalog_elsewhere import ExperimentRead
from strategist.ai.tools.standalone.catalog import (
    get_record_types,
    search_for_searches,
)
from strategist.ai.tools.standalone.optimization import sweep_can_run
from strategist.tests._support.experiment_cards import CRYPTO, CRYPTO_CARD
from strategist.tests._support.qa_recording import client_recording
from strategist.tests._support.run_context import lead_run_context
from strategist.tests._support.sub_agents import agent_tool_names
from strategist.tests._support.tool_names import foreign_names, held_tool_names
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools.conftest import function_toolset_or_none

_ARGUMENT = re.compile(r"^ {4}(\w+):", re.MULTILINE)
_WRAPPED: dict[str, Callable[..., object]] = {
    "search_for_searches": search_for_searches,
    "get_search_overview": catalog_discovery.get_search_overview,
    "get_parameter_options": catalog_discovery.get_parameter_options,
    "get_record_types": get_record_types,
    "read_experiment": _catalog_elsewhere.read_experiment,
}
_ORTHOLOGS = WDKSearchResponse.model_validate(
    client_recording("search_genes_by_orthologs").json_body()
).search_data
_OWN = SearchMatch(
    name="GenesByRNASeqpfal3D7_Su_strand_specific_RSRC",
    display_name="Sporozoite RNA-Seq",
    description="Find genes by sporozoite RNA-Seq",
    record_type="transcript",
    relevance=1.0,
    semantic_similarity=0.61,
)


def _explore_tools() -> dict[str, Tool[Any]]:
    explore = build_explore_agent()
    held = agent_tool_names(explore)
    return {
        name: tool
        for toolset in explore.toolsets
        if (found := function_toolset_or_none(toolset)) is not None
        for name, tool in found.tools.items()
        if name in held
    }


def _seen(tool: Tool[Any]) -> str:
    schema = json.dumps(tool.tool_def.parameters_json_schema)
    return f"{tool.description or ''}\n{schema}"


def _arguments(tool: Tool[Any]) -> set[str]:
    doc = inspect.getdoc(tool.function) or ""
    _, _, args = doc.partition("Args:")
    return set(_ARGUMENT.findall(args))


def test_no_explore_tool_description_names_a_tool_explore_lacks() -> None:
    explore = build_explore_agent()

    foreign = {
        name: found
        for name, tool in _explore_tools().items()
        if (found := foreign_names(_seen(tool), explore))
    }

    assert foreign == {}


def test_no_explore_catalog_read_describes_framing() -> None:
    framing = ("creating a step", "criterion", "discovery gate")

    described = {
        tool.name: [words for words in framing if words in _seen(tool)]
        for tool in explore_tools.catalog_reads()
    }

    assert described == {name: [] for name in _WRAPPED}


def test_explore_catalog_reads_carry_their_own_words() -> None:
    for tool in explore_tools.catalog_reads():
        frame_words = Tool(_WRAPPED[tool.name]).description
        properties = set(tool.tool_def.parameters_json_schema["properties"])
        assert tool.description != frame_words, tool.name
        assert _arguments(tool) == properties, tool.name


def test_explore_holds_the_two_catalog_reads_it_is_told_about() -> None:
    assert {"read_experiment", "get_record_types"} <= held_tool_names(
        build_explore_agent()
    )


@pytest.fixture
def cryptodb_shown(monkeypatch: pytest.MonkeyPatch) -> RunContext[LeadDeps]:
    monkeypatch.setattr(catalog, "search_for_searches", AsyncMock(return_value=[_OWN]))
    monkeypatch.setattr(
        catalog, "rank_experiments_elsewhere", AsyncMock(return_value=[CRYPTO])
    )
    monkeypatch.setattr(
        catalog, "get_raw_searches", AsyncMock(return_value=[_ORTHOLOGS])
    )
    monkeypatch.setattr(
        catalog, "read_search_definition", AsyncMock(return_value=_ORTHOLOGS)
    )
    monkeypatch.setattr(catalog, "read_experiment", AsyncMock(return_value=CRYPTO_CARD))
    monkeypatch.setattr(
        explore_tools, "record_columns_block", AsyncMock(return_value=None)
    )
    return lead_run_context(tool_call_id="call_1")


async def test_explore_reads_an_experiment_its_search_showed(
    cryptodb_shown: RunContext[LeadDeps],
) -> None:
    ctx = cryptodb_shown
    await explore_tools.search_for_searches(
        ctx, "infection time course RNA-Seq", "transcript"
    )

    read = returned(
        await explore_tools.read_experiment(ctx, CRYPTO_CARD.dataset_id),
        ExperimentRead,
    )

    assert (read.site, read.dataset_id) == ("cryptodb", CRYPTO_CARD.dataset_id)
    assert CRYPTO_CARD.record_url in ctx.deps.state.turn_markers.retrieved_sources


async def test_explore_is_refused_an_experiment_it_did_not_show(
    cryptodb_shown: RunContext[LeadDeps],
) -> None:
    ctx = cryptodb_shown
    await explore_tools.search_for_searches(
        ctx, "infection time course RNA-Seq", "transcript"
    )

    with pytest.raises(ModelRetry) as refused:
        await explore_tools.read_experiment(ctx, "DS_never_shown")

    assert CRYPTO_CARD.dataset_id in str(refused.value)


async def test_a_sweep_without_a_set_names_no_tool_that_writes() -> None:
    with pytest.raises(ModelRetry) as refused:
        await sweep_can_run(
            lead_run_context(),
            reply="I will sweep the SignalP version against your controls.",
            wdk_step_id=440606243,
            control_set_id="96eaafb0-659c-4041-8bf3-5c66e5a9f95c",
        )

    assert foreign_names(str(refused.value), build_explore_agent()) == []
    assert str(refused.value).endswith("Nothing was started and no card was shown.")
