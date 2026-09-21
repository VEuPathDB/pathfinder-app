"""What moved on the strategy since the spec it answers to was recorded.

The comparison is tree against tree: two forms of one graph, never a spec
value against a step value.
"""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.outside_changes import outside_changes

from ._builders import combine, leaf, transform


def _ast(root: StrategyStepNode) -> StrategyAst:
    return StrategyAst(record_type="transcript", root=root)


def _expression(percentile: int = 80, step_id: str = "expr") -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByRNASeqEvidence",
        parameters={"min_expression_percentile": NumberValue(value=percentile)},
    )


def _built(percentile: int = 80) -> StrategyAst:
    return _ast(combine("c0", leaf("text"), _expression(percentile)))


def test_the_same_tree_moved_nothing() -> None:
    changes = outside_changes(_built(), _built())

    assert (changes.changed, changes.added, changes.removed) == ([], [], [])
    assert changes.structure_moved is False


def test_a_value_set_on_a_step_is_one_changed_parameter() -> None:
    changes = outside_changes(_built(80), _built(48))

    assert [c.step_id for c in changes.changed] == ["expr"]
    assert [(p.name, p.before, p.after) for p in changes.changed[0].params] == [
        ("min_expression_percentile", "80", "48")
    ]
    assert not changes.structure_moved
    assert changes.moved


def test_a_step_added_beside_the_root_is_added_with_its_combine() -> None:
    grown = _ast(combine("c1", combine("c0", leaf("text"), _expression()), leaf("go")))

    changes = outside_changes(_built(), grown)

    assert {s.step_id for s in changes.added} == {"c1", "go"}
    assert changes.removed == []
    assert changes.structure_moved


def test_a_step_deleted_on_the_canvas_is_removed_with_its_combine() -> None:
    changes = outside_changes(_built(), _ast(leaf("text")))

    assert {s.step_id for s in changes.removed} == {"c0", "expr"}
    assert changes.structure_moved


def test_an_emptied_strategy_removes_every_step() -> None:
    changes = outside_changes(_built(), None)

    assert {s.step_id for s in changes.removed} == {"c0", "text", "expr"}
    assert changes.removed_ids == frozenset({"c0", "text", "expr"})
    assert changes.structure_moved


def test_a_thread_that_answered_to_nothing_reports_nothing() -> None:
    """Nothing says what the strategy was, so nothing is attributed to anyone."""
    changes = outside_changes(None, _built())

    assert (changes.changed, changes.added, changes.removed) == ([], [], [])
    assert changes.structure_moved is False


def test_a_flipped_operator_moves_the_structure_and_no_parameter() -> None:
    flipped = _ast(combine("c0", leaf("text"), _expression(), operator=CombineOp.UNION))

    changes = outside_changes(_built(), flipped)

    assert changes.changed == []
    assert changes.structure_moved


def test_swapped_sides_move_the_structure() -> None:
    swapped = _ast(combine("c0", _expression(), leaf("text")))

    changes = outside_changes(_built(), swapped)

    assert changes.changed == []
    assert changes.structure_moved


def test_a_transform_dropped_over_the_root_moves_the_structure() -> None:
    lifted = _ast(transform("orth", combine("c0", leaf("text"), _expression())))

    changes = outside_changes(_built(), lifted)

    assert {s.step_id for s in changes.added} == {"orth"}
    assert changes.structure_moved


def test_a_step_re_added_under_a_new_id_is_one_removal_and_one_addition() -> None:
    """The same search and values under another id is another step."""
    re_added = _ast(combine("c0", leaf("text"), _expression(80, step_id="expr2")))

    changes = outside_changes(_built(80), re_added)

    assert [s.step_id for s in changes.removed] == ["expr"]
    assert [s.step_id for s in changes.added] == ["expr2"]
