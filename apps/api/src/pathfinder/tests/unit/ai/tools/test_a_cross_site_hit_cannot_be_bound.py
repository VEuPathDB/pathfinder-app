"""An experiment another site holds informs a criterion and is never bound."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.wdk import WDKSearch
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import SearchMatch

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.catalog import search_for_searches
from pathfinder.ai.tools.toolsets.frame import build_toolset
from pathfinder.tests._support.experiment_cards import CRYPTO, CRYPTO_SEARCH
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_OWN = SearchMatch(
    name="GenesByRNASeqpfal3D7_Su_strand_specific_RSRC",
    display_name="Sporozoite RNA-Seq",
    description="Find genes by sporozoite RNA-Seq",
    record_type="transcript",
    relevance=1.0,
    semantic_similarity=0.61,
)
_SHARED_SEARCH = "GenesByIntronJunctions"
_ROUTES = (
    "An experiment on another site informs a criterion and is never bound: take "
    "its condition or stage into search_for_searches on plasmodb, cite it in "
    "why.sources, or carry its genes by orthology on the VEuPathDB portal, where "
    "one strategy holds both organisms. Nothing was recorded."
)


async def _after_a_read_showing_cryptodb(
    monkeypatch: pytest.MonkeyPatch,
) -> RunContext[AgentDeps]:
    monkeypatch.setattr(catalog, "search_for_searches", AsyncMock(return_value=[_OWN]))
    monkeypatch.setattr(
        catalog, "rank_experiments_elsewhere", AsyncMock(return_value=[CRYPTO])
    )
    # plasmodb publishes one search of the cryptodb card as well.
    monkeypatch.setattr(
        catalog,
        "get_raw_searches",
        AsyncMock(return_value=[WDKSearch(url_segment=_SHARED_SEARCH)]),
    )
    ctx = agent_run_context(agent_state=AgentToolState())
    await search_for_searches(ctx, query="infection time course RNA-Seq")
    return ctx


async def _set_criterion(ctx: RunContext[AgentDeps], search_name: str) -> None:
    toolset = build_toolset()
    tool = (await toolset.get_tools(ctx))["set_criterion"]
    await toolset.call_tool(
        "set_criterion",
        {
            "criterion_id": "c_infection",
            "text": "genes up during the in vitro infection time course",
            "search_name": search_name,
        },
        ctx,
        tool,
    )


@pytest.mark.asyncio
async def test_another_sites_search_is_refused_naming_both_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = await _after_a_read_showing_cryptodb(monkeypatch)

    with pytest.raises(ModelRetry) as refused:
        await _set_criterion(ctx, CRYPTO_SEARCH)

    assert str(refused.value) == (
        f"{CRYPTO_SEARCH} is a search on cryptodb, and this strategy runs on "
        f"plasmodb. {_ROUTES}"
    )
    assert ctx.deps.agent_state.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_another_sites_dataset_id_is_refused_the_same_way(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = await _after_a_read_showing_cryptodb(monkeypatch)

    with pytest.raises(ModelRetry) as refused:
        await _set_criterion(ctx, "DS_63b0de882c")

    assert str(refused.value) == (
        f"DS_63b0de882c is a dataset on cryptodb, and this strategy runs on "
        f"plasmodb. {_ROUTES}"
    )
    assert ctx.deps.agent_state.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_a_name_no_site_showed_gets_the_known_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = await _after_a_read_showing_cryptodb(monkeypatch)

    with pytest.raises(ModelRetry) as refused:
        await _set_criterion(ctx, "GenesByImaginary")

    assert str(refused.value) == (
        "search_name='GenesByImaginary' is not a known value for set_criterion. "
        "Choose one of: GenesByRNASeqpfal3D7_Su_strand_specific_RSRC, GenesByText. "
        "Copy it verbatim - do not paraphrase or invent."
    )


@pytest.mark.asyncio
async def test_a_search_this_site_also_publishes_gets_the_known_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name the card lists and this site publishes is not another site's alone."""
    ctx = await _after_a_read_showing_cryptodb(monkeypatch)

    with pytest.raises(ModelRetry) as refused:
        await _set_criterion(ctx, _SHARED_SEARCH)

    assert str(refused.value) == (
        f"search_name='{_SHARED_SEARCH}' is not a known value for set_criterion. "
        "Choose one of: GenesByRNASeqpfal3D7_Su_strand_specific_RSRC, GenesByText. "
        "Copy it verbatim - do not paraphrase or invent."
    )
