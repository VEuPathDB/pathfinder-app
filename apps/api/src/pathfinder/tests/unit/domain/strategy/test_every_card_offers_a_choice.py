"""A question that offers options offers at least two, each binding something
the others do not; no path builds one that offers a single option."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.questions import (
    AskedQuestion,
    OpenQuestion,
    SetValues,
    SlotQuestion,
    TypedOption,
)

_TM_PROMPT = (
    "How should the strategy handle a signal peptide that may be counted as one "
    "transmembrane helix?"
)


def _sets(option_id: str, value: str) -> TypedOption:
    return TypedOption(
        id=option_id,
        label=f"Minimum Number of Transmembrane Domains {value}",
        binding=SetValues(criterion_id="step_tm", params={"min_tm": value}),
    )


def test_a_question_with_one_option_is_refused_where_it_is_built() -> None:
    with pytest.raises(ValidationError) as refused:
        OpenQuestion(question=_TM_PROMPT, options=[_sets("three", "3")])

    assert "offers one option, 'Minimum Number of Transmembrane Domains 3'" in str(
        refused.value
    )


def test_two_options_that_bind_the_same_values_are_one_option() -> None:
    with pytest.raises(ValidationError, match="bind the same"):
        OpenQuestion(
            question=_TM_PROMPT, options=[_sets("three", "3"), _sets("3", "3")]
        )


def test_a_question_offering_two_values_is_asked() -> None:
    asked = OpenQuestion(
        question=_TM_PROMPT, options=[_sets("two", "2"), _sets("three", "3")]
    )

    assert [o.binding for o in asked.options] == [
        SetValues(criterion_id="step_tm", params={"min_tm": "2"}),
        SetValues(criterion_id="step_tm", params={"min_tm": "3"}),
    ]


def test_a_free_text_question_offers_no_option() -> None:
    assert OpenQuestion(question=_TM_PROMPT).options == []


def test_a_question_a_model_writes_with_one_label_is_refused() -> None:
    """A card whose one option is the cutoff to apply offers no choice."""
    with pytest.raises(ValidationError, match=r"offers one option, '1\.5'"):
        AskedQuestion(
            question=(
                "Should the step be recreated with an absolute effect-size cutoff of 1.5?"
            ),
            dimension=ConstraintKind.STATISTICAL_THRESHOLD,
            options=["1.5"],
        )


def test_a_slot_question_frame_writes_with_one_value_is_refused() -> None:
    with pytest.raises(ValidationError, match="offers one option"):
        SlotQuestion(
            question=_TM_PROMPT,
            criterion_id="step_tm",
            param_name="min_tm",
            options=["3"],
        )


def test_the_labels_of_a_question_that_binds_nothing_are_no_options() -> None:
    asked = AskedQuestion(
        question=_TM_PROMPT,
        options=[
            "Keep the current inclusive rule: at least 2 predicted TM domains",
            "Use a conservative corrected rule: at least 3 predicted TM domains",
        ],
    ).typed()

    assert asked.options == []


def test_a_fold_threshold_on_the_log2_scale_offers_both_readings_of_a_number() -> None:
    """A number offered for a log2(Fold Change) cut binds as a fold and as a
    log2 value."""
    analysis = Criterion(
        id="step_a036deb7",
        text="Genes higher in serum at 37C than at 30C",
        param_display_names={"effect_size_threshold": "log2(Fold Change)"},
    )

    asked = SlotQuestion(
        question=(
            "The differential-expression step is bound with an effect-size cutoff "
            "of 1. Which cutoff should it use?"
        ),
        dimension=ConstraintKind.FOLD_CHANGE,
        criterion_id="step_a036deb7",
        param_name="effect_size_threshold",
        options=["1.5", "1"],
    ).typed(analysis, noun="gene")

    def _sets(value: str) -> SetValues:
        return SetValues(
            criterion_id="step_a036deb7", params={"effect_size_threshold": value}
        )

    assert [(o.label, o.binding) for o in asked.options] == [
        ("log2(Fold Change) 0.585 (1.5-fold)", _sets("0.585")),
        ("log2(Fold Change) 1.5 (2.83-fold)", _sets("1.5")),
        ("log2(Fold Change) 0 (1-fold)", _sets("0")),
        ("log2(Fold Change) 1 (2-fold)", _sets("1")),
    ]
