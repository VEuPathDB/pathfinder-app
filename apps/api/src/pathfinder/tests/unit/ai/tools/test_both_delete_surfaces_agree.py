"""The Lead's delete and the BUILD sub-agent's delete answer one question once.

Both mount ``strategy_edits.delete_step``: the Lead through its wrapper, the
execution toolset directly. Neither chooses a resolution; the rules do.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from inspect import signature
from typing import Any

import pytest
from pydantic import JsonValue
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.lead import lead_tools
from pathfinder.ai.tools.standalone import strategy_edits
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    ctx,
    install_stub_api,
    leaf,
    seed,
    session_with,
)

type Delete = Callable[[StrategySession, str], Awaitable[Any]]


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


async def _through_the_lead(session: StrategySession, step_id: str) -> Any:
    run_ctx = lead_run_context(
        user_prompt="remove that step",
        strategy_session=session,
        tool_call_id="call_delete",
    )
    return await lead_tools.delete_step(run_ctx, step_id=step_id)


async def _through_the_sub_agent(session: StrategySession, step_id: str) -> Any:
    deps = seed(leaf("unused"), {})
    deps.strategy_session = session
    return await strategy_edits.delete_step(ctx(deps), step_id)


SURFACES: list[Delete] = [_through_the_lead, _through_the_sub_agent]


def _split_session() -> StrategySession:
    """A strategy, a loose component, and no push naming either as the root."""
    session = session_with(combine("step_c1", leaf("step_k1"), leaf("step_k2")), {})
    graph = session.graph
    assert graph is not None
    graph.steps.update(
        flatten_tree(combine("step_c9", leaf("step_k8"), leaf("step_k9"))),
    )
    graph.recompute_roots()
    return session


def _transform_rooted_session() -> StrategySession:
    return session_with(
        StrategyStepNode(
            id="step_t1",
            search_name="GenesByOrthologs",
            primary_input=combine("step_c1", leaf("step_k1"), leaf("step_k2")),
        ),
        {},
    )


def _graph(session: StrategySession) -> StrategyGraph:
    graph = session.graph
    assert graph is not None
    return graph


def test_the_sub_agent_tool_takes_no_resolution_argument() -> None:
    """No caller may ask for delete-strategy, so the argument is gone.

    The model's schema is derived from the signature, so the signature is
    where the argument is absent.
    """
    named = signature(strategy_edits.delete_step).parameters

    assert "resolution" not in named
    assert sorted(named) == ["ctx", "graph_id", "step_id"]


@pytest.mark.parametrize("delete", SURFACES)
async def test_an_ambiguous_root_is_refused_on_both(
    stub_api: StubAPI, delete: Delete
) -> None:
    session = _split_session()

    with pytest.raises(ModelRetry) as raised:
        await delete(session, "step_c1")

    assert "no push says which of them the strategy is" in str(raised.value)
    assert "step_c1 (3 steps)" in str(raised.value)
    assert stub_api.named("delete_step") == []
    assert len(_graph(session).steps) == 6


@pytest.mark.parametrize("delete", SURFACES)
async def test_a_root_transform_is_refused_on_both(
    stub_api: StubAPI, delete: Delete
) -> None:
    session = _transform_rooted_session()

    with pytest.raises(ModelRetry) as raised:
        await delete(session, "step_t1")

    assert "no delete gives its input step_c1 the root" in str(raised.value)
    assert stub_api.named("delete_step") == []


@pytest.mark.parametrize("delete", SURFACES)
async def test_a_root_combine_collapses_on_both(
    stub_api: StubAPI, delete: Delete
) -> None:
    session = session_with(combine("step_c1", leaf("step_k1"), leaf("step_k2")), {})

    answer = await delete(session, "step_c1")

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_c1", "step_k2"]
    assert sorted(_graph(session).steps) == ["step_k1"]


@pytest.mark.parametrize("delete", SURFACES)
async def test_a_combine_under_a_transform_keeps_the_primary_on_both(
    stub_api: StubAPI, delete: Delete
) -> None:
    session = _transform_rooted_session()

    answer = await delete(session, "step_c1")

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_c1", "step_k2"]
    assert sorted(_graph(session).steps) == ["step_k1", "step_t1"]


@pytest.mark.parametrize("delete", SURFACES)
async def test_a_loose_step_of_one_step_goes_on_both(
    stub_api: StubAPI, delete: Delete
) -> None:
    session = session_with(combine("step_c1", leaf("step_k1"), leaf("step_k2")), {})
    graph = _graph(session)
    graph.steps.update(flatten_tree(leaf("step_export")))
    graph.recompute_roots()

    answer = await delete(session, "step_export")

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_export"]
    assert sorted(_graph(session).steps) == ["step_c1", "step_k1", "step_k2"]


_THE_LEADS_WAY_OUT = "call clear_strategy"
_THE_BUILD_WAY_OUT = "stop and report it to the Lead, which can clear the strategy"


@pytest.mark.parametrize(
    ("delete", "way_out"),
    [
        (_through_the_lead, _THE_LEADS_WAY_OUT),
        (_through_the_sub_agent, _THE_BUILD_WAY_OUT),
    ],
)
async def test_an_ambiguous_root_names_the_way_out_this_caller_has(
    stub_api: StubAPI, delete: Delete, way_out: str
) -> None:
    """Only the Lead holds clear_strategy, so only the Lead is told to call it."""
    session = _split_session()

    with pytest.raises(ModelRetry) as raised:
        await delete(session, "step_c1")

    assert way_out in str(raised.value)
    assert stub_api.named("delete_step") == []


@pytest.mark.parametrize(
    ("delete", "way_out"),
    [
        (_through_the_lead, _THE_LEADS_WAY_OUT),
        (_through_the_sub_agent, _THE_BUILD_WAY_OUT),
    ],
)
async def test_a_root_transform_names_the_way_out_this_caller_has(
    stub_api: StubAPI, delete: Delete, way_out: str
) -> None:
    session = _transform_rooted_session()

    with pytest.raises(ModelRetry) as raised:
        await delete(session, "step_t1")

    assert way_out in str(raised.value)


async def test_the_building_pass_is_never_told_to_clear_the_strategy(
    stub_api: StubAPI,
) -> None:
    """The building pass does not hold clear_strategy, so the name misleads it."""
    session = _split_session()

    with pytest.raises(ModelRetry) as raised:
        await _through_the_sub_agent(session, "step_c1")

    assert "clear_strategy" not in str(raised.value)
    assert stub_api.named("delete_step") == []


async def test_the_refusal_lists_the_largest_root_first(stub_api: StubAPI) -> None:
    """The list reads as a ranking, so the thread that holds the most is first."""
    session = session_with(combine("step_zc", leaf("step_k1"), leaf("step_k2")), {})
    graph = _graph(session)
    graph.steps.update(flatten_tree(leaf("step_a1")))
    graph.recompute_roots()

    with pytest.raises(ModelRetry) as raised:
        await _through_the_lead(session, "step_zc")

    assert "step_zc (3 steps), step_a1 (1 step)" in str(raised.value)
