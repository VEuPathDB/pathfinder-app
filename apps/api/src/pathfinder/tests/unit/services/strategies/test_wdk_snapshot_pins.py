"""The AST a WDK strategy converts into, and the ids a live tree reports.

The fixture is the shape WDK returns for a saved strategy: a combine over a
transform, plus a combine WDK marks as an expanded saved sub-strategy.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.wdk.wdk_models import (
    WDKSearchConfig,
    WDKStep,
    WDKStepTree,
    WDKStrategyDetails,
)

from pathfinder.services.strategies import reconcile
from pathfinder.services.strategies.reconcile import fetch_wdk_strategy_step_ids
from pathfinder.services.strategies.wdk_conversion import build_snapshot_from_wdk

_BOOLEAN = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


class _FakeAPI:
    """Answers one strategy read."""

    def __init__(self, details: WDKStrategyDetails) -> None:
        self._details = details

    async def get_strategy(self, strategy_id: int) -> WDKStrategyDetails:
        del strategy_id
        return self._details


def _step(
    step_id: int,
    search_name: str,
    parameters: dict[str, str] | None = None,
    **extra: object,
) -> WDKStep:
    return WDKStep.model_validate(
        {
            "id": step_id,
            "search_name": search_name,
            "search_config": WDKSearchConfig(parameters=parameters or {}),
            "custom_name": f"name-{step_id}",
            **extra,
        }
    )


def _tree() -> WDKStepTree:
    return WDKStepTree(
        step_id=40,
        primary_input=WDKStepTree(step_id=30, primary_input=WDKStepTree(step_id=10)),
        secondary_input=WDKStepTree(step_id=20),
    )


def _details() -> WDKStrategyDetails:
    return WDKStrategyDetails(
        strategy_id=7,
        name="kinases",
        root_step_id=40,
        record_class_name="transcript",
        step_tree=_tree(),
        steps={
            "10": _step(
                10, "GenesByText", {"text_expression": "kinase"}, estimated_size=5
            ),
            "20": _step(20, "GenesByTaxon", strategy_id=99, estimated_size=7),
            "30": _step(30, "GenesByOrthologs", estimated_size=3),
            "40": _step(
                40,
                _BOOLEAN,
                {"bq_operator": "INTERSECT"},
                expanded=True,
                expanded_name="saved-1",
                estimated_size=2,
            ),
        },
    )


class TestTheAstBuiltFromWdk:
    def test_the_root_is_a_combine_over_the_transform_and_the_leaf(self) -> None:
        ast, _ = build_snapshot_from_wdk(_details())

        assert ast.root.id == "40"
        assert ast.root.search_name == _BOOLEAN
        assert ast.root.operator is CombineOp.INTERSECT
        assert ast.root.primary_input is not None
        assert ast.root.primary_input.id == "30"
        assert ast.root.secondary_input is not None
        assert ast.root.secondary_input.id == "20"

    def test_the_transform_keeps_its_own_input(self) -> None:
        ast, _ = build_snapshot_from_wdk(_details())

        transform = ast.root.primary_input
        assert transform is not None
        assert transform.search_name == "GenesByOrthologs"
        assert transform.primary_input is not None
        assert transform.primary_input.id == "10"

    def test_an_expanded_combine_names_the_saved_strategy_on_its_secondary(
        self,
    ) -> None:
        ast, _ = build_snapshot_from_wdk(_details())

        assert ast.root.expanded_strategy_id == 99
        assert ast.root.expanded_name == "saved-1"

    def test_only_leaf_and_transform_wire_parameters_go_to_the_sidecar(self) -> None:
        _, wire = build_snapshot_from_wdk(_details())

        assert wire == {
            "10": {"text_expression": "kinase"},
            "20": {},
            "30": {},
        }

    def test_counts_and_wdk_ids_come_back_keyed_by_step_id(self) -> None:
        ast, _ = build_snapshot_from_wdk(_details())

        assert ast.wdk_step_ids == {"10": 10, "20": 20, "30": 30, "40": 40}
        assert ast.step_counts == {"10": 5, "20": 7, "30": 3, "40": 2}


class TestTheLiveStepIds:
    async def test_every_node_of_the_tree_is_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            reconcile, "get_strategy_api", lambda site_id: _FakeAPI(_details())
        )

        assert await fetch_wdk_strategy_step_ids("plasmodb", 7) == {10, 20, 30, 40}

    async def test_a_leaf_tree_reports_one_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        details = _details().model_copy(update={"step_tree": WDKStepTree(step_id=5)})
        monkeypatch.setattr(
            reconcile, "get_strategy_api", lambda site_id: _FakeAPI(details)
        )

        assert await fetch_wdk_strategy_step_ids("plasmodb", 7) == {5}
