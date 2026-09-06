"""What the projection actually hands to ``PUT .../step-tree``.

The projection is three functions. A test that stops after the second never
reaches the wire shape.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters.values import StringValue
from veupathdb.domain.strategy.graph_model import (
    StepKind,
    StrategyStep,
    pushable_root_id,
    rebuild_tree,
)
from veupathdb.domain.strategy.ops import CombineOp

from pathfinder.platform.errors import StrategyCompilationError
from pathfinder.services.strategies.sync import build_step_tree_from_graph


def _leaf(step_id: str) -> StrategyStep:
    return StrategyStep(
        id=step_id,
        kind=StepKind.SEARCH,
        search_name="GenesByMolecularWeight",
        parameters={"min_molecular_weight": StringValue(value="10000")},
    )


def _graph_with_a_detached_subtree() -> dict[str, StrategyStep]:
    """A half-wired combine over one good leaf, plus a leaf nobody reaches."""
    return {
        "kinase": _leaf("kinase"),
        "orphan": _leaf("orphan"),
        "combine": StrategyStep(
            id="combine",
            kind=StepKind.COMBINE,
            operator=CombineOp.INTERSECT,
            primary_input_id="kinase",
            secondary_input_id=None,
        ),
    }


_WDK_IDS = {"kinase": 101, "orphan": 102, "combine": 103}


class TestTheProjectionCollapsesToOnePushableRoot:
    def test_wdk_strat_002_a_half_wired_combine_is_not_the_root(self) -> None:
        steps = _graph_with_a_detached_subtree()

        assert pushable_root_id("combine", steps) == "kinase"

    def test_wdk_strat_002_the_pushed_tree_has_exactly_one_root(self) -> None:
        steps = _graph_with_a_detached_subtree()
        pushable = pushable_root_id("combine", steps)
        assert pushable is not None

        tree = build_step_tree_from_graph(rebuild_tree(pushable, steps), _WDK_IDS)

        assert tree.step_id == 101
        assert tree.primary_input is None
        assert tree.secondary_input is None

    def test_wdk_strat_003_no_step_outside_the_pushed_subtree_appears(self) -> None:
        steps = _graph_with_a_detached_subtree()
        pushable = pushable_root_id("combine", steps)
        assert pushable is not None

        tree = build_step_tree_from_graph(rebuild_tree(pushable, steps), _WDK_IDS)
        serialized = tree.model_dump(by_alias=True, exclude_none=True)

        assert serialized == {"stepId": 101}

    def test_wdk_strat_003_every_node_of_a_wired_tree_is_reachable(self) -> None:
        steps = _graph_with_a_detached_subtree()
        steps["combine"] = steps["combine"].model_copy(
            update={"secondary_input_id": "orphan"}
        )

        pushable = pushable_root_id("combine", steps)
        assert pushable == "combine"
        tree = build_step_tree_from_graph(rebuild_tree("combine", steps), _WDK_IDS)

        assert tree.model_dump(by_alias=True, exclude_none=True) == {
            "stepId": 103,
            "primaryInput": {"stepId": 101},
            "secondaryInput": {"stepId": 102},
        }


class TestWdkMap003TheWireShapeIsIdsOnly:
    def test_wdk_map_003_the_serialized_tree_carries_only_the_three_keys(self) -> None:
        steps = _graph_with_a_detached_subtree()
        steps["combine"] = steps["combine"].model_copy(
            update={"secondary_input_id": "orphan"}
        )

        tree = build_step_tree_from_graph(rebuild_tree("combine", steps), _WDK_IDS)
        serialized = tree.model_dump(by_alias=True, exclude_none=True)

        assert set(serialized) == {"stepId", "primaryInput", "secondaryInput"}
        assert set(serialized["primaryInput"]) == {"stepId"}

    def test_wdk_map_003_no_parameter_or_name_rides_along(self) -> None:
        steps = _graph_with_a_detached_subtree()

        tree = build_step_tree_from_graph(rebuild_tree("kinase", steps), _WDK_IDS)
        serialized = tree.model_dump(by_alias=True, exclude_none=True, mode="json")

        assert "searchName" not in serialized
        assert "parameters" not in serialized

    def test_wdk_map_003_a_step_without_a_wdk_id_is_refused(self) -> None:
        # Every step in the pushed tree needs an id, or the push is a 422.
        steps = _graph_with_a_detached_subtree()
        steps["combine"] = steps["combine"].model_copy(
            update={"secondary_input_id": "orphan"}
        )

        with pytest.raises(StrategyCompilationError):
            build_step_tree_from_graph(
                rebuild_tree("combine", steps), {"combine": 103, "kinase": 101}
            )
