"""Two persisted states of one strategy diff to parameter-level changes."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, NumberValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepFilter,
    StrategyAst,
    StrategyStepNode,
)

from strategist.domain.strategy.ast_diff import diff_strategy_asts


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
        ("min_expression_percentile", "90.0", "75.0"),
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


def test_a_weight_set_on_the_site_is_reported_with_both_values() -> None:
    weighted = _leaf("step_expr", 90).model_copy(update={"wdk_weight": 3})

    diff = diff_strategy_asts(
        _ast(weighted), _ast(weighted.model_copy(update={"wdk_weight": 5}))
    )

    assert [
        (c.step_id, c.params, c.settings, c.before.wdk_weight, c.after.wdk_weight)
        for c in diff.changed
    ] == [("step_expr", [], ["wdk_weight"], 3, 5)]


def test_a_filter_or_an_operator_that_moved_is_a_change() -> None:
    def combined(operator: CombineOp, filtered: bool) -> StrategyAst:
        leaf = _leaf("step_a", 90)
        if filtered:
            leaf = leaf.model_copy(
                update={
                    "filters": [
                        StepFilter(
                            name="matched_transcript_filter_array",
                            value={"values": ["N"]},
                        )
                    ]
                }
            )
        return _ast(
            StrategyStepNode(
                id="step_u",
                search_name=COMBINE_SEARCH_NAME,
                operator=operator,
                primary_input=leaf,
                secondary_input=_leaf("step_b", 50),
            )
        )

    diff = diff_strategy_asts(
        combined(CombineOp.UNION, filtered=False),
        combined(CombineOp.INTERSECT, filtered=True),
    )

    assert [(c.step_id, c.settings) for c in diff.changed] == [
        ("step_a", ["filters"]),
        ("step_u", ["operator"]),
    ]
