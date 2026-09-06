"""Two persisted states of one strategy diff to parameter-level changes."""

from __future__ import annotations

from veupathdb.domain.parameters.values import MultiPickValue, NumberValue
from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.domain.strategy.ast_diff import diff_strategy_asts


def _leaf(step_id: str, percentile: int) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByRNASeqEvidence",
        parameters={"min_expression_percentile": NumberValue(value=percentile)},
        display_name="top expression",
    )


def _ast(*leaves: StrategyStepNode) -> StrategyAst:
    if len(leaves) == 1:
        return StrategyAst(record_type="transcript", root=leaves[0])
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_join",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=leaves[0],
            secondary_input=leaves[1],
        ),
    )


def test_a_parameter_edit_is_reported_with_both_values() -> None:
    diff = diff_strategy_asts(
        _ast(_leaf("step_expr", 90)), _ast(_leaf("step_expr", 75))
    )

    assert diff.moved
    assert [c.step_id for c in diff.changed] == ["step_expr"]
    change = diff.changed[0]
    assert change.label == "top expression"
    assert [(p.name, p.before, p.after) for p in change.params] == [
        ("min_expression_percentile", "90", "75"),
    ]


def test_an_untouched_strategy_reports_nothing() -> None:
    diff = diff_strategy_asts(
        _ast(_leaf("step_expr", 90)), _ast(_leaf("step_expr", 90))
    )

    assert not diff.moved
    assert diff.changed == []
    assert diff.added == []
    assert diff.removed == []


def test_a_step_added_and_a_step_removed_are_named() -> None:
    before = _ast(_leaf("step_expr", 90))
    after = _ast(
        StrategyStepNode(
            id="step_taxon",
            search_name="GenesByTaxon",
            parameters={"organism": MultiPickValue(values=["Plasmodium"])},
        ),
    )

    diff = diff_strategy_asts(before, after)

    assert [s.step_id for s in diff.added] == ["step_taxon"]
    assert [s.step_id for s in diff.removed] == ["step_expr"]
    assert [s.label for s in diff.added] == ["GenesByTaxon"]


def test_a_step_that_changed_its_search_reports_both_names() -> None:
    before = _ast(_leaf("step_expr", 90))
    after = _ast(
        StrategyStepNode(
            id="step_expr",
            search_name="GenesByMicroarrayEvidence",
            parameters={"min_expression_percentile": NumberValue(value=90)},
            display_name="top expression",
        ),
    )

    diff = diff_strategy_asts(before, after)

    change = diff.changed[0]
    assert change.search_before == "GenesByRNASeqEvidence"
    assert change.search_after == "GenesByMicroarrayEvidence"
    assert change.params == []


def test_a_thread_with_one_revision_reports_nothing() -> None:
    diff = diff_strategy_asts(None, _ast(_leaf("step_expr", 90)))

    assert (diff.moved, diff.changed, diff.added, diff.removed) == (False, [], [], [])


def test_a_combine_step_added_around_two_leaves_is_reported_once() -> None:
    before = _ast(_leaf("step_expr", 90))
    after = _ast(
        _leaf("step_expr", 90),
        StrategyStepNode(id="step_taxon", search_name="GenesByTaxon"),
    )

    diff = diff_strategy_asts(before, after)

    assert sorted(s.step_id for s in diff.added) == ["step_join", "step_taxon"]
    assert diff.changed == []
    assert diff.removed == []
