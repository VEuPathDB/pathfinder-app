from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.strategy import (
    StepAnalysis,
    StepFilter,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)

from strategist.ai.tools.standalone.graph_helpers import serialize_step
from strategist.domain.strategy.session import StrategyGraph
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    FIELDS,
    Env,
    _patch_ops,
    _row,
    commit_ops,
    new_thread,
    node_of,
    plan_root,
    replace_with,
)

_FIXTURES = (
    Path(__file__).resolve().parents[7] / "web/src/features/strategy/graph/__fixtures__"
)
_UNDO_PLANS = TypeAdapter(dict[str, StrategyAst])
_FILTER = "matched_transcript_filter_array"


def _filtered(*values: str) -> list[StepFilter]:
    return [StepFilter(name=_FILTER, value={"values": list(values)})] if values else []


def _states() -> dict[str, StrategyStepNode]:
    states: dict[str, StrategyStepNode] = {}
    for name, values in (
        ("planned", ("N",)),
        ("unfiltered", ()),
        ("refiltered", ("Y", "N")),
    ):
        root = plan_root()
        node_of(root, "step_a").filters = _filtered(*values)
        node_of(root, "step_b").analyses = [
            StepAnalysis(analysis_type="go-enrichment", parameters={"goSubset": "No"})
        ]
        states[name] = root
    return states


def _views(root: StrategyStepNode) -> list[dict[str, object]]:
    graph = StrategyGraph("g1", "Kinases near membrane genes", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    return [
        serialize_step(graph, step).model_dump(
            by_alias=True, mode="json", exclude_none=True
        )
        for step in graph.steps.values()
    ]


def _replayed(root: StrategyStepNode) -> StrategyStepNode:
    plans = _UNDO_PLANS.validate_json((_FIXTURES / "undo-plan.json").read_text())
    stated = node_of(root, "step_a").filters
    [name] = [n for n, r in _states().items() if node_of(r, "step_a").filters == stated]
    return plans[name].root


def test_the_step_views_the_undo_serializes_are_the_step_responses() -> None:
    held = json.loads((_FIXTURES / "weighted-plan.json").read_text())

    assert held == {name: _views(root) for name, root in _states().items()}


async def test_p1_undo_replay_holds_every_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    await commit_ops(deps, *_patch_ops())

    async def write(root: StrategyStepNode) -> int | None:
        return await commit_ops(deps, replace_with(_replayed(root)))

    assert await _row(env, plan_root(), write) == FIELDS
