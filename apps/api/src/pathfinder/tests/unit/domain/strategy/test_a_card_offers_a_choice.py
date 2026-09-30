"""A question reaches the card only when it offers a choice: a question with one
option, one whose offered values bind one term, or one the researcher
answered, is never asked."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from veupathdb.domain.parameters import SinglePickValue, StringValue

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import (
    Keep,
    OpenQuestion,
    SetValues,
    SlotQuestion,
    TypedOption,
    Withdraw,
    unanswered_questions,
    with_withdrawals,
)

_COMPARISONS = "samples_fc_direct_generic_page"
_PNA_TERM = "pnaVsPromastigote (microarray)"
_PNA_LABEL = (
    "PNA - Metacyclic Promastigote vs. Early Log Procyclic Promastigote (microarray)"
)
_PROMPT = (
    "No amastigote-versus-promastigote comparison is available. Use the "
    "available PNA-versus-early-log-promastigote comparison, or leave the "
    "expression criterion unchanged?"
)


def _lmajor_study() -> Criterion:
    """The tritrypdb expression step as the thread held it: the comparison is
    the site's default term, whose label a vocabulary reading records."""
    return Criterion(
        id="step_bb9551dc",
        text="up-regulated in amastigotes compared with promastigotes",
        search_name=(
            "GenesByMicroarrayDirectWithConfidencelmajFriedlin_microarrayExpression_"
            "E-MEXP-1864_Beverley_Steve_LifeStages_RSRC"
        ),
        resolved_params={
            _COMPARISONS: BoundValue(
                value=SinglePickValue(value=_PNA_TERM), source="default"
            ),
            "fold_change": BoundValue(value=StringValue(value="2"), source="default"),
        },
        param_display_names={_COMPARISONS: "Comparisons"},
        measurements=[
            Measurement(
                kind="vocabulary_label",
                param=_COMPARISONS,
                label=_PNA_LABEL,
                reading=_PNA_TERM,
            )
        ],
        result_count=142,
    )


def _asks(*values: str) -> OpenQuestion:
    return SlotQuestion(
        question=_PROMPT,
        dimension=ConstraintKind.DATA_TYPE,
        recommended_value=_PNA_LABEL,
        criterion_id="step_bb9551dc",
        param_name=_COMPARISONS,
        options=list(values),
    ).typed(_lmajor_study(), noun="gene")


def test_an_option_spelled_as_the_held_label_binds_the_held_term() -> None:
    held, other = _asks(_PNA_LABEL, "amastigoteVsPromastigote (microarray)").options

    assert held.binding == SetValues(
        criterion_id="step_bb9551dc", params={_COMPARISONS: _PNA_TERM}
    )
    assert held.label == f"Comparisons {_PNA_LABEL}: 142 genes"
    assert other.label == "Comparisons amastigoteVsPromastigote (microarray)"


def test_a_question_whose_only_option_is_the_held_value_is_refused() -> None:
    """The tritrypdb card: one option, the comparison the step already runs."""
    with pytest.raises(ValidationError, match="offers one option"):
        _asks(_PNA_LABEL)


def test_a_question_offering_the_held_value_beside_another_is_asked() -> None:
    asked = _asks(_PNA_LABEL, "amastigoteVsPromastigote (microarray)")

    assert unanswered_questions([asked]) == [asked]


def test_a_single_option_for_an_open_slot_is_refused() -> None:
    with pytest.raises(ValidationError, match="offers one option"):
        SlotQuestion(
            question=_PROMPT,
            criterion_id="step_bb9551dc",
            param_name=_COMPARISONS,
            options=[_PNA_TERM],
        )


_FOLD = Constraint(
    kind=ConstraintKind.FOLD_CHANGE,
    requested_value="1.5-fold",
    label="fold-change cutoff",
    source=ConstraintSource.USER_EXPLICIT,
)


def test_a_requirement_no_question_asks_is_offered_to_drop_or_keep() -> None:
    [asked] = with_withdrawals([], [_FOLD])

    assert [(o.label, o.binding) for o in asked.options] == [
        ("Drop 1.5-fold", Withdraw(constraint_id="fold_change:1.5-fold")),
        ("Keep 1.5-fold", Keep(constraint_id="fold_change:1.5-fold")),
    ]


def test_a_question_whose_only_option_withdraws_is_refused() -> None:
    with pytest.raises(ValidationError, match="offers one option"):
        OpenQuestion(
            question="No search on this site states '1.5-fold'. Drop it?",
            options=[
                TypedOption(
                    id="drop",
                    label="Drop 1.5-fold",
                    binding=Withdraw(constraint_id=_FOLD.key),
                )
            ],
        )


def test_a_question_the_researcher_answered_is_not_asked_again() -> None:
    asked = _asks(_PNA_LABEL, "amastigoteVsPromastigote (microarray)")

    assert unanswered_questions([asked], answered=[_PROMPT]) == []


def test_a_question_offering_one_value_twice_is_refused() -> None:
    with pytest.raises(ValidationError, match="offers one option"):
        _asks(_PNA_LABEL, _PNA_LABEL)


def test_a_term_and_its_label_are_one_option_so_the_question_is_not_asked() -> None:
    """The held term and the label the site gives it bind one value, so the
    question offers no choice and a pass that asks it records none."""
    asks = SlotQuestion(
        question=_PROMPT,
        dimension=ConstraintKind.DATA_TYPE,
        criterion_id="step_bb9551dc",
        param_name=_COMPARISONS,
        options=[_PNA_TERM, _PNA_LABEL],
    )
    result = FrameResult(disposition="needs_user", open_questions=[asks])

    assert asks.offers_a_choice(_lmajor_study()) is False
    assert result.questions(OperationalSpec(criteria=[_lmajor_study()])) == []
