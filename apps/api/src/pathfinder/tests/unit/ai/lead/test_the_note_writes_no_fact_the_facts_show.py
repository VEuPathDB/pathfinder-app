from uuid import uuid4

import pytest
from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDenied
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_contract import hold_the_contract_on_a_card
from pathfinder.ai.lead.card_reply import CARD_NOT_SHOWN, PROSE_MAX_CHARS
from pathfinder.ai.lead.contract_messages import note_facts_message
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import CONTRACT_HEADING, hold_the_turn_contract
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


def test_a_written_count_is_refused_with_each_number_it_writes() -> None:
    with pytest.raises(ModelRetry) as refused:
        hold_the_turn_contract(run_context_for(_micro()), reply(_WRITTEN))

    assert str(refused.value) == "\n\n".join(
        [CONTRACT_HEADING, note_facts_message(["66", "57"])]
    )


def test_the_correction_keeps_a_name_with_digits() -> None:
    message = note_facts_message(["66"])

    assert message == (
        "The note writes ``66``. The facts beside the reply show every count, "
        "value, setting and link of this turn as the site holds it, so the note "
        "writes none: take each out and keep the rest of the note as it is. A "
        "name with digits, such as a strain or a tool version, stays as "
        "written, and a record is named as [record:<record_id>]."
    )


def test_a_note_is_refused_up_to_the_bound_then_shown_unchecked() -> None:
    deps = _micro()
    deps.state.turn_markers.contract_refused = True
    ctx = run_context_for(deps)
    answer = reply(_WRITTEN)

    verdicts: list[object] = []
    for _ in range(REFUSALS_PER_CHECK + 1):
        try:
            verdicts.append(hold_the_turn_contract(ctx, answer))
        except ModelRetry:
            verdicts.append("refused")

    assert verdicts == ["refused", "refused", answer]
    assert deps.state.turn_markers.unchecked_reply is True


def test_a_reply_over_the_length_cap_is_clipped_to_it() -> None:
    assert len(reply("x" * (PROSE_MAX_CHARS + 5)).prose) == PROSE_MAX_CHARS


def test_a_cards_reply_is_held_to_the_note() -> None:
    deps = _micro()
    deps.state.turn_markers.contract_refused = True
    requests = DeferredToolRequests(
        approvals=[
            ToolCallPart(
                tool_name="consult_user",
                args={"questions": [], "reply": _WRITTEN},
                tool_call_id="call_card",
            )
        ]
    )

    results = hold_the_contract_on_a_card(run_context_for(deps), requests)

    assert results is not None
    denial = results.approvals["call_card"]
    assert isinstance(denial, ToolDenied)
    assert "``66``, ``57``" in denial.message
    assert denial.message.endswith(f"{CARD_NOT_SHOWN} Answer again with the card.")


def test_every_cards_reply_is_held_whole_past_the_joined_length() -> None:
    deps = _micro()
    deps.state.turn_markers.contract_refused = True
    filler = "The step keeps the secreted genes of the organism. " * 48
    requests = DeferredToolRequests(
        approvals=[
            ToolCallPart(
                tool_name="consult_user",
                args={"questions": [], "reply": f"{filler}Which field?"},
                tool_call_id="call_first",
            ),
            ToolCallPart(
                tool_name="consult_user",
                args={"questions": [], "reply": f"{filler}It keeps 129 genes."},
                tool_call_id="call_second",
            ),
        ]
    )

    results = hold_the_contract_on_a_card(run_context_for(deps), requests)

    assert results is not None
    denial = results.approvals["call_second"]
    assert isinstance(denial, ToolDenied)
    assert "``129``" in denial.message
