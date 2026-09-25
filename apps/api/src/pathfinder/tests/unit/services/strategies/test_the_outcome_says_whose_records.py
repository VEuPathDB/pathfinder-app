"""The build a strategy leaves says whose genes its records are when a transform
carried them to another organism, and the ledger prints it."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.lead import sub_agent_dispatch
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.ledger_render import render_build_full
from pathfinder.ai.lead.ledger_sections import BuildSection
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.orthology import OrganismChange
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.graph_outcome import outcome_for_graph
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.analysis_catalog import serve_the_catalog
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import install_stub_api

_SOURCE = "Plasmodium falciparum 3D7"
_TARGET = "Plasmodium vivax P01"


def _graph(*organisms: str) -> StrategyGraph:
    """The seed, then one orthology transform per organism, in order."""
    node = StrategyStepNode(
        id="step_seed",
        search_name="GenesWithSignalPeptide",
        parameters={"organism": MultiPickValue(values=[_SOURCE])},
    )
    for index, organism in enumerate(organisms):
        node = StrategyStepNode(
            id=f"step_leg{index}",
            search_name="GenesByOrthologs",
            parameters={
                "organism": MultiPickValue(values=[organism]),
                "isSyntenic": SinglePickValue(value="no"),
            },
            primary_input=node,
        )
    graph = StrategyGraph(graph_id="g1", name="Orthologs", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(node)
    graph.recompute_roots()
    return graph


def _outcome(graph: StrategyGraph) -> OrganismChange | None:
    return outcome_for_graph(
        graph=graph,
        sync_state=WDKSyncState(),
        counts={},
        failed_step_ids=[],
        wdk_url=None,
    ).organism_change


def test_a_carry_records_the_organism_of_the_records() -> None:
    assert _outcome(_graph(_TARGET)) == OrganismChange(
        seed=[_SOURCE], records=[_TARGET]
    )


def test_a_carry_there_and_back_and_a_seed_alone_record_no_change() -> None:
    assert (_outcome(_graph(_TARGET, _SOURCE)), _outcome(_graph())) == (None, None)


def test_the_ledger_prints_whose_records_they_are() -> None:
    graph = _graph(_TARGET)
    outcome = outcome_for_graph(
        graph=graph,
        sync_state=WDKSyncState(),
        counts={},
        failed_step_ids=[],
        wdk_url=None,
    )

    rendered = render_build_full(BuildSection(outcome=outcome))

    records = [line for line in rendered.splitlines() if line.startswith("- records")]
    assert records == [f"- records: {_TARGET} (the seed searched {_SOURCE})"]


async def test_a_build_of_a_carry_records_the_organism_of_the_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    serve_the_catalog(monkeypatch)
    session = StrategySession(site_id="plasmodb")
    session.graph = StrategyGraph("g1", "Orthologs", "plasmodb")
    session.graph.record_type = "transcript"
    root = _graph(_TARGET).to_strategy_ast()
    assert root is not None

    outcome = await build_strategy_from_spec(
        deps=StrategyMutationContext(site_id="plasmodb", strategy_session=session),
        root=root.root,
    )

    assert outcome.organism_change == OrganismChange(seed=[_SOURCE], records=[_TARGET])


async def test_a_resync_after_recovery_reads_the_organism_of_the_tree_it_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _sync(**_kwargs: object) -> SyncResult:
        return SyncResult(
            wdk_strategy_id=330679883,
            wdk_url=None,
            root_step_id=440537303,
            counts={},
            root_count=67,
            zero_step_ids=[],
            step_count=2,
        )

    monkeypatch.setattr(sub_agent_dispatch, "sync_strategy_for_site", _sync)
    session = StrategySession(site_id="plasmodb")
    session.graph = _graph(_TARGET)
    deps = lead_deps(pipeline_state(user_prompt="carry"), strategy_session=session)

    fresh = await sub_agent_dispatch._resync_outcome(
        agent_deps_for(deps), BuildOutcome()
    )

    assert fresh.organism_change == OrganismChange(seed=[_SOURCE], records=[_TARGET])
