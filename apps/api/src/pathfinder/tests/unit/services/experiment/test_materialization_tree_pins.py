"""The order and shape of the WDK calls that materialize an experiment tree.

An input is created before the step that consumes it, a combine goes through
the combined-step call, and an imported tree reaches WDK unchanged.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters.values import StringValue
from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.wdk.wdk_models import (
    CombinedStepSpec,
    NewStepSpec,
    WDKIdentifier,
    WDKStepTree,
)

from pathfinder.services.experiment import materialization
from pathfinder.services.experiment.materialization import _persist_experiment_strategy
from pathfinder.services.experiment.types.experiment import ExperimentConfig


class _RecordingAPI:
    """Hands out increasing ids and records what was asked for, in order."""

    def __init__(self, duplicated: WDKStepTree | None = None) -> None:
        self.calls: list[str] = []
        self.step_tree: WDKStepTree | None = None
        self._duplicated = duplicated
        self._next = 100

    def _mint(self) -> WDKIdentifier:
        self._next += 1
        return WDKIdentifier(id=self._next)

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del record_type, user_id
        self.calls.append(f"create_step:{spec.search_name}")
        return self._mint()

    async def create_transform_step(
        self,
        spec: NewStepSpec,
        input_step_id: int,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del record_type, user_id
        self.calls.append(f"create_transform_step:{spec.search_name}<-{input_step_id}")
        return self._mint()

    async def create_combined_step(
        self, spec: CombinedStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del record_type, user_id
        operator = spec.boolean_operator.value
        self.calls.append(
            f"create_combined_step:{spec.primary_step_id}{operator}"
            f"{spec.secondary_step_id}"
        )
        return self._mint()

    async def get_duplicated_step_tree(self, strategy_id: int) -> WDKStepTree:
        self.calls.append(f"get_duplicated_step_tree:{strategy_id}")
        assert self._duplicated is not None
        return self._duplicated

    async def create_strategy(
        self,
        step_tree: WDKStepTree,
        name: str,
        description: str | None = None,
        *,
        is_public: bool = False,
        is_saved: bool = False,
        is_internal: bool = False,
    ) -> WDKIdentifier:
        del name, description, is_public, is_saved, is_internal
        self.step_tree = step_tree
        self.calls.append("create_strategy")
        return WDKIdentifier(id=999)


def _tree() -> StrategyStepNode:
    """``orthologs(text) INTERSECT taxon``."""
    return StrategyStepNode(
        id="root",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="t",
            search_name="GenesByOrthologs",
            primary_input=StrategyStepNode(
                id="a",
                search_name="GenesByText",
                parameters={"text_expression": StringValue(value="kinase")},
            ),
        ),
        secondary_input=StrategyStepNode(id="b", search_name="GenesByTaxon"),
    )


def _config(
    root: StrategyStepNode | None, mode: str = "multi-step"
) -> ExperimentConfig:
    return ExperimentConfig(
        site_id="plasmodb",
        record_type="transcript",
        search_name="GenesByText",
        parameters={},
        positive_controls=[],
        negative_controls=[],
        controls_search_name="GeneByLocusTag",
        controls_param_name="ds_gene_ids",
        name="tree",
        mode=mode,
        step_tree=root,
    )


def _install(monkeypatch: pytest.MonkeyPatch, api: _RecordingAPI) -> None:
    monkeypatch.setattr(materialization, "get_strategy_api", lambda site_id: api)


class TestMaterializingATree:
    @pytest.mark.asyncio
    async def test_every_input_is_created_before_the_step_that_consumes_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _RecordingAPI()
        _install(monkeypatch, api)

        await _persist_experiment_strategy(_config(_tree()), "exp_abc")

        assert api.calls == [
            "create_step:GenesByText",
            "create_transform_step:GenesByOrthologs<-101",
            "create_step:GenesByTaxon",
            "create_combined_step:102INTERSECT103",
            "create_strategy",
        ]

    @pytest.mark.asyncio
    async def test_the_tree_sent_to_wdk_mirrors_the_plan(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _RecordingAPI()
        _install(monkeypatch, api)

        ids = await _persist_experiment_strategy(_config(_tree()), "exp_abc")

        assert api.step_tree is not None
        assert api.step_tree.model_dump(by_alias=True, exclude_none=True) == {
            "stepId": 104,
            "primaryInput": {"stepId": 102, "primaryInput": {"stepId": 101}},
            "secondaryInput": {"stepId": 103},
        }
        assert ids == {"strategy_id": 999, "step_id": 104}

    @pytest.mark.asyncio
    async def test_a_leaf_tree_is_one_create_step_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _RecordingAPI()
        _install(monkeypatch, api)

        await _persist_experiment_strategy(
            _config(StrategyStepNode(id="a", search_name="GenesByTaxon")), "exp_abc"
        )

        assert api.calls == ["create_step:GenesByTaxon", "create_strategy"]
        assert api.step_tree is not None
        assert api.step_tree.model_dump(by_alias=True, exclude_none=True) == {
            "stepId": 101
        }


class TestImportingATree:
    @pytest.mark.asyncio
    async def test_the_duplicated_tree_reaches_wdk_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        duplicated = WDKStepTree(
            step_id=7,
            primary_input=WDKStepTree(step_id=8, primary_input=WDKStepTree(step_id=9)),
            secondary_input=WDKStepTree(step_id=10),
        )
        api = _RecordingAPI(duplicated=duplicated)
        _install(monkeypatch, api)
        config = _config(None, mode="import").model_copy(
            update={"source_strategy_id": "42"}
        )

        ids = await _persist_experiment_strategy(config, "exp_abc")

        assert api.calls == ["get_duplicated_step_tree:42", "create_strategy"]
        assert api.step_tree == duplicated
        assert ids == {"strategy_id": 999, "step_id": 7}
