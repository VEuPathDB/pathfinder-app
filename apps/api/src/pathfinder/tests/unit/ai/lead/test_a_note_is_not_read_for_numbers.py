from uuid import uuid4

from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ToolCallPart
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_contract import hold_the_contract_on_a_card
from pathfinder.ai.lead.card_reply import PROSE_MAX_CHARS
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import hold_the_turn_contract
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_NOTE = (
    "Without the ortholog filter the signal peptide step keeps far more genes, "
    "so the filter is what narrows the result to the shared secretome."
)
_WRITTEN = "Without the ortholog filter the search returns 66 genes, 57 more."


def _micro() -> LeadDeps:
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
    graph = StrategyGraph(graph_id="g1", name="strategy", site_id="microsporidiadb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session = StrategySession(site_id="microsporidiadb")
    session.graph = graph
    session.sync_state = WDKSyncState(
        step_counts={"step_sp": 66, "step_orth": 129, "step_join": 9}
    )
    state = pipeline_state(
        "microsporidiadb", user_message_id=uuid4(), domain=StrategyDomainState()
    )
    state.turn_markers.intent_classified = True
    return lead_deps(state, strategy_session=session)


def test_a_note_that_writes_no_fact_stands() -> None:
    deps = _micro()
    answer = reply(_NOTE)

    assert hold_the_turn_contract(run_context_for(deps), answer) == answer


def test_a_note_that_writes_numbers_stands_unmarked() -> None:
    deps = _micro()
    answer = reply(_WRITTEN)

    assert hold_the_turn_contract(run_context_for(deps), answer) == answer
    assert deps.state.turn_markers.unchecked_reply is False


def test_a_reply_over_the_length_cap_is_clipped_to_it() -> None:
    assert len(reply("x" * (PROSE_MAX_CHARS + 5)).prose) == PROSE_MAX_CHARS


def test_a_cards_reply_that_writes_numbers_reaches_the_card() -> None:
    requests = DeferredToolRequests(
        approvals=[
            ToolCallPart(
                tool_name="consult_user",
                args={"questions": [], "reply": _WRITTEN},
                tool_call_id="call_card",
            )
        ]
    )

    deps = _micro()
    held = hold_the_contract_on_a_card(run_context_for(deps), requests)

    assert (held, deps.state.turn_markers.output_refusals) == (None, 0)
