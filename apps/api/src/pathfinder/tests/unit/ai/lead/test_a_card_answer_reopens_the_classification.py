"""A card answer under the same message is classified once more, and its stated
requirements reach the intent and the thread; a repeat of the same answer's
classification is still refused."""

from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from pydantic_ai.exceptions import ToolFailed

from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
    user_intent,
)

pytestmark = pytest.mark.usefixtures("recorded_site_organisms")

_MESSAGE = "Find the GPI-anchored surface proteins of Trypanosoma congolense IL3000"
_TERM_QUESTION = "Which text term should the search use?"
_SECOND_ANSWER = (
    'use the phrase "GPI anchored", and also include the variant surface '
    "glycoprotein products"
)
_PHRASE = requirement(ConstraintKind.OTHER, "Phrase", "GPI anchored")
_VSG = requirement(ConstraintKind.OTHER, "VSG products", "variant surface glycoprotein")


async def _answer_card(deps: LeadDeps, call_id: str, note: str) -> None:
    card = CardQuestion(id="q1", prompt=_TERM_QUESTION, options=[])
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id=call_id, tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        call_id: [
            UserQuestionAnswer(
                question_id=card.id, prompt=card.prompt, chosen_labels=[], note=note
            )
        ]
    }
    await consult_user(
        run_context_for(deps, call_id), questions=[card], reply="One question."
    )


async def _deps_after_the_first_answer() -> LeadDeps:
    deps = lead_deps(pipeline_state("tritrypdb", user_prompt=_MESSAGE))
    ctx = run_context_for(deps, tool_call_id="call_classify")
    await classify_user_intent(ctx, user_intent(IntentClassification.NEW_STRATEGY))
    await _answer_card(deps, "call_consult_1", "a text search")
    await classify_user_intent(
        ctx, user_intent(IntentClassification.CLARIFICATION_RESPONSE)
    )
    return deps


async def test_a_second_card_answer_is_classified_with_its_stated_parts() -> None:
    deps = await _deps_after_the_first_answer()
    await _answer_card(deps, "call_consult_2", _SECOND_ANSWER)
    answer = user_intent(
        IntentClassification.CLARIFICATION_RESPONSE,
        explicit_constraints=[_PHRASE, _VSG],
    )

    await classify_user_intent(run_context_for(deps, "call_classify_2"), answer)

    assert deps.intent is not None
    assert [c.key for c in deps.intent.explicit_constraints] == [
        "other:GPI anchored",
        "other:variant surface glycoprotein",
    ]
    assert [
        (c.key, c.source.value) for c in deps.state.turn_markers.requirements_added
    ] == [
        ("other:GPI anchored", "user_explicit"),
        ("other:variant surface glycoprotein", "user_explicit"),
    ]


async def test_a_repeated_classification_of_the_same_answer_is_refused() -> None:
    deps = await _deps_after_the_first_answer()

    with pytest.raises(ToolFailed) as refused:
        await classify_user_intent(
            run_context_for(deps, "call_classify_2"),
            user_intent(IntentClassification.CLARIFICATION_RESPONSE),
        )

    assert "already classified as clarification_response" in refused.value.message


async def test_a_second_answer_classified_twice_is_refused_the_second_time() -> None:
    deps = await _deps_after_the_first_answer()
    await _answer_card(deps, "call_consult_2", _SECOND_ANSWER)
    answer = user_intent(
        IntentClassification.CLARIFICATION_RESPONSE, explicit_constraints=[_PHRASE]
    )
    ctx = run_context_for(deps, "call_classify_2")
    await classify_user_intent(ctx, answer)

    with pytest.raises(ToolFailed) as refused:
        await classify_user_intent(ctx, answer)

    assert "already classified as clarification_response" in refused.value.message
