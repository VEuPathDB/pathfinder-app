"""The Lead lists a built step's columns a page at a time and counts the step by
one of them through the tool server, and the counts are facts a reply quotes."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.toolsets import FunctionToolset, WrapperToolset
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb_mcp.wdk import (
    ColumnCounts,
    ColumnNotCountedError,
    CountedValue,
    StepColumn,
    StepColumns,
)

from pathfinder.ai.lead.lead_agent import build_lead_toolset
from pathfinder.ai.tools.standalone.step_tally import (
    StepColumnPage,
    count_step_by_column,
    step_columns,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.tally_facts import tally_count, tally_id
from pathfinder.services.experiment.column_tally import ColumnTally
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.recorded_columns import TM_STEP, column_catalog
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.step_tally_site import TallySite, ToolServer, serve
from pathfinder.tests._support.tool_returns import returned


def _membrane_genes() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("g1", "membrane genes", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id="tm", search_name="GenesByTransmembraneDomains")
    )
    graph.steps["tm"].record_class = "transcript"
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={"tm": TM_STEP})
    return session


def _listed() -> StepColumns:
    return StepColumns(
        step_id=TM_STEP,
        record_type="transcript",
        search_name="GenesByTransmembraneDomains",
        columns=tuple(
            StepColumn(
                name=a.name,
                display_name=a.display_name or a.name,
                data_type=a.column_data_type,
                countable=a.column_data_type in ("STRING", "NUMBER")
                and "byValue" in a.tools.reports,
            )
            for a in column_catalog().attributes or []
        ),
    )


def _serve(monkeypatch: pytest.MonkeyPatch, server: ToolServer) -> ToolServer:
    serve(monkeypatch, TallySite(column_catalog(), step_count=840), server)
    return server


_ORGANISMS = ColumnCounts(
    step_id=TM_STEP,
    column="organism",
    display_name="Organism",
    kind="string",
    total_records=840,
    distinct_values=3,
    values=(
        CountedValue(value="<i>Plasmodium falciparum</i> 3D7", count=812),
        CountedValue(value="<i>Plasmodium falciparum</i> IT", count=21),
        CountedValue(value="<i>Plasmodium falciparum</i> HB3", count=7),
    ),
)


async def test_a_step_is_counted_through_the_tool_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _serve(monkeypatch, ToolServer(counts=_ORGANISMS))
    ctx = lead_run_context(site_id="plasmodb", strategy_session=_membrane_genes())

    result = await count_step_by_column(ctx, TM_STEP, "organism", top=3)

    tally = returned(result, ColumnTally)
    assert server.counted == [("plasmodb", TM_STEP, "organism", 3)]
    assert [(row.value, row.count) for row in tally.rows] == [
        ("Plasmodium falciparum 3D7", 812),
        ("Plasmodium falciparum IT", 21),
        ("Plasmodium falciparum HB3", 7),
    ]
    assert (tally.title, tally.record_noun, tally.total, tally.distinct) == (
        "Transcripts by Organism",
        "transcript",
        840,
        3,
    )
    chunks = [
        c
        for c in result.metadata or []
        if isinstance(c, DataChunk) and c.type == "data-column-tally"
    ]
    assert [c.data for c in chunks] == [tally.model_dump(by_alias=True, mode="json")]


async def test_the_counts_of_a_step_are_facts_a_reply_quotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, ToolServer(counts=_ORGANISMS))
    ctx = lead_run_context(site_id="plasmodb", strategy_session=_membrane_genes())

    await count_step_by_column(ctx, TM_STEP, "organism")

    tallies = ctx.deps.state.turn_markers.tallies
    held = tally_id("plasmodb", f"step {TM_STEP}", "organism", None)
    assert [
        tally_count(tallies, body)
        for body in (
            held,
            f"{held}.Plasmodium falciparum IT",
            f"{held}:values",
        )
    ] == ["840 transcripts", "21 transcripts", "3 values"]


async def test_an_unknown_column_goes_back_naming_the_countable_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refusal = ColumnNotCountedError(
        TM_STEP, "organsim", None, ("gene_type", "organism", "tm_count")
    )
    _serve(monkeypatch, ToolServer(refusal=refusal))
    ctx = lead_run_context(site_id="plasmodb", strategy_session=_membrane_genes())

    with pytest.raises(ModelRetry) as refused:
        await count_step_by_column(ctx, TM_STEP, "organsim")

    assert str(refused.value) == (
        f"transcript records of step {TM_STEP} cannot be counted by organsim: it "
        "is not a column of the step. The columns it can be counted by: "
        "gene_type, organism, tm_count."
    )
    assert ctx.deps.state.turn_markers.tallies == []


async def test_a_steps_columns_are_listed_a_page_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listed = _listed()
    server = _serve(monkeypatch, ToolServer(listed=listed))
    ctx = lead_run_context(site_id="plasmodb", strategy_session=_membrane_genes())

    first = returned(await step_columns(ctx, TM_STEP), StepColumnPage)
    last = returned(await step_columns(ctx, TM_STEP, offset=2300), StepColumnPage)

    assert server.listed_for == [("plasmodb", TM_STEP), ("plasmodb", TM_STEP)]
    assert (first.total, first.countable, first.offset, len(first.columns)) == (
        2375,
        2373,
        0,
        100,
    )
    assert first.columns[0].name == "primary_key"
    assert [c.name for c in first.columns] == [c.name for c in listed.columns[:100]]
    assert [c.name for c in last.columns] == [c.name for c in listed.columns[2300:]]
    assert (first.record_type, first.search_name) == (
        "transcript",
        "GenesByTransmembraneDomains",
    )


async def test_a_steps_columns_are_found_by_name_and_countable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, ToolServer(listed=_listed()))
    ctx = lead_run_context(site_id="plasmodb", strategy_session=_membrane_genes())

    found = returned(
        await step_columns(ctx, TM_STEP, name="ORGANISM", countable_only=True),
        StepColumnPage,
    )
    links = returned(await step_columns(ctx, TM_STEP, name="jbrowse"), StepColumnPage)

    assert [(c.name, c.display_name) for c in found.columns] == [
        ("organism", "Organism"),
        ("organism_text", "Organism (Internal)"),
        ("organism_full", "Organism"),
        ("organismAbbrev", "organismAbbrev"),
    ]
    assert (found.total, found.countable, found.reach, found.transforms) == (
        4,
        4,
        "step",
        [],
    )
    assert [(c.name, c.data_type, c.countable) for c in links.columns] == [
        ("JBrowse", "OTHER", False),
    ]
    counted_links = returned(
        await step_columns(ctx, TM_STEP, name="jbrowse", countable_only=True),
        StepColumnPage,
    )
    assert (
        counted_links.total,
        counted_links.columns,
        counted_links.reach,
        counted_links.transforms,
    ) == (0, [], "none", [])


async def test_a_step_the_strategy_does_not_hold_is_not_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _serve(monkeypatch, ToolServer(listed=_listed()))
    ctx = lead_run_context(site_id="plasmodb", strategy_session=_membrane_genes())

    with pytest.raises(ModelRetry) as refused:
        await step_columns(ctx, 1)

    assert str(refused.value) == (
        f"Step 1 is not a step of this strategy. Its built steps: {TM_STEP}."
    )
    assert server.listed_for == []


def test_the_lead_lists_and_counts_a_steps_columns() -> None:
    read_once = build_lead_toolset()
    assert isinstance(read_once, WrapperToolset)
    refusal_memory = read_once.wrapped
    assert isinstance(refusal_memory, WrapperToolset)
    base = refusal_memory.wrapped
    assert isinstance(base, FunctionToolset)

    assert {"step_columns", "count_step_by_column"} <= set(base.tools)
