from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree, walk
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import step_wdk_push
from pathfinder.services.strategies.step_push_planner import plan_step_pushes
from pathfinder.services.strategies.step_wdk_push import (
    PushOutcome,
    push_steps_with_plan,
)
from pathfinder.services.strategies.sync_state import WDKSyncState


@dataclass
class _CallRecord:
    name: str
    kwargs: dict[str, Any]


@dataclass
class CountingStrategyAPI:
    next_id: int = 1000
    calls: list[_CallRecord] = field(default_factory=list)
    fail_on_search_names: set[str] = field(default_factory=set)

    def _alloc(self) -> int:
        self.next_id += 1
        return self.next_id

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(
            _CallRecord(
                "create_step",
                {
                    "search_name": spec.search_name,
                    "parameters": dict(spec.search_config.parameters),
                    "record_type": record_type,
                },
            )
        )
        if spec.search_name in self.fail_on_search_names:
            msg = f"synthetic failure for {spec.search_name}"
            raise WDKError(msg)
        return WDKIdentifier(id=self._alloc())

    async def create_combined_step(
        self,
        spec: CombinedStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(
            _CallRecord(
                "create_combined_step",
                {
                    "primary_step_id": spec.primary_step_id,
                    "secondary_step_id": spec.secondary_step_id,
                    "boolean_operator": spec.boolean_operator.value,
                    "record_type": record_type,
                },
            )
        )
        return WDKIdentifier(id=self._alloc())

    async def create_transform_step(
        self,
        spec: NewStepSpec,
        input_step_id: int,
        record_type: str = "transcript",
        *,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(
            _CallRecord(
                "create_transform_step",
                {
                    "search_name": spec.search_name,
                    "input_step_id": input_step_id,
                    "record_type": record_type,
                },
            )
        )
        return WDKIdentifier(id=self._alloc())

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
    ) -> None:
        del user_id, record_type, search_config
        self.calls.append(
            _CallRecord(
                "update_step_search_config",
                {"step_id": step_id, "search_name": search_name},
            )
        )

    async def update_step_properties(
        self,
        step_id: int,
        spec: PatchStepSpec,
        *,
        user_id: str | None = None,
    ) -> None:
        del user_id
        self.calls.append(
            _CallRecord(
                "update_step_properties",
                {"step_id": step_id, "custom_name": spec.custom_name},
            )
        )

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByTaxon",
            search_config=WDKSearchConfig(parameters={}),
        )


async def _noop_validate_plan_params(*_args: object, **_kwargs: object) -> set[str]:
    return set()


@pytest.fixture
def counting_api(monkeypatch: pytest.MonkeyPatch) -> CountingStrategyAPI:
    api = CountingStrategyAPI()
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(
        step_wdk_push, "_validate_plan_params", _noop_validate_plan_params
    )
    return api


def _leaf(step_id: str, search: str = "GenesByTaxon") -> StrategyStepNode:
    return StrategyStepNode(
        search_name=search,
        parameters={"organism": MultiPickValue(values=["Pf3D7"])},
        id=step_id,
    )


def _populate_graph(graph: StrategyGraph, ast: StrategyAst) -> None:
    for step in walk(ast.root):
        graph.steps.update(flatten_tree(step))
    graph.record_type = ast.record_type
    graph.recompute_roots()


def test_push_outcome_partial_property_true_only_when_failed_nonempty() -> None:
    assert PushOutcome(succeeded=["a"], failed=[]).partial is False
    assert PushOutcome(succeeded=[], failed=[]).partial is False
    assert PushOutcome(succeeded=["a"], failed=["b"]).partial is True
    assert PushOutcome(succeeded=[], failed=["b"]).partial is True


async def test_push_outcome_all_succeeded(counting_api: CountingStrategyAPI) -> None:
    a = _leaf("A", "SearchA")
    ast = StrategyAst(record_type="transcript", root=a)

    graph = StrategyGraph("g1", "test", "plasmodb")
    sync_state = WDKSyncState()
    _populate_graph(graph, ast)

    plan = plan_step_pushes(old_ast=None, new_ast=ast, existing_wdk_ids={})
    outcome = await push_steps_with_plan(graph, sync_state, "plasmodb", plan)

    assert outcome.succeeded == ["A"]
    assert outcome.failed == []
    assert outcome.partial is False
    assert sync_state.wdk_step_ids == {"A": 1001}


async def test_push_outcome_partial_failure_continues_after_failed_step(
    counting_api: CountingStrategyAPI,
) -> None:
    counting_api.fail_on_search_names = {"SearchB"}

    a = _leaf("A", "SearchA")
    b = _leaf("B", "SearchB")
    c = _leaf("C", "SearchC")
    graph_a = StrategyGraph("g1", "test", "plasmodb")
    graph_a.steps = flatten_tree(a)
    graph_a.record_type = "transcript"
    graph_a.recompute_roots()

    sync_state = WDKSyncState()
    plan_a = plan_step_pushes(
        old_ast=None,
        new_ast=StrategyAst(record_type="transcript", root=a),
        existing_wdk_ids={},
    )
    await push_steps_with_plan(graph_a, sync_state, "plasmodb", plan_a)
    a_wdk_id = sync_state.wdk_step_ids["A"]

    graph_b = StrategyGraph("g1", "test", "plasmodb")
    graph_b.steps = flatten_tree(b)
    graph_b.record_type = "transcript"
    graph_b.recompute_roots()
    plan_b = plan_step_pushes(
        old_ast=None,
        new_ast=StrategyAst(record_type="transcript", root=b),
        existing_wdk_ids={},
    )
    outcome_b = await push_steps_with_plan(graph_b, sync_state, "plasmodb", plan_b)

    graph_c = StrategyGraph("g1", "test", "plasmodb")
    graph_c.steps = flatten_tree(c)
    graph_c.record_type = "transcript"
    graph_c.recompute_roots()
    plan_c = plan_step_pushes(
        old_ast=None,
        new_ast=StrategyAst(record_type="transcript", root=c),
        existing_wdk_ids={},
    )
    outcome_c = await push_steps_with_plan(graph_c, sync_state, "plasmodb", plan_c)

    assert outcome_b.succeeded == []
    assert outcome_b.failed == ["B"]
    assert outcome_b.partial is True

    assert outcome_c.succeeded == ["C"]
    assert outcome_c.failed == []
    assert sync_state.wdk_step_ids == {"A": a_wdk_id, "C": 1002}
    assert (
        sync_state.wdk_push_errors["B"]
        == "VEuPathDB service error: synthetic failure for SearchB"
    )


async def test_push_outcome_all_failed(counting_api: CountingStrategyAPI) -> None:
    counting_api.fail_on_search_names = {"SearchA", "SearchB", "SearchC"}

    a = _leaf("A", "SearchA")
    b = _leaf("B", "SearchB")
    c = _leaf("C", "SearchC")

    sync_state = WDKSyncState()

    for step_id, node in [("A", a), ("B", b), ("C", c)]:
        graph = StrategyGraph("g1", "test", "plasmodb")
        graph.steps = flatten_tree(node)
        graph.record_type = "transcript"
        graph.recompute_roots()
        plan = plan_step_pushes(
            old_ast=None,
            new_ast=StrategyAst(record_type="transcript", root=node),
            existing_wdk_ids={},
        )
        outcome = await push_steps_with_plan(graph, sync_state, "plasmodb", plan)
        assert outcome.succeeded == []
        assert outcome.failed == [step_id]
        assert outcome.partial is True

    assert sync_state.wdk_step_ids == {}
    assert set(sync_state.wdk_push_errors.keys()) == {"A", "B", "C"}
