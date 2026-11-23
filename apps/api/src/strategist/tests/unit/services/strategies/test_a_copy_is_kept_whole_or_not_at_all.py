from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.domain.strategy.validate import (
    StepValidationIssue,
    ValidationResult,
)
from strategist.services.eval import build_gold_strategy
from strategist.services.strategies import _tree_write, commit_tree
from strategist.services.strategies.save_substrategy import save_subtree_as_strategy
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
    plan_root,
)


async def _save(root: StrategyStepNode) -> int:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session.graph = graph
    saved = await save_subtree_as_strategy(
        session=session, site_id="plasmodb", source_step_id=root.id, name="Saved"
    )
    return saved.wdk_strategy_id


async def test_a_saved_copy_with_a_refused_step_leaves_no_step_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)

    async def _one_refused(*_args: object, **kwargs: Any) -> ValidatedParams:
        values = {**kwargs["context"], **kwargs["stated"]}
        if values.get("text_expression") == StringValue(value="membrane"):
            raise ValidationError(title="membrane is not a term")
        return ValidatedParams(params=values)

    monkeypatch.setattr(commit_tree, "validate_parameters", _one_refused)

    with pytest.raises(ValidationError):
        await _save(plan_root())

    assert len(env.wdk.written("POST", "/steps")) == 4
    assert (env.wdk.steps, env.wdk.strategies) == ({}, {})


async def test_a_saved_copy_wdk_departs_from_is_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    env.wdk.drops_the_weight_on_create = True

    with pytest.raises(ValidationError):
        await _save(plan_root())

    assert env.wdk.strategies == {}


async def test_a_saved_copy_is_marked_saved_only_after_it_is_read_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)

    strategy_id = await _save(plan_root())

    (made,) = env.wdk.written("POST", "/strategies")
    marks = [w for w in env.wdk.written("PATCH") if "isSaved" in w.body]
    assert made.body["isSaved"] is False
    assert [(w.path.rsplit("/", 1)[-1], w.body) for w in marks] == [
        (str(strategy_id), {"isSaved": True})
    ]
    assert env.wdk.strategies[strategy_id]["isSaved"] is True


async def test_a_gold_tree_the_strategy_check_refuses_leaves_no_step_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    issue = StepValidationIssue(path="root", message="no organism", code="organism")
    monkeypatch.setattr(
        _tree_write,
        "validate_strategy",
        lambda *_a, **_k: ValidationResult.failure([issue]),
    )

    with pytest.raises(ValidationError):
        await build_gold_strategy(
            gold_id="g1",
            site_id="plasmodb",
            step_tree=plan_root().model_dump(
                by_alias=True, exclude_none=True, mode="json"
            ),
        )

    assert len(env.wdk.written("POST", "/steps")) == 7
    assert (env.wdk.steps, env.wdk.strategies) == ({}, {})
