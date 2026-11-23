from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.build_outcome import citable_count
from strategist.domain.strategy.operations import (
    DeleteResolution,
    DeleteStepOp,
    UpdateStepMetaOp,
    UpdateStepParamsOp,
)
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.domain.strategy.step_words import StepWords
from strategist.services.strategies import commit, stated_sides
from strategist.services.strategies.commit import apply_and_commit
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.recording_wdk import (
    RecordingWDK,
    held_by_the_site,
    served,
)
from strategist.tests._support.wdk_write_stubs import serve_the_site, skip_the_tree_put


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> RecordingWDK:
    api = RecordingWDK()
    monkeypatch.setitem(served, "site", api)
    serve_the_site(monkeypatch, api)
    skip_the_tree_put(monkeypatch)

    async def _echo_parameters(*_args: Any, **kwargs: Any) -> ValidatedParams:
        params: dict[str, ParamValue] = dict(kwargs["stated"])
        return ValidatedParams(params=params, record_class="transcript")

    monkeypatch.setattr(stated_sides, "validate_parameters", _echo_parameters)

    async def _noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(commit, "persist_strategy_ast_to_conversation", _noop)
    return api


def _leaf(id_: str) -> StrategyStepNode:
    return StrategyStepNode(id=id_, search_name="geneById")


def _combine(id_: str, p: StrategyStepNode, s: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id=id_,
        search_name="__combine__",
        primary_input=p,
        secondary_input=s,
        operator=CombineOp.INTERSECT,
    )


def _seed_session(
    root: StrategyStepNode,
    wdk_step_ids: dict[str, int],
    step_words: StepWords | None = None,
) -> StrategyMutationContext:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Test", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(wdk_step_ids),
        wdk_strategy_id=42,
    )
    held_by_the_site(session)
    return StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=session,
        conversation_id=uuid4(),
        step_words=step_words or StepWords(),
    )


@pytest.mark.asyncio
async def test_delete_step_collapses_and_calls_wdk_delete(
    stub_api: RecordingWDK,
) -> None:
    a = _leaf("A")
    b = _leaf("B")
    c = _combine("C", a, b)
    deps = _seed_session(c, wdk_step_ids={"A": 100, "B": 200, "C": 300})

    result = await apply_and_commit(
        deps=deps,
        op=DeleteStepOp(step_id="A", resolution=DeleteResolution.COLLAPSE_COMBINE),
    )

    graph = deps.strategy_session.graph
    assert graph is not None
    assert sorted(graph.steps.keys()) == ["B"]
    assert sorted(result.dropped_step_ids) == ["A", "C"]

    deleted_ids = {
        c.kwargs["step_id"] for c in stub_api.calls if c.name == "delete_step"
    }
    assert deleted_ids == {100, 300}
    sync = deps.strategy_session.sync_state
    assert sync is not None
    assert "A" not in sync.wdk_step_ids
    assert "C" not in sync.wdk_step_ids


@pytest.mark.asyncio
async def test_update_step_meta_does_not_delete_wdk_steps(
    stub_api: RecordingWDK,
) -> None:
    a = _leaf("a")
    deps = _seed_session(a, wdk_step_ids={"a": 100})

    await apply_and_commit(
        deps=deps,
        op=UpdateStepMetaOp(step_id="a", display_name="renamed"),
    )

    assert deps.strategy_session.graph is not None
    assert deps.strategy_session.graph.steps["a"].display_name == "renamed"
    deletes = [c for c in stub_api.calls if c.name == "delete_step"]
    assert deletes == []


@pytest.mark.asyncio
async def test_a_refused_push_leaves_no_count_on_its_step(
    stub_api: RecordingWDK,
) -> None:
    """The step still runs the old search, so its stored count is not this edit's."""
    stub_api.refuse = WDKError("422 organism: Invalid value", status=422)
    deps = _seed_session(_leaf("a"), wdk_step_ids={"a": 100})
    session_sync = deps.strategy_session.sync_state
    assert session_sync is not None
    session_sync.step_counts["a"] = 1282

    result = await apply_and_commit(
        deps=deps,
        op=UpdateStepParamsOp(
            step_id="a", parameters={"organism": MultiPickValue(values=["PvP01"])}
        ),
    )

    assert [failure.step_id for failure in result.failures] == ["a"]
    assert result.failures[0].wdk_status == 422
    cited = citable_count(
        "a", counts=session_sync.step_counts, refused=session_sync.wdk_push_errors
    )
    assert (cited, sorted(session_sync.wdk_push_errors)) == (None, ["a"])


@pytest.mark.asyncio
async def test_a_commit_takes_the_words_the_spec_states(stub_api: RecordingWDK) -> None:
    del stub_api
    deps = _seed_session(
        _leaf("a"),
        wdk_step_ids={"a": 100},
        step_words=StepWords(criterion_texts={"a": "kinases"}),
    )

    await apply_and_commit(
        deps=deps, op=UpdateStepMetaOp(step_id="a", display_name="renamed")
    )

    assert deps.strategy_session.graph is not None
    assert deps.strategy_session.graph.words.criterion_texts == {"a": "kinases"}


@pytest.mark.asyncio
async def test_deleting_the_whole_strategy_deletes_the_steps_wdk_held(
    stub_api: RecordingWDK,
) -> None:
    deps = _seed_session(_leaf("a"), wdk_step_ids={"a": 100})

    await apply_and_commit(
        deps=deps,
        op=DeleteStepOp(step_id="a", resolution=DeleteResolution.DELETE_STRATEGY),
    )

    deleted = [c.kwargs["step_id"] for c in stub_api.calls if c.name == "delete_step"]
    assert deleted == [100]
    sync = deps.strategy_session.sync_state
    assert sync is not None
    assert sync.wdk_step_ids == {}
