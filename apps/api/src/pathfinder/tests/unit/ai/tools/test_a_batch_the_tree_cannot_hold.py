"""A batch the strategy cannot be rebuilt from leaves the strategy as it was.

Every operation applies to the live nodes, so a batch that lands a tree no
reader can rebuild would take every later read of the strategy with it.
"""

from __future__ import annotations

from itertools import count
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp
from veupathdb.errors import ValidationError

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.tools.standalone.strategy import apply_operations
from pathfinder.ai.tools.toolsets.execution import build_toolset
from pathfinder.domain.strategy.operations import AddLeafOp
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.operations.types import AttachNewRoot
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import commit as commit_module
from pathfinder.services.strategies.commit import apply_operations_and_commit

from ._strategy_edit_stubs import (
    StubAPI,
    combine,
    ctx,
    install_stub_api,
    leaf,
    session_with,
)

_WDK_STEP_IDS = {"step_k1": 101, "step_k2": 102, "step_k3": 103}

_A_COMBINE_WITH_NO_OPERATOR = {
    "kind": "addCombine",
    "step": {"id": "step_cn", "searchName": COMBINE_SEARCH_NAME},
    "leftId": "step_k1",
    "rightId": "step_k3",
}

_A_TRANSFORM_OVER_A_BRANCH = {
    "kind": "addTransform",
    "step": {"id": "step_new", "searchName": "GenesByOrthologs"},
    "inputId": "step_k2",
    "mode": "new-root",
}

_A_STEP_WIRED_INTO_ITSELF = {
    "kind": "wireInput",
    "targetStepId": "step_k1",
    "slot": "primary",
    "sourceStepId": "step_k1",
}

_A_STEP_WIRED_UNDER_ITS_OWN_INPUT = {
    "kind": "wireInput",
    "targetStepId": "step_k2",
    "slot": "primary",
    "sourceStepId": "step_c1",
}

_THE_ROOT_WIRED_UNDER_A_LEAF = {
    "kind": "wireInput",
    "targetStepId": "step_k1",
    "slot": "primary",
    "sourceStepId": "step_c2",
}


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


def _deps() -> AgentDeps:
    root = combine(
        "step_c2",
        combine("step_c1", leaf("step_k1"), leaf("step_k2"), op=CombineOp.UNION),
        leaf("step_k3"),
    )
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(root, _WDK_STEP_IDS),
        conversation_id=uuid4(),
        turn_markers=TurnMarkers(),
    )


def _graph(deps: AgentDeps) -> StrategyGraph:
    graph = deps.strategy_session.graph
    assert graph is not None
    return graph


async def _sent(deps: AgentDeps, *payloads: dict[str, Any]) -> None:
    graph = _graph(deps)
    tools = await build_toolset().get_tools(ctx(deps))
    args = tools["apply_operations"].args_validator.validate_python(
        {
            "base_revision": strategy_revision(graph.to_strategy_ast()),
            "operations": list(payloads),
        }
    )
    await apply_operations(ctx(deps), **args)


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (_A_COMBINE_WITH_NO_OPERATOR, "operator is required when secondaryInput"),
        (_A_TRANSFORM_OVER_A_BRANCH, "duplicate step ids: ['step_k2']"),
    ],
)
async def test_the_graph_is_what_it_was_before_the_batch(
    stub_api: StubAPI, payload: dict[str, Any], reason: str
) -> None:
    deps = _deps()
    graph = _graph(deps)
    before = sorted(graph.steps)

    with pytest.raises(ModelRetry) as caught:
        await _sent(deps, payload)

    assert "cannot be read back" in str(caught.value)
    assert reason in str(caught.value)
    assert "Nothing was applied" in str(caught.value)
    assert "VEuPathDB was not asked" in str(caught.value)
    assert sorted(graph.steps) == before
    assert before == ["step_c1", "step_c2", "step_k1", "step_k2", "step_k3"]
    assert stub_api.calls == []


@pytest.mark.parametrize(
    "payload", [_A_COMBINE_WITH_NO_OPERATOR, _A_TRANSFORM_OVER_A_BRANCH]
)
async def test_the_thread_answers_the_next_operation(
    stub_api: StubAPI, payload: dict[str, Any]
) -> None:
    """The strategy still reads, so the next turn is not stuck on the bad batch."""
    deps = _deps()
    graph = _graph(deps)

    with pytest.raises(ModelRetry):
        await _sent(deps, payload)

    after = graph.to_strategy_ast()
    assert after is not None
    assert after.root.id == "step_c2"

    await _sent(
        deps,
        {
            "kind": "updateStepMeta",
            "stepId": "step_k1",
            "displayName": "Kinase domain",
        },
    )

    assert graph.steps["step_k1"].display_name == "Kinase domain"


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (_A_STEP_WIRED_INTO_ITSELF, "step_k1 cannot take its own output as an input"),
        (
            _A_STEP_WIRED_UNDER_ITS_OWN_INPUT,
            (
                "step_c1 already reads step_k2, so wiring it into step_k2 would "
                "make a loop"
            ),
        ),
        (
            _THE_ROOT_WIRED_UNDER_A_LEAF,
            (
                "step_c2 already reads step_k1, so wiring it into step_k1 would "
                "make a loop"
            ),
        ),
    ],
)
async def test_a_wire_that_loops_is_refused_before_it_is_written(
    stub_api: StubAPI, payload: dict[str, Any], reason: str
) -> None:
    """A step that read its own output would leave a tree no reader can walk."""
    deps = _deps()
    graph = _graph(deps)

    with pytest.raises(ModelRetry) as caught:
        await _sent(deps, payload)

    assert reason in str(caught.value)
    assert "Nothing was applied" in str(caught.value)
    assert "VEuPathDB was not asked" in str(caught.value)
    assert graph.steps["step_k1"].primary_input_id is None
    assert graph.steps["step_k2"].primary_input_id is None
    assert sorted(graph.roots) == ["step_c2"]
    assert stub_api.calls == []


