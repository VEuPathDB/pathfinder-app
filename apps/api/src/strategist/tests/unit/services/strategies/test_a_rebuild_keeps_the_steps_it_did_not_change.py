from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import ValidatedParams

from strategist.services.strategies import commit_tree, spec_build
from strategist.services.strategies.spec_build import build_strategy_from_spec
from strategist.services.strategies.sync_state import ensure_sync_state
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
    new_thread,
)


def _leaf(step_id: str, words: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByTextSearch",
        display_name=step_id,
        parameters={"text_expression": StringValue(value=words)},
    )


def _tree(b_words: str, b_search: str = "GenesByTextSearch") -> StrategyStepNode:
    return StrategyStepNode(
        id="j2",
        search_name="__combine__",
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="j1",
            search_name="__combine__",
            operator=CombineOp.UNION,
            primary_input=_leaf("c_a", "kinase"),
            secondary_input=_leaf("c_b", b_words).model_copy(
                update={"search_name": b_search}
            ),
        ),
        secondary_input=_leaf("c_c", "membrane"),
    )


async def test_a_rebuild_that_moves_a_value_patches_that_step_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await build_strategy_from_spec(deps=deps, root=_tree("rhoptry"))
    sync_state = ensure_sync_state(deps.strategy_session)
    first = dict(sync_state.wdk_step_ids)
    env.wdk.writes.clear()
    env.wdk.answer_size = 412

    outcome = await build_strategy_from_spec(deps=deps, root=_tree("exported"))

    assert [(w.method, w.path) for w in env.wdk.writes] == [
        ("PUT", f"/users/1/steps/{first['c_b']}/search-config")
    ]
    assert sync_state.wdk_step_ids == first
    assert sync_state.step_counts == dict.fromkeys(first, 412)
    assert outcome.failed_steps == []


async def test_a_rebuild_that_moves_a_search_recreates_it_and_the_combines_above(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await build_strategy_from_spec(deps=deps, root=_tree("rhoptry"))
    sync_state = ensure_sync_state(deps.strategy_session)
    first = dict(sync_state.wdk_step_ids)
    env.wdk.writes.clear()
    env.wdk.answer_size = 412

    outcome = await build_strategy_from_spec(
        deps=deps, root=_tree("rhoptry", "GenesByOtherText")
    )

    posted = [w.body["searchName"] for w in env.wdk.written("POST", "/steps")]
    assert posted == [
        "GenesByOtherText",
        "boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
        "boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
    ]
    assert {k: sync_state.wdk_step_ids[k] == v for k, v in first.items()} == {
        "c_a": True,
        "c_b": False,
        "c_c": True,
        "j1": False,
        "j2": False,
    }
    gone = {first["c_b"], first["j1"], first["j2"]}
    assert gone & set(env.wdk.steps) == set()
    puts = [i for i, w in enumerate(env.wdk.writes) if w.path.endswith("/step-tree")]
    deletes = [i for i, w in enumerate(env.wdk.writes) if w.method == "DELETE"]
    assert max(puts) < min(deletes)
    assert sync_state.step_counts == dict.fromkeys(first, 412)
    assert outcome.failed_steps == []


async def test_a_refused_leaf_fails_its_build_and_its_sibling_still_lands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)

    async def _refusing(*_args: object, **kwargs: Any) -> ValidatedParams:
        stated: dict[str, ParamValue] = {**kwargs["context"], **kwargs["stated"]}
        if stated.get("text_expression") == StringValue(value="nonsense"):
            raise ValidationError(
                title="Invalid parameter value", detail="text_expression: refused"
            )
        return ValidatedParams(params=stated)

    monkeypatch.setattr(commit_tree, "validate_parameters", _refusing)
    root = StrategyStepNode(
        id="j1",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=_leaf("c_a", "nonsense"),
        secondary_input=_leaf("c_b", "rhoptry"),
    )

    outcome = await build_strategy_from_spec(deps=new_thread(), root=root)

    assert [(f.step_id, f.error) for f in outcome.failed_steps] == [
        ("c_a", "text_expression: refused")
    ]
    assert (outcome.pushed_step_ids, outcome.skipped_step_ids) == (["c_b"], ["j1"])
    assert env.wdk.written("POST", "/strategies") == []
    assert outcome.wdk_strategy_id is None


async def test_a_rebuild_in_place_reports_the_strategy_its_zeros_and_refreshes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    refreshes: list[object] = []

    async def _refresh(deps: object) -> None:
        refreshes.append(deps)

    monkeypatch.setattr(spec_build, "defer_the_gene_set_refresh", _refresh)
    deps = new_thread()
    first = await build_strategy_from_spec(deps=deps, root=_tree("rhoptry"))
    env.wdk.answer_size = 0

    second = await build_strategy_from_spec(deps=deps, root=_tree("exported"))

    assert second.wdk_strategy_id == first.wdk_strategy_id
    assert first.wdk_strategy_id is not None
    assert sorted(second.zero_step_ids) == ["c_a", "c_b", "c_c", "j1", "j2"]
    assert len(refreshes) == 2
