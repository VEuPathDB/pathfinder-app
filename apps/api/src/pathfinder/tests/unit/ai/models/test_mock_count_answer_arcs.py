"""The count arc answers with a step's count, the result's and their
difference, and the turn holds all three."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.models._mock_turns import Scene, names, play

# toxodb: GT1 signal peptide 680, the ncan exclusion 1,240, 53 in both.
_LIVE = {
    "rootCount": 53,
    "steps": [
        {
            "stepId": "step_sp",
            "displayName": "Predicted Signal Peptide",
            "estimatedSize": 680,
        },
        {
            "stepId": "step_orth",
            "displayName": "Orthology Phylogenetic Profile",
            "estimatedSize": 1240,
        },
        {
            "stepId": "step_join",
            "displayName": "Intersect",
            "estimatedSize": 53,
            "isRoot": True,
        },
    ],
}


def _toxo_turn():
    root = StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_sp", search_name="GenesWithSignalPeptide"
        ),
        secondary_input=StrategyStepNode(
            id="step_orth", search_name="GenesByOrthologPattern"
        ),
    )
    graph = StrategyGraph(graph_id="g1", name="strategy", site_id="toxodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session = StrategySession(site_id="toxodb")
    session.graph = graph
    session.sync_state = WDKSyncState(
        step_counts={"step_sp": 680, "step_orth": 1240, "step_join": 53}
    )
    state = pipeline_state(
        "toxodb", user_message_id=uuid4(), domain=StrategyDomainState()
    )
    return lead_deps(state, strategy_session=session)


def test_the_count_arc_answers_with_a_difference_the_turn_holds() -> None:
    calls = play(
        "lead",
        "toxodb",
        "How many did the ortholog filter remove? [[arc:derived-count]]",
        scene=Scene(answers={"get_live_strategy_state": _LIVE}),
    )
    prose = str(calls[-1].args_as_dict()["prose"])
    record = turn_record(run_context_for(_toxo_turn()))

    assert names(calls) == [
        "classify_user_intent",
        "get_live_strategy_state",
        "final_result",
    ]
    assert (prose, record.prose_refusal(prose, [])) == (
        (
            "The Predicted Signal Peptide step returns 680 genes and the result 53, "
            "so the other filters remove 627."
        ),
        None,
    )
