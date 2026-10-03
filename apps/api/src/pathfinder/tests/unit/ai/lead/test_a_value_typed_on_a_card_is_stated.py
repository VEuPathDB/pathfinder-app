"""Words the researcher typed on a card are theirs: a value they hold binds as
stated, as a value their message holds does."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import ConsultOption, UserQuestionAnswer
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import apply_option_bindings
from pathfinder.ai.tools.standalone._frame_sources import bound_values
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.questions import OpenQuestion
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_FLOOR = "min_expression_percentile"
_PROMPT = "How strictly must the genes be expressed in trophozoites?"
_REQUEST = "Also require that they are expressed in trophozoites."


def _question() -> OpenQuestion:
    return OpenQuestion(question=_PROMPT, dimension=ConstraintKind.PERCENTILE)


# The card as it was asked, with two labels that bind nothing.
_CARD = CardQuestion(
    id="q1",
    prompt=_PROMPT,
    dimension=ConstraintKind.PERCENTILE,
    options=[
        ConsultOption(label="Another floor"),
        ConsultOption(label="A lower floor"),
    ],
)


def _floor_after(answer: UserQuestionAnswer) -> str:
    state = pipeline_state(
        "amoebadb",
        user_prompt=_REQUEST,
        user_message_id=uuid4(),
        domain=StrategyDomainState(open_questions=[_question()]),
    )

    apply_option_bindings(state, [answer], [_CARD], sheets={})

    bound = bound_values(
        {_FLOOR: StringValue(value="90")},
        infos=[],
        site_supplied=set(),
        request_texts=state.researcher_messages(),
        reason="",
    )
    return bound[_FLOOR].source


def test_a_value_in_the_note_of_a_free_text_answer_binds_as_stated() -> None:
    answer = UserQuestionAnswer(
        question_id="q1",
        prompt=_PROMPT,
        chosen_labels=["Another floor"],
        note="percentile 90",
    )

    assert _floor_after(answer) == "stated"


def test_a_value_typed_as_the_answer_binds_as_stated() -> None:
    answer = UserQuestionAnswer(
        question_id="q1", prompt=_PROMPT, chosen_labels=["percentile 90"]
    )

    assert _floor_after(answer) == "stated"


def test_the_label_of_an_option_the_researcher_picked_is_not_their_words() -> None:
    answer = UserQuestionAnswer(
        question_id="q1", prompt=_PROMPT, chosen_labels=["Another floor"]
    )

    state = pipeline_state(
        "amoebadb",
        user_prompt=_REQUEST,
        user_message_id=uuid4(),
        domain=StrategyDomainState(open_questions=[_question()]),
    )
    apply_option_bindings(state, [answer], [_CARD], sheets={})

    assert state.researcher_messages() == [_REQUEST]


def test_the_label_of_an_option_the_researcher_picked_is_no_requirement() -> None:
    answer = UserQuestionAnswer(
        question_id="q1", prompt=_PROMPT, chosen_labels=["Another floor"]
    )
    state = pipeline_state(
        "amoebadb",
        user_prompt=_REQUEST,
        user_message_id=uuid4(),
        domain=StrategyDomainState(open_questions=[_question()]),
    )

    apply_option_bindings(state, [answer], [_CARD], sheets={})

    assert state.domain.requirements == []