async def test_the_thread_answers_after_a_wire_that_loops(stub_api: StubAPI) -> None:
    deps = _deps()
    graph = _graph(deps)

    with pytest.raises(ModelRetry):
        await _sent(deps, _A_STEP_WIRED_INTO_ITSELF)

    after = graph.to_strategy_ast()
    assert after is not None
    assert after.root.id == "step_c2"

    await _sent(
        deps,
        {"kind": "updateStepMeta", "stepId": "step_k1", "displayName": "Kinase domain"},
    )

    assert graph.steps["step_k1"].display_name == "Kinase domain"


async def test_a_rebuild_that_recurses_puts_the_graph_back(
    stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard holds for a rebuild that never returns, not only for a bad value."""
    deps = _deps()
    graph = _graph(deps)
    before = sorted(graph.steps)
    reads = count()
    rebuild = StrategyGraph.to_strategy_ast

    def _recurses(self: StrategyGraph, *args: Any, **kwargs: Any) -> Any:
        if next(reads) > 0:
            msg = "maximum recursion depth exceeded"
            raise RecursionError(msg)
        return rebuild(self, *args, **kwargs)

    monkeypatch.setattr(StrategyGraph, "to_strategy_ast", _recurses)

    with pytest.raises(ApplyError) as caught:
        await apply_operations_and_commit(
            deps=deps.to_strategy_context(),
            ops=[AddLeafOp(step=leaf("step_new"), attach=AttachNewRoot())],
        )

    assert "cannot be read back" in str(caught.value)
    assert sorted(graph.steps) == before
    assert stub_api.calls == []


async def test_a_push_the_site_refuses_puts_the_graph_back(
    stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The push raises after the batch applied, so the graph is put back.

    The next plan is measured against the strategy the researcher has, and a
    graph left ahead of it would state a step no push ever landed.
    """
    deps = _deps()
    graph = _graph(deps)
    before = sorted(graph.steps)

    async def _refuses(*_args: Any, **_kwargs: Any) -> Any:
        raise ValidationError(title="Invalid", detail="min_pep: Cannot be empty.")

    monkeypatch.setattr(commit_module, "push_steps_with_plan", _refuses)

    with pytest.raises(ValidationError):
        await apply_operations_and_commit(
            deps=deps.to_strategy_context(),
            ops=[AddLeafOp(step=leaf("step_new"), attach=AttachNewRoot())],
        )

    assert sorted(graph.steps) == before
    assert "step_new" not in graph.steps
    assert sorted(graph.roots) == ["step_c2"]


async def test_a_rolled_back_batch_keeps_the_name_it_had(stub_api: StubAPI) -> None:
    """A refusal says the strategy is unchanged, so its name is unchanged too."""
    deps = _deps()
    graph = _graph(deps)
    before = graph.name

    with pytest.raises(ModelRetry):
        await _sent(
            deps,
            {"kind": "updateStrategyMeta", "name": "Renamed", "description": "New d"},
            _A_COMBINE_WITH_NO_OPERATOR,
        )

    assert graph.name == before
    assert graph.name == "Test"
    assert graph.description is None


_A_RENAME = {"kind": "updateStrategyMeta", "name": "Renamed", "description": "New d"}

_A_COMBINE_OVER_A_STEP_THAT_IS_GONE = {
    "kind": "addCombine",
    "step": {"id": "step_cn", "searchName": COMBINE_SEARCH_NAME, "operator": "UNION"},
    "leftId": "step_k1",
    "rightId": "step_k3",
}


async def test_a_refused_batch_on_an_empty_graph_keeps_the_name_it_had(
    stub_api: StubAPI,
) -> None:
    """A graph with no steps has no tree to replay, and is restored all the same."""
    deps = _deps()
    graph = _graph(deps)
    graph.steps.clear()
    graph.roots.clear()
    graph.last_step_id = None

    with pytest.raises(ModelRetry):
        await _sent(deps, _A_RENAME, _A_COMBINE_OVER_A_STEP_THAT_IS_GONE)

    assert (graph.name, graph.description) == ("Test", None)
    assert graph.steps == {}
    assert stub_api.calls == []


async def test_a_rolled_back_batch_keeps_the_write_cursor_it_had(
    stub_api: StubAPI,
) -> None:
    """The cursor names the step the last write settled on, not the root."""
    deps = _deps()
    graph = _graph(deps)
    graph.last_step_id = "step_k3"

    with pytest.raises(ModelRetry):
        await _sent(deps, _A_COMBINE_WITH_NO_OPERATOR)

    assert graph.last_step_id == "step_k3"
    assert stub_api.calls == []
