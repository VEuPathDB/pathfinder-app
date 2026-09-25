"""The Lead opens a turn knowing what moved since its last answer."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    ParamValue,
    StringValue,
)
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.ai.lead.turn_briefing import MAX_BRIEFING_LINES, compose_turn_briefing
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.services.conversations.thread_activity import (
    AnalysisDrift,
    FinishedTask,
    ThreadActivity,
)


def _expression_ast(percentile: int, *, rnaseq: bool = True) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_expr",
            search_name=(
                "GenesByRNASeqEvidence" if rnaseq else "GenesByMicroarrayEvidence"
            ),
            parameters={
                "min_expression_percentile": NumberValue(value=percentile),
                "p_value": NumberValue(value=0.05),
            },
            display_name="top expression",
        ),
    )


def test_an_editor_edit_pins_the_parameter_line() -> None:
    briefing = compose_turn_briefing(
        ThreadActivity(),
        requirements=[],
        answered=_expression_ast(90),
        live=_expression_ast(75),
    )

    assert briefing.moved
    assert "min_expression_percentile 90 -> 75" in briefing.render()
    assert briefing.render().startswith("## Since your last turn")


def test_a_completed_task_pins_the_task_line() -> None:
    briefing = compose_turn_briefing(
        ThreadActivity(
            finished_tasks=[
                FinishedTask(tool_name="run_control_tests_on_step", failed=False),
                FinishedTask(tool_name="run_eda_compute", failed=True),
            ],
        ),
        requirements=[],
    )

    rendered = briefing.render()
    assert "run_control_tests_on_step finished" in rendered
    assert "run_eda_compute failed" in rendered


def test_an_analysis_that_moved_past_its_card_is_named() -> None:
    """A change through the tools and a change on the site read the same."""
    briefing = compose_turn_briefing(
        ThreadActivity(analysis=AnalysisDrift(dataset_id="DS_1234")),
        requirements=[],
    )

    assert (
        "- the open analysis (DS_1234) changed after the card in this conversation"
        in briefing.render()
    )


def test_a_constraint_that_lost_its_grounding_is_named() -> None:
    requirement = Constraint(
        kind=ConstraintKind.DATA_TYPE,
        requested_value="RNA-Seq only",
        label="RNA-Seq only",
        source=ConstraintSource.USER_EXPLICIT,
    )

    briefing = compose_turn_briefing(
        ThreadActivity(),
        requirements=[requirement],
        answered=_expression_ast(90),
        live=_expression_ast(90, rnaseq=False),
    )

    rendered = briefing.render()
    assert [c.label for c in briefing.constraints] == ["RNA-Seq only"]
    assert "grounded -> substituted" in rendered


def test_a_quiet_turn_renders_the_empty_string() -> None:
    briefing = compose_turn_briefing(ThreadActivity(), requirements=[])

    assert not briefing.moved
    assert briefing.render() == ""


def test_a_strategy_that_did_not_move_renders_the_empty_string() -> None:
    briefing = compose_turn_briefing(
        ThreadActivity(),
        requirements=[],
        answered=_expression_ast(90),
        live=_expression_ast(90),
    )

    assert briefing.render() == ""


def _many_steps(count: int, percentile: int) -> StrategyAst:
    leaves = [
        StrategyStepNode(
            id=f"step_{index}",
            search_name="GenesByTaxon",
            parameters={"organism": MultiPickValue(values=[f"org {percentile}"])},
        )
        for index in range(count)
    ]
    return StrategyAst(
        record_type="transcript",
        root=leaves[0],
        detached_roots=leaves[1:],
    )


def test_more_changes_than_fit_are_elided_with_a_count() -> None:
    briefing = compose_turn_briefing(
        ThreadActivity(),
        requirements=[],
        answered=_many_steps(12, 1),
        live=_many_steps(12, 2),
    )

    lines = briefing.render().splitlines()
    assert len(briefing.strategy.changed) == 12
    assert "- and 4 more changes" in lines
    assert sum(1 for line in lines if line.startswith("- ")) == MAX_BRIEFING_LINES + 1


def _wordy_ast(text: str, extras: int) -> StrategyAst:
    parameters: dict[str, ParamValue] = {
        "text_expression": StringValue(value=text),
    }
    for index in range(extras):
        parameters[f"extra_{index}"] = StringValue(value=text)
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_text",
            search_name="GenesByText",
            parameters=parameters,
        ),
    )


def test_a_long_value_is_clipped_and_extra_params_are_counted() -> None:
    briefing = compose_turn_briefing(
        ThreadActivity(),
        requirements=[],
        answered=_wordy_ast("kinase " * 20, 5),
        live=_wordy_ast("phosphatase " * 20, 5),
    )

    line = briefing.render().splitlines()[1]
    assert "..." in line
    assert "+4 more params" in line
    assert len(line) < 200


def _many_wordy_steps(count: int, word: str) -> StrategyAst:
    leaves = [
        StrategyStepNode(
            id=f"step_{index}",
            search_name="GenesByText",
            display_name=f"{word} step {index} " * 6,
            parameters={
                f"param_{slot}": StringValue(value=f"{word} " * 30) for slot in range(6)
            },
        )
        for index in range(count)
    ]
    return StrategyAst(
        record_type="transcript",
        root=leaves[0],
        detached_roots=leaves[1:],
    )


def test_the_worst_case_briefing_stays_bounded() -> None:
    briefing = compose_turn_briefing(
        ThreadActivity(),
        requirements=[],
        answered=_many_wordy_steps(12, "kinase"),
        live=_many_wordy_steps(12, "phosphatase"),
    )

    assert len(briefing.render()) < 1200
