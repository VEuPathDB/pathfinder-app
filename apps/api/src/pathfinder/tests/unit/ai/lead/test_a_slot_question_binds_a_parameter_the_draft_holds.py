"""A question that names a slot binds only a parameter its criterion holds, open
or bound; a question that names none is held to the draft's open slots."""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_questions import questions_that_bind_to_nothing
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SlotQuestion

_FLOOR = "min_expression_percentile"


def _draft(*, open_floor: bool) -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_troph",
                text="expressed in trophozoites",
                search_name="GenesByRNASeqPercentile",
                resolved_params=(
                    {}
                    if open_floor
                    else {
                        _FLOOR: BoundValue(
                            value=NumberValue(value=80), source="default"
                        )
                    }
                ),
                open_params=(
                    [OpenSlot(criterion_id="c_troph", param_name=_FLOOR)]
                    if open_floor
                    else []
                ),
            )
        ]
    )


def _asks(criterion_id: str, param_name: str) -> SlotQuestion:
    return SlotQuestion(
        question="How strictly must the genes be expressed?",
        dimension=ConstraintKind.PERCENTILE,
        recommended_value="1",
        criterion_id=criterion_id,
        param_name=param_name,
        options=["1", "80"],
    )


def _asked(*questions: SlotQuestion, unstated: tuple[str, ...] = ()) -> FrameResult:
    return FrameResult(
        disposition="needs_user",
        open_questions=list(questions),
        unstated=list(unstated),
    )


def test_a_question_on_an_open_slot_binds() -> None:
    draft = _draft(open_floor=True)

    assert (
        questions_that_bind_to_nothing(_asked(_asks("c_troph", _FLOOR)), draft, None)
        == ""
    )


def test_a_question_on_a_value_the_site_defaulted_binds() -> None:
    """Asking a bound value again changes it, even over an untouched draft."""
    draft = _draft(open_floor=False)

    assert (
        questions_that_bind_to_nothing(_asked(_asks("c_troph", _FLOOR)), draft, draft)
        == ""
    )


def test_a_question_on_a_parameter_the_criterion_lacks_is_refused() -> None:
    refusal = questions_that_bind_to_nothing(
        _asked(_asks("c_troph", "max_expression_percentile")),
        _draft(open_floor=True),
        None,
    )

    assert "max_expression_percentile" in refusal
    assert f"c_troph: {_FLOOR}" in refusal


def test_a_question_on_a_criterion_the_draft_lacks_is_refused() -> None:
    refusal = questions_that_bind_to_nothing(
        _asked(_asks("c_gone", _FLOOR)), _draft(open_floor=True), None
    )

    assert "c_gone" in refusal


def test_a_question_that_names_half_a_slot_is_refused() -> None:
    refusal = questions_that_bind_to_nothing(
        _asked(_asks("c_troph", "")), _draft(open_floor=True), None
    )

    assert "criterion_id and param_name" in refusal


def test_a_question_about_a_requirement_the_pass_names_unstated_binds() -> None:
    """Its answer lands on the requirement, through the drop and keep options."""
    free = SlotQuestion(
        question="No search on this site states a predicted GPI anchor. Drop it?",
        dimension=ConstraintKind.DATA_TYPE,
        recommended_value="GenesWithSignalPeptide",
    )

    assert (
        questions_that_bind_to_nothing(
            _asked(free, unstated=("predicted GPI anchor",)),
            _draft(open_floor=False),
            None,
        )
        == ""
    )


def test_a_free_question_on_a_draft_with_no_open_slot_is_refused() -> None:
    free = SlotQuestion(
        question="Which evidence should stand in?",
        dimension=ConstraintKind.DATA_TYPE,
        recommended_value="GenesWithSignalPeptide",
    )

    refusal = questions_that_bind_to_nothing(
        _asked(free, unstated=("predicted GPI anchor",)),
        _draft(open_floor=False),
        None,
    )

    assert "no criterion of the spec holds an open slot" in refusal
