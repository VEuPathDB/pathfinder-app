"""The mock reads the root's organism from the graph pin a sub-agent carries,
down the primary inputs of the root."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

from pathfinder.ai.agents.strategy_instructions import pinned_graph_state
from pathfinder.ai.models.mock.graph_pin import pinned_root_organism
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_PF = "Plasmodium falciparum 3D7"
_PV = "Plasmodium vivax P01"


def _pinned(*steps: StrategyStep) -> str:
    graph = StrategyGraph("g1", "pinned", "plasmodb")
    graph.record_type = "transcript"
    for step in steps:
        add_step_to_graph(graph, step)
    session = StrategySession("plasmodb")
    session.add_graph(graph)
    return pinned_graph_state(agent_run_context(strategy_session=session)) or ""


def _leaf(step_id: str, organism: str) -> StrategyStep:
    return StrategyStep(
        id=step_id,
        kind=StepKind.SEARCH,
        search_name="GenesWithSignalPeptide",
        parameters={
            "signalp_version": StringValue(value="SignalP-6.0"),
            "organism": MultiPickValue(values=[organism]),
        },
    )


def test_a_combined_root_holds_the_organism_of_its_primary_input() -> None:
    pinned = _pinned(
        _leaf("left", _PF),
        _leaf("right", _PV),
        StrategyStep(
            id="both",
            kind=StepKind.COMBINE,
            primary_input_id="left",
            secondary_input_id="right",
            operator=CombineOp.INTERSECT,
        ),
    )

    assert pinned_root_organism(pinned) == _PF


def test_no_organism_down_the_root_and_no_graph_pin_name_none() -> None:
    text_only = _pinned(
        StrategyStep(
            id="text",
            kind=StepKind.SEARCH,
            search_name="GenesByText",
            parameters={"text_expression": StringValue(value="kinase")},
        )
    )
    unframed = "## Operational Spec\nNot framed yet."

    assert (pinned_root_organism(text_only), pinned_root_organism(unframed)) == (
        None,
        None,
    )
