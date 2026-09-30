"""A proposal card's changes are typed by what they bind. The card's sentences
are the Lead's words: a yes states only what the researcher wrote."""

from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import UserQuestionAnswer
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_proposal import propose_changes
from pathfinder.ai.lead.proposal import (
    AddCriterionChange,
    CardProposal,
    Proposal,
    SetValuesChange,
)
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_RELATED = (
    "Include genes with related structural or surface-coat terminology where "
    "the catalog annotation supports that connection."
)
_SPORE_WALL_CARD = CardProposal(
    question=(
        "Should I build a gene-search strategy for the named organism's spore "
        "wall proteins?"
    ),
    proposed_changes=[
        AddCriterionChange(
            sentence=(
                "Search the catalog for genes whose product annotations refer to "
                "spore wall or spore-wall-associated proteins in the named organism."
            ),
            search_name="GenesByText",
            params={"text_expression": "spore wall"},
        ),
        AddCriterionChange(
            sentence=_RELATED,
            search_name="GenesByText",
            params={"text_expression": "surface coat OR structural"},
        ),
    ],
    reply="A first pass would combine direct and related annotation matches.",
)
# The requirements the classifier recorded once the researcher said yes.
_ACCEPTED = [
    Constraint(
        kind=ConstraintKind.ORGANISM,
        requested_value="Encephalitozoon cuniculi GB-M1",
        label="named organism",
        source=ConstraintSource.USER_EXPLICIT,
    ),
    Constraint(
        kind=ConstraintKind.OTHER,
        requested_value="spore wall or spore-wall-associated proteins",
        label="direct spore wall annotation",
        source=ConstraintSource.USER_EXPLICIT,
    ),
    Constraint(
        kind=ConstraintKind.OTHER,
        requested_value=(
            "related structural or surface-coat terminology where the catalog "
            "annotation supports that connection"
        ),
        label="related annotation terminology",
        source=ConstraintSource.USER_EXPLICIT,
        hard=False,
    ),
]


async def test_a_yes_states_only_what_the_researcher_wrote() -> None:
    """The microsporidiadb card: a yes, then the classification of the yes."""
    state = pipeline_state(
        "microsporidiadb",
        user_prompt="Yes",
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            original_request="Spore wall proteins in Encephalitozoon cuniculi GB-M1"
        ),
    )
    deps = lead_deps(state)

    with pytest.raises(ModelRetry, match="nothing to edit"):
        await propose_changes(run_context_for(deps, "call_card"), _SPORE_WALL_CARD)
    state.domain.record_intent(
        UserIntent(
            classification=IntentClassification.APPROVAL,
            inferred_goal="Build the accepted spore wall strategy.",
            explicit_constraints=_ACCEPTED,
        ),
        request_text="Yes",
    )

    assert [(c.requested_value, c.source) for c in state.domain.requirements] == [
        ("Encephalitozoon cuniculi GB-M1", ConstraintSource.USER_EXPLICIT),
        ("spore wall or spore-wall-associated proteins", ConstraintSource.ASSUMED),
        (_ACCEPTED[2].requested_value, ConstraintSource.ASSUMED),
    ]


def test_a_change_that_names_no_search_is_refused() -> None:
    """The vectorbase card: a more specific criterion, with no search named."""
    with pytest.raises(ValidationError, match=r"search_name|searchName"):
        Proposal.model_validate(
            {
                "question": "Tighten the cytochrome P450 criterion?",
                "proposedChanges": [
                    {
                        "kind": "add_criterion",
                        "sentence": (
                            "Replace the broad product-text criterion with a more "
                            "specific cytochrome P450 criterion."
                        ),
                    }
                ],
            }
        )


def test_a_change_that_sets_no_value_is_refused() -> None:
    with pytest.raises(ValidationError, match="params"):
        SetValuesChange(sentence="Tighten it.", criterion_id="step_p450", params={})


def test_a_change_written_as_a_sentence_alone_is_refused() -> None:
    with pytest.raises(ValidationError):
        Proposal.model_validate(
            {
                "question": "Tighten the cytochrome P450 criterion?",
                "proposedChanges": ["Use a more specific cytochrome P450 criterion."],
            }
        )


def test_the_brief_names_what_each_change_binds() -> None:
    proposal = Proposal(
        question="Use the Pfam domain for cytochrome P450?",
        proposed_changes=[
            SetValuesChange(
                sentence="Search the Pfam domain Cytochrome P450 in place of the text.",
                criterion_id="step_p450",
                params={"domain_accession": "PF00067"},
            )
        ],
    )

    assert proposal.brief("") == (
        "The researcher accepted this proposal: Use the Pfam domain for "
        "cytochrome P450?\n"
        "Make these changes:\n"
        "- Search the Pfam domain Cytochrome P450 in place of the text. "
        '(on criterion step_p450, set domain_accession to "PF00067")'
    )


def test_a_removal_is_no_change_a_card_offers() -> None:
    """The plasmodb card: a removal is the delete card's, which lists the cascade."""
    with pytest.raises(ValidationError, match="remove_criterion"):
        CardProposal.model_validate(
            {
                "question": "Drop the transmembrane-domain requirement?",
                "proposedChanges": [
                    {
                        "kind": "remove_criterion",
                        "sentence": (
                            "Remove the transmembrane-domain requirement from the "
                            "strategy, leaving the apicoplast-targeted gene search "
                            "as the starting set."
                        ),
                        "criterionId": "step_4dfb1df9",
                    }
                ],
                "reply": "The apicoplast search alone gives a broader set.",
            }
        )


async def test_a_card_sentence_is_never_the_researchers_words() -> None:
    state = pipeline_state(
        "microsporidiadb",
        user_prompt="Yes",
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            original_request="Spore wall proteins in Encephalitozoon cuniculi GB-M1"
        ),
    )
    state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1",
                prompt=_SPORE_WALL_CARD.question,
                chosen_labels=["Yes"],
                note="Keep it to annotated proteins.",
            )
        ]
    }

    with pytest.raises(ModelRetry, match="nothing to edit"):
        await propose_changes(
            run_context_for(lead_deps(state), "call_card"), _SPORE_WALL_CARD
        )

    assert state.domain.request_messages == ["Keep it to annotated proteins."]
