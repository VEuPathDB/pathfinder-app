"""Every option a question card offers carries what answering it binds: values
on a criterion, or the withdrawal or keeping of a requirement. A label is never
a requirement, so a question that binds no slot offers no option."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.questions import (
    AskedQuestion,
    Keep,
    OpenQuestion,
    SetValues,
    SlotQuestion,
    TypedOption,
    Withdraw,
)

_PERCENTILE = "min_expression_percentile"


def test_a_slot_question_offers_options_that_set_the_slot() -> None:
    asked = SlotQuestion(
        question="Which expression floor?",
        dimension=ConstraintKind.PERCENTILE,
        recommended_value="50",
        criterion_id="c_expr",
        param_name=_PERCENTILE,
        options=["50", "80", "80"],
    )

    assert asked.typed().options == [
        TypedOption(
            id="50",
            label="50",
            binding=SetValues(criterion_id="c_expr", params={_PERCENTILE: "50"}),
        ),
        TypedOption(
            id="80",
            label="80",
            binding=SetValues(criterion_id="c_expr", params={_PERCENTILE: "80"}),
        ),
    ]


def test_a_slot_question_keeps_what_it_asks_and_recommends() -> None:
    typed = SlotQuestion(
        question="Which stage?",
        dimension=ConstraintKind.OTHER,
        recommended_value="ring",
        criterion_id="c_stage",
        param_name="stage",
        options=["ring", "trophozoite"],
    ).typed()

    assert (typed.question, typed.recommended_value) == ("Which stage?", "ring")


def test_a_question_that_names_no_slot_offers_no_option() -> None:
    typed = SlotQuestion(
        question="Which saved strategy?",
        options=["kinase panel", "surfaceome v2"],
    ).typed()

    assert (typed.question, typed.options) == ("Which saved strategy?", [])


def test_the_leads_question_is_answered_in_the_researchers_words() -> None:
    typed = AskedQuestion(
        question="Which organism?", options=["P. vivax", "P. knowlesi"]
    ).typed()

    assert typed.options == []


def test_a_free_text_binding_does_not_exist() -> None:
    with pytest.raises(ValidationError):
        TypedOption.model_validate(
            {"id": "other", "label": "Another floor", "binding": {"kind": "free_text"}}
        )


def test_a_withdraw_option_names_the_requirement_key() -> None:
    option = TypedOption(
        id="drop-exported",
        label="Drop the exported requirement",
        binding=Withdraw(constraint_id="other:exported"),
    )

    keep = TypedOption(
        id="keep-exported",
        label="Keep the exported requirement",
        binding=Keep(constraint_id="other:exported"),
    )

    assert OpenQuestion(question="Drop it?", options=[option, keep]).options == [
        option,
        keep,
    ]


def test_two_options_with_one_id_are_refused() -> None:
    twice = TypedOption(id="a", label="a", binding=Keep(constraint_id="other:a"))

    with pytest.raises(ValidationError):
        OpenQuestion(question="Which?", options=[twice, twice])


def test_a_set_values_binding_sets_at_least_one_value() -> None:
    with pytest.raises(ValidationError):
        SetValues(criterion_id="c_expr", params={})


def test_an_option_round_trips_through_its_wire_form() -> None:
    option = TypedOption(
        id="50",
        label="50",
        binding=SetValues(criterion_id="c_expr", params={_PERCENTILE: "50"}),
    )

    dumped = option.model_dump(by_alias=True, mode="json")

    assert (dumped["binding"]["criterionId"], TypedOption.model_validate(dumped)) == (
        "c_expr",
        option,
    )
