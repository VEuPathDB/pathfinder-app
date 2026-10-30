"""The counts of the strategy's most recent change are a fact of every later
turn, shown as a facts line and named by two references."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)

from pathfinder.domain.last_change import LastChange, change_between, change_since
from pathfinder.domain.turn_facts import StepFact, TurnFacts

_SIGNAL_PEPTIDE = "Predicted Signal Peptide"
_DELETED = LastChange(before=17, after=68, what=f"deleted {_SIGNAL_PEPTIDE}")
_ASKED = "[last_change:before] before the delete and [last_change:after] after."


def _facts(last_change: LastChange | None) -> TurnFacts:
    return TurnFacts(
        steps=[StepFact(step_id="step_text", display_name="Text search", count=68)],
        root_count=68,
        last_change=last_change,
    )


def _text_search(value: str = "secreted") -> StrategyStepNode:
    return StrategyStepNode(
        id="step_text",
        search_name="GenesByText",
        parameters={"text_expression": StringValue(value=value)},
        display_name="Text search",
    )


def _joined() -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_join",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=_text_search(),
            secondary_input=StrategyStepNode(
                id="step_sp",
                search_name="GenesWithSignalPeptide",
                display_name=_SIGNAL_PEPTIDE,
            ),
        ),
        step_counts={"step_text": 68, "step_sp": 431, "step_join": 17},
    )


def _text_alone(count: int = 68, value: str = "secreted") -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=_text_search(value),
        step_counts={"step_text": count},
    )


def test_the_facts_show_the_last_change_with_both_counts() -> None:
    assert (
        "Last change: deleted Predicted Signal Peptide; 17 genes before, 68 genes after"
        in _facts(_DELETED).lines()
    )


def test_a_count_not_recorded_is_said_so() -> None:
    built = LastChange(before=None, after=68, what="built the strategy")

    assert (
        "Last change: built the strategy; count before not recorded, 68 genes after"
        in _facts(built).lines()
    )


def test_a_delete_is_named_by_the_step_it_removed() -> None:
    assert change_between(_joined(), _text_alone()) == _DELETED


def test_a_first_strategy_is_a_build_with_no_count_before() -> None:
    assert change_between(None, _text_alone()) == LastChange(
        before=None, after=68, what="built the strategy"
    )


def test_an_added_step_is_named() -> None:
    assert change_between(_text_alone(), _joined()) == LastChange(
        before=68, after=17, what=f"added {_SIGNAL_PEPTIDE}"
    )


def test_an_edited_value_names_its_step() -> None:
    edited = _text_alone(count=12, value="secreted protease")

    assert change_between(_text_alone(), edited) == LastChange(
        before=68, after=12, what="edited Text search"
    )


def test_a_turn_that_changed_nothing_keeps_the_change_with_the_live_count() -> None:
    refreshed = _text_alone(count=70)

    assert change_since(_text_alone(), _DELETED, refreshed) == LastChange(
        before=17, after=70, what=f"deleted {_SIGNAL_PEPTIDE}"
    )


def test_a_turn_that_changed_the_tree_is_the_last_change() -> None:
    assert change_since(_joined(), None, _text_alone()) == _DELETED


def test_no_strategy_has_no_last_change() -> None:
    assert [change_since(_joined(), _DELETED, None)] == [None]
