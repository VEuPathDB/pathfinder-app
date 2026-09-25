"""The Lead removes a step the user wants gone, with their approval."""

from __future__ import annotations

import pytest
from pydantic import JsonValue
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStepTree

from pathfinder.ai.lead.lead_tools import delete_step
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)

_REPLY = "I remove the step you named, and the rest stays."


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


def _cite(session: StrategySession, step_id: str) -> None:
    """Record the push that names this step the WDK strategy's root step."""
    session.sync_state = WDKSyncState(
        wdk_step_ids={step_id: 9001},
        wdk_strategy_id=42,
        wdk_step_tree=WDKStepTree(step_id=9001),
    )


def _ctx(*, detached: bool = False, cited: bool = False) -> RunContext[LeadDeps]:
    session = session_with(combine("step_c1", leaf("step_k1"), leaf("step_k2")), {})
    graph = session.graph
    assert graph is not None
    if detached:
        graph.steps.update(flatten_tree(leaf("step_loose")))
        graph.recompute_roots()
    if cited:
        _cite(session, "step_c1")
    ctx = lead_run_context(
        user_prompt="remove any step that is not connected",
        strategy_session=session,
        tool_call_id="call_delete",
    )
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal="essential kinases",
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon"),
            Criterion(id="step_k2", text="blood stages", search_name="GenesByTaxon"),
        ],
    )
    return ctx


def _graph(ctx: RunContext[LeadDeps]) -> StrategyGraph:
    graph = ctx.deps.runtime.strategy_session.graph
    assert graph is not None
    return graph


