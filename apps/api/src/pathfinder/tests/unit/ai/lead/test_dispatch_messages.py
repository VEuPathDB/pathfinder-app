"""What a dispatch tool tells the model when it cannot run."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.lead.dispatch_messages import (
    build_not_ready_message,
    build_would_replace_the_strategy,
    frame_result_from_draft,
    undeclared_spec_changes,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange, diff_specs


def _spec_with_open_slots() -> OperationalSpec:
    return OperationalSpec(
        goal="candidate drug targets",
        criteria=[
            Criterion(
                id="kinases",
                text="kinase annotations",
                search_name="GenesByInterproDomain",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="kinases")
        ),
        open_slots=[
            OpenSlot(
                criterion_id="kinases",
                param_name="ms_assay",
                question="Which trophozoite mass-spec assay?",
                options=["Assay A", "Assay B"],
            ),
            OpenSlot(criterion_id="kinases", param_name="min_peptides"),
        ],
    )


def _draft(*names: str) -> OperationalSpec:
    return OperationalSpec(
        goal="find candidate drug targets",
        criteria=[
            Criterion(id=n, text=n, role="filter", search_name=f"By{n}") for n in names
        ],
    )


class TestNoSpecYet:
    def test_tells_the_model_to_frame_first(self) -> None:
        message = build_not_ready_message(None)

        assert "frame_problem" in message

    def test_is_a_retry_the_model_can_act_on(self) -> None:
        assert "frame_problem" in build_not_ready_message(None)


class TestOpenSlotsNeedTheUser:
    def test_does_not_send_the_model_back_to_frame(self) -> None:
        message = build_not_ready_message(_spec_with_open_slots())

        assert "frame_problem" not in message, (
            "re-running FRAME regenerates the same open slots; only the user "
            "can fill them"
        )

    def test_names_the_open_parameters(self) -> None:
        message = build_not_ready_message(_spec_with_open_slots())

        assert "ms_assay" in message
        assert "min_peptides" in message

    def test_tells_the_model_to_ask_the_user(self) -> None:
        message = build_not_ready_message(_spec_with_open_slots())

        assert "ask" in message.lower()

    def test_carries_the_question_when_frame_wrote_one(self) -> None:
        message = build_not_ready_message(_spec_with_open_slots())

        assert "Which trophozoite mass-spec assay?" in message


class TestUnboundCriteria:
    def test_a_spec_with_no_criteria_goes_back_to_frame(self) -> None:
        empty = OperationalSpec(goal="x")

        assert "frame_problem" in build_not_ready_message(empty)


def test_the_message_is_raisable_as_model_retry() -> None:
    with pytest.raises(ModelRetry, match="ms_assay"):
        raise ModelRetry(build_not_ready_message(_spec_with_open_slots()))


def test_the_build_refusal_names_the_tool_that_starts_over() -> None:
    assert "clear_strategy" in build_would_replace_the_strategy(3)


class TestABoundCriterionIsReported:
    def test_the_disposition_asks_for_another_pass(self) -> None:
        result = frame_result_from_draft(_draft("a", "b"))

        assert result.disposition == "needs_user"

    def test_the_summary_counts_what_was_bound(self) -> None:
        result = frame_result_from_draft(_draft("a", "b", "c"))

        assert "3" in result.summary

    def test_the_summary_names_the_budget_rather_than_a_failure(self) -> None:
        result = frame_result_from_draft(_draft("a"))

        assert "budget" in result.summary.lower()

    def test_a_criterion_is_named_so_the_work_is_identifiable(self) -> None:
        result = frame_result_from_draft(_draft("kinases"))

        assert "kinases" in result.summary


class TestNothingBoundIsStillNothing:
    def test_an_empty_draft_says_so(self) -> None:
        result = frame_result_from_draft(OperationalSpec(goal="g"))

        assert "no criteria" in result.summary.lower()

    def test_a_missing_draft_says_so(self) -> None:
        result = frame_result_from_draft(None)

        assert result.disposition == "needs_user"


_OPEN_PARAM = "min_peptide_count"


def _with_an_open_slot() -> OperationalSpec:
    """One criterion whose parameter the user has not answered yet."""
    return OperationalSpec(
        goal="candidate drug targets",
        criteria=[
            Criterion(
                id="mass_spec",
                text="detected by mass spectrometry",
                search_name="GenesByMassSpec",
                open_params=[
                    OpenSlot(criterion_id="mass_spec", param_name=_OPEN_PARAM)
                ],
            ),
        ],
    )


def _answered(value: str) -> OperationalSpec:
    after = _with_an_open_slot()
    after.criteria[0].resolved_params = {_OPEN_PARAM: StringValue(value=value)}
    after.criteria[0].open_params = []
    return after


class TestAnAnsweredOpenSlotIsNotARebinding:
    def test_filling_an_open_parameter_of_a_kept_criterion_is_no_problem(self) -> None:
        before = _with_an_open_slot()

        problem = undeclared_spec_changes(
            diff_specs(before, _answered("1")),
            [CriterionChange(criterion_id="mass_spec", disposition="kept")],
            before,
        )

        assert problem == ""

    def test_moving_a_value_the_baseline_resolved_is_still_refused(self) -> None:
        before = _answered("1")

        problem = undeclared_spec_changes(
            diff_specs(before, _answered("2")),
            [CriterionChange(criterion_id="mass_spec", disposition="kept")],
            before,
        )

        assert "mass_spec" in problem
        assert f"{_OPEN_PARAM}=2" in problem
