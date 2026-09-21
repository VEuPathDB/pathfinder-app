from __future__ import annotations

from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.domain.strategy.operations import DeleteResolution
from pathfinder.domain.strategy.operations.resolutions import compute_delete_choices
from pathfinder.domain.strategy.session import StrategyGraph

from ._builders import graph_with, leaf


def _graph_from_root(root: StrategyStepNode) -> StrategyGraph:
    return graph_with([root])


class TestComputeDeleteChoices:
    def test_sole_leaf_only_delete_strategy(self) -> None:
        g = _graph_from_root(leaf("a"))
        choices = compute_delete_choices(g, "a")
        assert [c.resolution for c in choices] == [DeleteResolution.DELETE_STRATEGY]
        assert choices[0].will_delete == ["a"]
        assert choices[0].is_default

    def test_leaf_of_root_combine(self) -> None:
        a = leaf("a")
        b = leaf("b")
        c = StrategyStepNode(
            id="c",
            search_name="__combine__",
            primary_input=a,
            secondary_input=b,
            operator=CombineOp.INTERSECT,
        )
        g = _graph_from_root(c)
        choices = compute_delete_choices(g, "a")
        assert {c.resolution for c in choices} == {
            DeleteResolution.COLLAPSE_COMBINE,
            DeleteResolution.DELETE_SUBTREE,
        }
        default = next(c for c in choices if c.is_default)
        assert default.resolution == DeleteResolution.COLLAPSE_COMBINE
        collapse = next(
            c for c in choices if c.resolution == DeleteResolution.COLLAPSE_COMBINE
        )
        assert sorted(collapse.will_delete) == ["a", "c"]

    def test_root_combine_promote_or_delete_strategy(self) -> None:
        a = leaf("a")
        b = leaf("b")
        c = StrategyStepNode(
            id="c",
            search_name="__combine__",
            primary_input=a,
            secondary_input=b,
            operator=CombineOp.INTERSECT,
        )
        g = _graph_from_root(c)
        choices = compute_delete_choices(g, "c")
        assert {c.resolution for c in choices} == {
            DeleteResolution.PROMOTE_PRIMARY,
            DeleteResolution.DELETE_STRATEGY,
        }
        promote = next(
            c for c in choices if c.resolution == DeleteResolution.PROMOTE_PRIMARY
        )
        assert sorted(promote.will_delete) == ["b", "c"]

    def test_transform_keeps_the_step_it_consumed(self) -> None:
        a = leaf("a")
        t = StrategyStepNode(
            id="t",
            search_name="orthologs",
            primary_input=a,
        )
        g = _graph_from_root(t)
        choices = compute_delete_choices(g, "t")
        assert [c.resolution for c in choices] == [DeleteResolution.PROMOTE_PRIMARY]
        assert choices[0].will_delete == ["t"]

    def test_transform_with_no_input_is_placed_by_the_leaf_rules(self) -> None:
        """A transform an earlier delete left with no input reads nothing."""
        t = StrategyStepNode(id="t", search_name="orthologs", primary_input=leaf("a"))
        g = _graph_from_root(t)
        g.steps["t"].primary_input_id = None
        choices = compute_delete_choices(g, "t")
        assert [c.resolution for c in choices] == [DeleteResolution.DELETE_STRATEGY]

    def test_step_whose_parent_is_transform_cascades(self) -> None:
        a = leaf("a")
        t = StrategyStepNode(
            id="t",
            search_name="orthologs",
            primary_input=a,
        )
        g = _graph_from_root(t)
        choices = compute_delete_choices(g, "a")
        assert [c.resolution for c in choices] == [DeleteResolution.DELETE_SUBTREE]
        assert sorted(choices[0].will_delete) == ["a", "t"]

    def test_unknown_step_returns_empty(self) -> None:
        g = _graph_from_root(leaf("a"))
        assert compute_delete_choices(g, "missing") == []