async def test_a_detached_root_is_removed_and_the_turn_is_marked(
    stub_api: StubAPI,
) -> None:
    """The detached export is one step, so it goes with no push naming a root.

    A root of one step takes only itself, so the approval card names the whole
    effect and the ambiguity of a split thread does not arise.
    """
    ctx = _ctx(detached=True)

    answer = await delete_step(ctx, step_id="step_loose", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_loose"]
    assert sorted(_graph(ctx).steps) == ["step_c1", "step_k1", "step_k2"]
    assert ctx.deps.state.turn_markers.edited is True
    assert ctx.deps.state.turn_markers.changed_strategy is True


async def test_an_inner_leaf_collapses_its_combine(stub_api: StubAPI) -> None:
    ctx = _ctx()

    answer = await delete_step(ctx, step_id="step_k2", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_c1", "step_k2"]
    assert sorted(_graph(ctx).steps) == ["step_k1"]


async def test_the_deleted_step_leaves_the_spec(stub_api: StubAPI) -> None:
    ctx = _ctx()

    await delete_step(ctx, step_id="step_k2", reply=_REPLY)

    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == ["step_k1"]


async def test_a_step_the_graph_does_not_hold_is_refused(stub_api: StubAPI) -> None:
    ctx = _ctx()

    with pytest.raises(ModelRetry) as raised:
        await delete_step(ctx, step_id="step_gone", reply=_REPLY)

    assert "step_gone" in str(raised.value)
    assert "step_c1" in str(raised.value)
    assert stub_api.named("delete_step") == []
    assert ctx.deps.state.turn_markers.edited is False


async def test_the_only_step_of_a_strategy_is_removed(stub_api: StubAPI) -> None:
    """A leaf that is its own root has no combine above it to collapse."""
    session = session_with(leaf("step_k1"), {})
    ctx = lead_run_context(
        user_prompt="remove that step",
        strategy_session=session,
        tool_call_id="call_delete",
    )

    answer = await delete_step(ctx, step_id="step_k1", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_k1"]
    assert _graph(ctx).steps == {}
    assert ctx.deps.state.turn_markers.edited is True


async def test_the_root_combine_collapses_onto_its_primary_input(
    stub_api: StubAPI,
) -> None:
    """A combine of the strategy goes with one input; the other becomes root."""
    ctx = _ctx()

    answer = await delete_step(ctx, step_id="step_c1", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_c1", "step_k2"]
    assert sorted(_graph(ctx).steps) == ["step_k1"]
    assert _graph(ctx).primary_root_id() == "step_k1"


def _with_a_detached_combine(ctx: RunContext[LeadDeps]) -> StrategyGraph:
    graph = _graph(ctx)
    graph.steps.update(
        flatten_tree(combine("step_c9", leaf("step_k8"), leaf("step_k9"))),
    )
    graph.recompute_roots()
    return graph


async def test_a_detached_root_takes_its_whole_subtree(stub_api: StubAPI) -> None:
    """Naming the loose component's root clears the component."""
    ctx = _ctx(cited=True)
    _with_a_detached_combine(ctx)

    answer = await delete_step(ctx, step_id="step_c9", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_c9", "step_k8", "step_k9"]
    assert sorted(_graph(ctx).steps) == ["step_c1", "step_k1", "step_k2"]
    assert sorted(_graph(ctx).roots) == ["step_c1"]


async def test_a_detached_inner_step_collapses_its_own_combine(
    stub_api: StubAPI,
) -> None:
    """A step with a combine above it collapses it, inside the strategy or out."""
    ctx = _ctx()
    _with_a_detached_combine(ctx)

    answer = await delete_step(ctx, step_id="step_k8", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_c9", "step_k8"]
    assert sorted(_graph(ctx).steps) == [
        "step_c1",
        "step_k1",
        "step_k2",
        "step_k9",
    ]
    assert sorted(_graph(ctx).roots) == ["step_c1", "step_k9"]


def _transform_over(inner: StrategyStepNode) -> StrategyStepNode:
    """A transform reading one input, the shape an ortholog step takes."""
    return StrategyStepNode(
        id="step_t1", search_name="GenesByOrthologs", primary_input=inner
    )


def _rooted_transform_ctx() -> RunContext[LeadDeps]:
    session = session_with(
        _transform_over(combine("step_c1", leaf("step_k1"), leaf("step_k2"))), {}
    )
    return lead_run_context(
        user_prompt="drop the ortholog step",
        strategy_session=session,
        tool_call_id="call_delete",
    )


async def test_the_strategy_root_transform_leaves_its_input_the_root(
    stub_api: StubAPI,
) -> None:
    """A deleted step's primary input stands where it stood, the root included."""
    ctx = _rooted_transform_ctx()

    answer = await delete_step(ctx, step_id="step_t1", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_t1"]
    assert sorted(_graph(ctx).steps) == ["step_c1", "step_k1", "step_k2"]
    assert _graph(ctx).primary_root_id() == "step_c1"
    assert ctx.deps.state.turn_markers.edited is True


async def test_a_step_under_a_root_transform_takes_the_transform_with_it(
    stub_api: StubAPI,
) -> None:
    ctx = lead_run_context(
        user_prompt="drop the kinase step",
        strategy_session=session_with(_transform_over(leaf("step_k1")), {}),
        tool_call_id="call_delete",
    )

    answer = await delete_step(ctx, step_id="step_k1", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_k1", "step_t1"]
    assert _graph(ctx).steps == {}


async def _loose_component_ctx() -> RunContext[LeadDeps]:
    """One-step strategy, a three-step leftover, and no push naming a root."""
    session = session_with(leaf("step_main"), {})
    graph = session.graph
    assert graph is not None
    graph.steps.update(
        flatten_tree(combine("step_c9", leaf("step_k8"), leaf("step_k9"))),
    )
    graph.recompute_roots()
    return lead_run_context(
        user_prompt="remove the steps that are not connected",
        strategy_session=session,
        tool_call_id="call_delete",
    )


async def test_a_root_of_a_split_thread_no_push_named_is_refused(
    stub_api: StubAPI,
) -> None:
    """Size is not identity, so the strategy's root is not guessed."""
    ctx = await _loose_component_ctx()

    with pytest.raises(ModelRetry) as raised:
        await delete_step(ctx, step_id="step_c9", reply=_REPLY)

    assert str(raised.value) == (
        "step_c9 is one of the 2 roots this conversation holds, and no push says "
        "which of them the strategy is: step_c9 (3 steps), step_main (1 step). "
        "Nothing was removed. Name a step under the one you mean, or call "
        "clear_strategy to remove every step of the conversation."
    )
    assert stub_api.named("delete_step") == []
    assert sorted(_graph(ctx).steps) == [
        "step_c9",
        "step_k8",
        "step_k9",
        "step_main",
    ]
    assert ctx.deps.state.turn_markers.edited is False


async def test_the_root_combine_of_a_split_thread_is_never_wiped(
    stub_api: StubAPI,
) -> None:
    """The leftover can outweigh the strategy, so neither root is re-wired."""
    session = session_with(combine("step_c1", leaf("step_k1"), leaf("step_k2")), {})
    graph = session.graph
    assert graph is not None
    graph.steps.update(
        flatten_tree(
            combine(
                "step_c9",
                combine("step_c8", leaf("step_k7"), leaf("step_k8")),
                leaf("step_k9"),
            ),
        ),
    )
    graph.recompute_roots()
    ctx = lead_run_context(
        user_prompt="remove the intersect step",
        strategy_session=session,
        tool_call_id="call_delete",
    )

    with pytest.raises(ModelRetry) as raised:
        await delete_step(ctx, step_id="step_c1", reply=_REPLY)

    assert "step_c1 (3 steps)" in str(raised.value)
    assert "step_c9 (5 steps)" in str(raised.value)
    assert sorted(_graph(ctx).steps) == [
        "step_c1",
        "step_c8",
        "step_c9",
        "step_k1",
        "step_k2",
        "step_k7",
        "step_k8",
        "step_k9",
    ]
    assert ctx.deps.state.turn_markers.edited is False


async def test_a_root_transform_of_a_split_thread_is_refused_as_ambiguous(
    stub_api: StubAPI,
) -> None:
    ctx = lead_run_context(
        user_prompt="drop the ortholog step",
        strategy_session=session_with(
            _transform_over(combine("step_c1", leaf("step_k1"), leaf("step_k2"))), {}
        ),
        tool_call_id="call_delete",
    )
    graph = _graph(ctx)
    graph.steps.update(flatten_tree(leaf("step_loose")))
    graph.recompute_roots()

    with pytest.raises(ModelRetry) as raised:
        await delete_step(ctx, step_id="step_t1", reply=_REPLY)

    assert "no push says which of them the strategy is" in str(raised.value)
    assert stub_api.named("delete_step") == []
    assert ctx.deps.state.turn_markers.edited is False


async def test_a_step_under_a_root_of_a_split_thread_is_unambiguous(
    stub_api: StubAPI,
) -> None:
    """A step with a parent names its own component, so it is not refused."""
    ctx = await _loose_component_ctx()

    answer = await delete_step(ctx, step_id="step_k8", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_c9", "step_k8"]
    assert sorted(_graph(ctx).steps) == ["step_k9", "step_main"]


async def test_a_combine_under_a_root_transform_leaves_its_secondary_branch(
    stub_api: StubAPI,
) -> None:
    """The transform reads the primary, which is what the refusal advises."""
    ctx = _rooted_transform_ctx()

    answer = await delete_step(ctx, step_id="step_c1", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_c1", "step_k2"]
    assert sorted(_graph(ctx).steps) == ["step_k1", "step_t1"]
    assert _graph(ctx).steps["step_t1"].primary_input_id == "step_k1"


async def test_a_transform_under_a_transform_leaves_its_input_in_its_place(
    stub_api: StubAPI,
) -> None:
    """The stack keeps the step the inner transform read, under the outer one."""
    stacked = StrategyStepNode(
        id="step_t2",
        search_name="GenesByOrthologs",
        primary_input=_transform_over(leaf("step_k1")),
    )
    ctx = lead_run_context(
        user_prompt="drop the inner ortholog step",
        strategy_session=session_with(stacked, {}),
        tool_call_id="call_delete",
    )

    answer = await delete_step(ctx, step_id="step_t1", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_t1"]
    assert sorted(_graph(ctx).steps) == ["step_k1", "step_t2"]
    assert _graph(ctx).steps["step_t2"].primary_input_id == "step_k1"


async def test_the_cited_root_decides_when_it_is_not_the_largest(
    stub_api: StubAPI,
) -> None:
    """The last push named step_main, so the larger component is not the root."""
    session = session_with(leaf("step_main"), {"step_main": 9001})
    graph = session.graph
    assert graph is not None
    graph.steps.update(
        flatten_tree(combine("step_c9", leaf("step_k8"), leaf("step_k9"))),
    )
    graph.recompute_roots()
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_main": 9001},
        wdk_strategy_id=42,
        wdk_step_tree=WDKStepTree(step_id=9001),
    )
    ctx = lead_run_context(
        user_prompt="remove the steps that are not connected",
        strategy_session=session,
        tool_call_id="call_delete",
    )

    answer = await delete_step(ctx, step_id="step_c9", reply=_REPLY)

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_c9", "step_k8", "step_k9"]
    assert sorted(_graph(ctx).steps) == ["step_main"]
