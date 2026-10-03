"""The turn contract refuses every answer whose prose writes a fact outside a
reference, or names a fact the turn's facts lack, and its correction names the
reference that renders each fact. A typed reply and a card's reply are held
the same way, after the message's other correction too."""

from __future__ import annotations

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

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.card_contract import hold_the_contract_on_a_card
from pathfinder.ai.lead.card_reply import REPLY_REFERENCES
from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    CONTRACT_HEADING,
    hold_the_turn_contract,
    reconcile,
    to_correct,
)
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.caveats import RequirementGap
from pathfinder.domain.reply_references import ProseFault
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.orthology import OrganismChange
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.turn_facts import ParameterFact, StepFact, TurnFacts
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reading_deps, reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# microsporidiadb, build 71: E. intestinalis signal peptide 66, the E. cuniculi
# ortholog exclusion 129, 9 in both.
_REFERENCED = (
    "Without the ortholog filter the signal peptide step returns [count:step_sp] "
    "against [root] now, so the filter removes [diff:step_sp,root]."
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


def test_a_reply_that_writes_every_count_by_reference_stands() -> None:
    deps = _micro()
    answer = reply(_REFERENCED)

    assert hold_the_turn_contract(run_context_for(deps), answer) is answer


def test_a_written_count_is_refused_with_the_reference_that_renders_it() -> None:
    deps = _micro()

    with pytest.raises(ModelRetry) as refused:
        hold_the_turn_contract(run_context_for(deps), reply(_WRITTEN))

    assert str(refused.value) == "\n\n".join(
        [
            CONTRACT_HEADING,
            unrendered_prose_message(
                [
                    ProseFault(
                        token="66", kind="number", references=("[count:step_sp]",)
                    ),
                    ProseFault(
                        token="57",
                        kind="number",
                        references=("[diff:step_sp,step_join]", "[diff:step_sp,root]"),
                    ),
                ]
            ),
        ]
    )


def test_the_correction_names_the_token_and_the_reference() -> None:
    message = unrendered_prose_message(
        [
            ProseFault(token="57", kind="number", references=("[diff:step_sp,root]",)),
            ProseFault(token="628", kind="number"),
            ProseFault(token="[count:step_gone]", kind="unheld_reference"),
        ]
    )

    assert message.splitlines()[1:] == [
        "- ``57``: write ``[diff:step_sp,root]``, which renders it.",
        "- ``628``: no fact holds it, so take it out.",
        "- ``[count:step_gone]`` names nothing the facts hold.",
    ]


def test_the_correction_says_a_malformed_reference_is_no_reference() -> None:
    message = unrendered_prose_message(
        [ProseFault(token="[count:]", kind="malformed_reference")]
    )

    assert message.splitlines()[1:] == [
        (
            "- ``[count:]`` is no reference the product reads: write one of the "
            "references above, or take the brackets out."
        ),
    ]


def test_the_correction_lists_every_reference_the_product_renders() -> None:
    message = unrendered_prose_message([ProseFault(token="628", kind="number")])

    assert message.splitlines()[0] == (
        f"Your reply writes facts the product renders. {REPLY_REFERENCES} Keep "
        "every other part of the reply as it is."
    )


def test_prose_is_refused_on_every_answer_after_the_messages_one_correction() -> None:
    deps = _micro()
    deps.state.turn_markers.contract_refused = True
    ctx = run_context_for(deps)

    with pytest.raises(ModelRetry, match="57"):
        hold_the_turn_contract(ctx, reply(_WRITTEN))
    with pytest.raises(ModelRetry, match="57"):
        hold_the_turn_contract(ctx, reply(_WRITTEN))


def test_a_reference_to_a_step_the_strategy_lacks_is_refused() -> None:
    deps = _micro()
    record = turn_record(run_context_for(deps))

    answer = reply("It returns [count:step_gone].")

    [mismatch] = to_correct(run_context_for(deps), answer, record, [answer.prose])

    assert (mismatch.kind, mismatch.sentence.splitlines()[1]) == (
        "unrendered_prose",
        "- ``[count:step_gone]`` names nothing the facts hold.",
    )


def test_a_cards_reply_is_held_to_the_references() -> None:
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
    assert "``57``: write ``[diff:step_sp,step_join]``" in denial.message


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
                args={"questions": [], "reply": f"{filler}It is [count:step_gone]."},
                tool_call_id="call_second",
            ),
        ]
    )

    results = hold_the_contract_on_a_card(run_context_for(deps), requests)

    assert results is not None
    denial = results.approvals["call_second"]
    assert isinstance(denial, ToolDenied)
    assert "``[count:step_gone]`` names nothing the facts hold." in denial.message


def test_the_rules_read_the_reply_as_the_researcher_reads_it() -> None:
    """A value the reply names by reference names the organism the records moved to."""
    state = pipeline_state(
        user_prompt="Carry these to their orthologs in Plasmodium vivax P01.",
        user_message_id=uuid4(),
    )
    state.record_build(
        BuildOutcome(
            pushed_step_ids=["s1", "s2"],
            organism_change=OrganismChange(
                seed=["Plasmodium falciparum 3D7"], records=["Plasmodium vivax P01"]
            ),
        )
    )
    state.turn_markers.verified = True
    record = turn_record(run_context_for(lead_deps(state))).model_copy(
        update={
            "facts": TurnFacts(
                steps=[
                    StepFact(
                        step_id="s2",
                        display_name="Orthologs",
                        parameters=[
                            ParameterFact(
                                name="organism",
                                display_name="Organism",
                                value="Plasmodium vivax P01",
                                source="stated",
                            )
                        ],
                    )
                ]
            )
        }
    )
    named = reply("The strategy now holds genes of [value:s2.organism].", changed=True)
    unnamed = reply("The strategy now holds the genes.", changed=True)

    assert [m.kind for m in reconcile(named, record)] == []
    assert [m.kind for m in reconcile(unnamed, record)] == ["unnamed_record_organism"]


def test_a_failed_gap_named_only_by_a_value_reference_is_named() -> None:
    """The failed-check rule reads the rendered reply, so a gap the reply names
    through a value reference is stated."""
    deps = reading_deps()
    domain = deps.state.domain
    domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="The ortholog exclusion is not answered.",
            success=False,
            gaps=[RequirementGap(text="Neospora caninum Liverpool", status="unmet")],
        ),
        revision=strategy_revision(domain.answered_graph),
    )
    facts = TurnFacts(
        steps=[
            StepFact(
                step_id="s2",
                display_name="Orthology Phylogenetic Profile",
                parameters=[
                    ParameterFact(
                        name="excluded_species",
                        display_name="Excluded Species",
                        value="ncan",
                        label="Neospora caninum Liverpool",
                        source="stated",
                    )
                ],
            )
        ]
    )
    record = turn_record(run_context_for(deps)).model_copy(update={"facts": facts})
    named = reply("The check found the exclusion of [value:s2.excluded_species] unmet.")
    unnamed = reply("The check found the exclusion unmet.")

    assert (
        [m.kind for m in reconcile(named, record)],
        [m.kind for m in reconcile(unnamed, record)],
    ) == ([], ["failed_check"])
