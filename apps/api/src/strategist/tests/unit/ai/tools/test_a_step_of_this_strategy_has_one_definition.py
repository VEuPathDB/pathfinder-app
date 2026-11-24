"""Every tool that names a step of the strategy refuses an id the strategy does
not hold with the one sentence, written in one place."""

from __future__ import annotations

import ast
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.standalone.optimization import sweep_can_run
from strategist.ai.tools.standalone.step_tally import step_columns
from strategist.ai.tools.standalone.strategy_attach import add_step_filter
from strategist.ai.tools.standalone.strategy_edits import (
    delete_step,
    insert_saved_strategy,
    replace_subtree,
    update_combine_operator,
    update_leaf_params,
    update_step_metadata,
)
from strategist.domain.evidence import NamedControlSet
from strategist.domain.strategy.session import not_a_step
from strategist.tests._support.run_context import lead_run_context
from strategist.tests.unit.ai.tools._strategy_edit_stubs import (
    combine,
    ctx,
    leaf,
    seed,
    session_with,
    stated_leaf,
)

_SOURCE = Path(__file__).resolve().parents[4]
_SENTENCE = "is not a step of this strategy"
_SET_ID = "96eaafb0-659c-4041-8bf3-5c66e5a9f95c"

type _Call = Callable[[RunContext[AgentDeps]], Awaitable[Any]]

_GRAPH_ID_CALLS: dict[str, _Call] = {
    "update_leaf_params": lambda c: update_leaf_params(c, "ghost", {}),
    "update_combine_operator": lambda c: update_combine_operator(
        c, "ghost", CombineOp.UNION
    ),
    "update_step_metadata": lambda c: update_step_metadata(c, "ghost", "x"),
    "delete_step": lambda c: delete_step(c, "ghost"),
    "replace_subtree": lambda c: replace_subtree(c, "ghost", stated_leaf("n")),
    "insert_saved_strategy": lambda c: insert_saved_strategy(c, "ghost", 7),
    "add_step_filter": lambda c: add_step_filter(c, "ghost", "f", "v"),
}


@pytest.mark.parametrize("call", list(_GRAPH_ID_CALLS.values()), ids=_GRAPH_ID_CALLS)
async def test_a_tool_refuses_a_step_id_the_graph_does_not_hold(call: _Call) -> None:
    root = combine("step_c", leaf("step_a"), leaf("step_b"), CombineOp.INTERSECT)
    deps = seed(root, {"step_a": 11, "step_b": 12, "step_c": 13})

    with pytest.raises(ModelRetry) as refused:
        await call(ctx(deps))

    assert str(refused.value) == (
        "Step ghost is not a step of this strategy. It holds step_a, step_b, step_c."
    )


async def test_a_read_refuses_a_wdk_step_id_the_strategy_did_not_build() -> None:
    deps = lead_run_context(
        strategy_session=session_with(leaf("step_a"), {"step_a": 11})
    )

    with pytest.raises(ModelRetry) as refused:
        await step_columns(deps, 99)

    assert str(refused.value) == "Step 99 is not a step of this strategy. It holds 11."


async def test_a_sweep_on_a_strategy_with_no_built_step_is_refused() -> None:
    run = lead_run_context(strategy_session=session_with(leaf("step_a"), {}))
    run.deps.state.domain.attach_control_set(
        NamedControlSet(id=_SET_ID, name="Signal peptide controls")
    )

    with pytest.raises(ModelRetry) as refused:
        await sweep_can_run(run, reply="", wdk_step_id=99, control_set_id=_SET_ID)

    assert str(refused.value) == (
        "Step 99 is not a step of this strategy. It holds no step yet. Nothing was "
        "started and no card was shown."
    )


def test_the_sentence_lists_what_the_strategy_holds() -> None:
    assert (not_a_step("x", ["a", "b"]), not_a_step("x", [])) == (
        "Step x is not a step of this strategy. It holds a, b.",
        "Step x is not a step of this strategy. It holds no step yet.",
    )


def _production_files() -> list[Path]:
    return [
        path
        for path in _SOURCE.rglob("*.py")
        if "tests" not in path.relative_to(_SOURCE).parts
    ]


def test_the_sentence_is_written_once() -> None:
    writers = sorted(
        str(path.relative_to(_SOURCE))
        for path in _production_files()
        if _SENTENCE in path.read_text()
    )

    assert writers == ["domain/strategy/session.py"]


def _refuses_on_membership(node: ast.If) -> bool:
    raises = any(isinstance(n, ast.Raise) for n in ast.walk(node))
    test = node.test
    return (
        raises
        and isinstance(test, ast.Compare)
        and any(isinstance(op, ast.NotIn) for op in test.ops)
        and any(
            isinstance(c, ast.Attribute) and c.attr == "steps" for c in test.comparators
        )
    )


def test_no_tool_refuses_on_its_own_step_membership_check() -> None:
    found = sorted(
        f"{path.relative_to(_SOURCE)}:{node.lineno}"
        for path in _production_files()
        if path.relative_to(_SOURCE).parts[0] == "ai"
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.If) and _refuses_on_membership(node)
    )

    assert found == []
