from __future__ import annotations

from strategist.ai.graph.rebuild import rebuilt_state
from strategist.ai.graph.state import PipelineState, StrategyDomainState
from strategist.ai.graph.stored_requirement_keys import questions_by_id
from strategist.ai.lead.derive import derive_ledger
from strategist.ai.lead.recorded_cards import card_questions
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.question_options import (
    Keep,
    SetValues,
    TypedOption,
    Withdraw,
)
from strategist.domain.strategy.questions import OpenQuestion, with_withdrawals
from strategist.tests.unit.ai.lead.conftest import pipeline_state

_PROMPT = "Should the condition be relaxed to an aggregate count?"
_COPIES = Constraint(
    kind=ConstraintKind.COUNT,
    requested_value="at least 2 copies and at most 5 copies",
    label="copies",
    source=ConstraintSource.USER_EXPLICIT,
)


def _sets(option_id: str, value: str) -> TypedOption:
    return TypedOption(
        id=option_id,
        label=f"Copies {value}",
        binding=SetValues(criterion_id="c_one", params={"copies": value}),
    )


def _withdraws(option_id: str, key: str) -> TypedOption:
    return TypedOption(
        id=option_id, label=f"Drop {option_id}", binding=Withdraw(constraint_id=key)
    )


def _question(*options: TypedOption) -> OpenQuestion:
    return OpenQuestion(question=_PROMPT, options=list(options))


def _stored_with_one_option() -> OpenQuestion:
    return _question().model_copy(update={"options": [_withdraws("copies", "k1")]})


class TestOptionsGoThroughTheRule:
    def test_down_to_one_leaves_none(self) -> None:
        narrowed = _question(_sets("one", "1"), _sets("two", "2")).with_options(
            [_sets("one", "1")]
        )

        assert narrowed.options == []

    def test_down_to_none_leaves_none(self) -> None:
        narrowed = _question(_sets("one", "1"), _sets("two", "2")).with_options([])

        assert narrowed.options == []

    def test_keeping_two_keeps_them_and_the_question(self) -> None:
        kept = [_sets("one", "1"), _sets("three", "3")]
        question = OpenQuestion(
            question=_PROMPT,
            dimension=ConstraintKind.COUNT,
            recommended_value="1",
            criterion_id="c_one",
            options=[*kept, _sets("two", "2")],
        )

        narrowed = question.with_options(kept)

        assert narrowed == question.model_copy(update={"options": kept})

    def test_the_question_it_narrows_is_not_changed(self) -> None:
        options = [_sets("one", "1"), _sets("two", "2")]
        question = _question(*options)

        question.with_options([])

        assert question.options == options

    def test_one_option_built_directly_leaves_none(self) -> None:
        assert _question(_sets("one", "1")).options == []

    def test_two_that_bind_one_value_are_one_option(self) -> None:
        assert _question(_sets("three", "3"), _sets("3", "3")).options == []

    def test_a_second_id_of_one_value_leaves_the_rest(self) -> None:
        question = _question(_sets("three", "3"), _sets("3", "3"), _sets("two", "2"))

        assert question.options == [_sets("three", "3"), _sets("two", "2")]

    def test_a_repeated_id_leaves_the_first(self) -> None:
        question = _question(_sets("one", "1"), _sets("one", "9"), _sets("two", "2"))

        assert question.options == [_sets("one", "1"), _sets("two", "2")]

    def test_two_stored_keys_of_one_requirement_are_one_option(self) -> None:
        question = _question(_withdraws("first", "k1"), _withdraws("second", "k2"))

        [held] = questions_by_id([question], {"k1": "the-id", "k2": "the-id"})

        assert held.options == []


class TestAWithdrawalOnAQuestionOfItsDimension:
    def test_a_free_text_question_stays_free_text_and_a_new_one_offers_both(
        self,
    ) -> None:
        free_text = OpenQuestion(question=_PROMPT, dimension=ConstraintKind.COUNT)

        kept, offered = with_withdrawals([free_text], [_COPIES], criteria=[])

        assert kept == free_text
        assert [o.binding for o in offered.options] == [
            Withdraw(constraint_id=_COPIES.id),
            Keep(constraint_id=_COPIES.id),
        ]

    def test_a_question_that_offers_values_gains_the_drop(self) -> None:
        question = OpenQuestion(
            question=_PROMPT,
            dimension=ConstraintKind.COUNT,
            options=[_sets("one", "1"), _sets("two", "2")],
        )

        [held] = with_withdrawals([question], [_COPIES], criteria=[])

        assert [o.id for o in held.options] == [
            "one",
            "two",
            "drop-at-least-2-copies-and-at-most-5-copies",
        ]

    def test_a_question_that_already_offers_the_drop_holds_it_once(self) -> None:
        offered = [
            _sets("one", "1"),
            _sets("two", "2"),
            _withdraws("earlier-drop", _COPIES.id),
        ]
        question = OpenQuestion(
            question=_PROMPT, dimension=ConstraintKind.COUNT, options=offered
        )

        [held] = with_withdrawals([question], [_COPIES], criteria=[])

        assert held.options == offered

    def test_a_free_text_question_that_names_it_offers_both(self) -> None:
        question = OpenQuestion(question=_PROMPT, requirement_ids=[_COPIES.id])

        [held] = with_withdrawals([question], [_COPIES], criteria=[])

        assert [o.binding for o in held.options] == [
            Withdraw(constraint_id=_COPIES.id),
            Keep(constraint_id=_COPIES.id),
        ]

    def test_the_ledger_derives_from_what_it_leaves(self) -> None:
        free_text = OpenQuestion(question=_PROMPT, dimension=ConstraintKind.COUNT)
        asked = with_withdrawals([free_text], [_COPIES], criteria=[])
        state = pipeline_state(domain=StrategyDomainState(open_questions=asked))

        ledger = derive_ledger(state, None)

        assert [len(q.options) for q in ledger.frame.open_questions] == [0, 2]


class TestAStoredQuestionThatBreaksTheRule:
    def _state(self) -> PipelineState:
        return pipeline_state(
            domain=StrategyDomainState().model_copy(
                update={"open_questions": [_stored_with_one_option()]}
            )
        )

    def test_a_ledger_derives_from_it_in_the_turn_that_holds_it(self) -> None:
        ledger = derive_ledger(self._state(), None)

        assert [(q.question, q.options) for q in ledger.frame.open_questions] == [
            (_PROMPT, [])
        ]

    def test_a_checkpoint_of_it_loads_and_derives(self) -> None:
        loaded = rebuilt_state(self._state())

        assert [(q.question, q.options) for q in loaded.domain.open_questions] == [
            (_PROMPT, [])
        ]
        assert [
            (q.question, q.options)
            for q in derive_ledger(loaded, None).frame.open_questions
        ] == [(_PROMPT, [])]

    def test_a_checkpoint_of_it_asks_a_card_in_words(self) -> None:
        loaded = rebuilt_state(self._state())

        [card] = card_questions(loaded.domain.open_questions)

        assert (card.prompt, card.options) == (_PROMPT, [])

    def test_an_answered_question_loads_too(self) -> None:
        state = pipeline_state(
            domain=StrategyDomainState().model_copy(
                update={"answered_questions": [_stored_with_one_option()]}
            )
        )

        loaded = rebuilt_state(state)

        assert [q.options for q in loaded.domain.answered_questions] == [[]]
