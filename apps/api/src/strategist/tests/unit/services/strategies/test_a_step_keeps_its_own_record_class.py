from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.build_outcome import StepPushFailure
from strategist.domain.strategy.operations import UpdateStepParamsOp
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.strategies import (
    _tree_write,
    commit_tree,
    stated_sides,
)
from strategist.services.strategies.commit_tree import CommittedTree
from strategist.services.strategies.save_substrategy import save_subtree_as_strategy
from strategist.services.strategies.stated_sides import canonical_batch
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.orthomcl_record_classes import (
    serve_orthomcl_record_classes,
)
from strategist.tests._support.wdk_write_stubs import put_the_graph
from strategist.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    install_stub_api,
)

_UNSENT = (
    "The site lists no record type for Unlisted, so Strategist cannot address "
    "the step and did not send it."
)


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    api = install_stub_api(monkeypatch)
    serve_orthomcl_record_classes(monkeypatch)

    async def _as_stated(*_args: object, **kwargs: Any) -> ValidatedParams:
        return ValidatedParams(params=dict(kwargs["stated"]))

    monkeypatch.setattr(commit_tree, "validate_parameters", _as_stated)
    return api


def _graph(*nodes: StrategyStepNode) -> StrategyGraph:
    graph = StrategyGraph("g1", "groups", "orthomcl")
    for node in nodes:
        graph.steps.update(flatten_tree(node))
    graph.recompute_roots()
    return graph


def _groups() -> StrategyStepNode:
    return StrategyStepNode(id="step_groups", search_name="GroupsByPhyleticPattern")


def _unlisted() -> StrategyStepNode:
    return StrategyStepNode(id="step_lost", search_name="Unlisted")


async def _commit_new(graph: StrategyGraph, sync_state: WDKSyncState) -> CommittedTree:
    (root_id,) = graph.roots
    return await commit_tree.commit_tree(
        site_id="orthomcl",
        steps=graph.steps,
        root_id=root_id,
        old=None,
        sync_state=sync_state,
        target=commit_tree.CommitTarget(name="groups", description=""),
    )


async def test_a_pushed_group_step_is_sent_under_the_group_class(
    api: StubAPI,
) -> None:
    committed = await _commit_new(_graph(_groups()), WDKSyncState())

    assert (
        committed.failures,
        [c.kwargs["record_type"] for c in api.named("create_step")],
    ) == ([], ["group"])


async def test_a_pushed_step_of_no_listed_class_is_not_sent(api: StubAPI) -> None:
    sync_state = WDKSyncState()

    committed = await _commit_new(_graph(_unlisted()), sync_state)

    assert (api.calls, [f.error for f in committed.failures]) == ([], [_UNSENT])
    assert sync_state.wdk_push_errors == {"step_lost": _UNSENT}


async def test_a_sync_reads_the_strategys_class_off_its_root(
    api: StubAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commit_tree, "put_the_tree", _tree_write.put_the_tree)
    graph = _graph(_groups())
    sync_state = WDKSyncState(wdk_step_ids={"step_groups": 227284900})
    api.holds(graph.steps, sync_state)

    await put_the_graph(graph, sync_state, "orthomcl")

    assert (graph.record_type, [c.name for c in api.calls]) == (
        "group",
        ["create_strategy"],
    )


async def test_an_unlisted_transform_root_is_a_named_refusal(
    api: StubAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commit_tree, "put_the_tree", _tree_write.put_the_tree)
    root = StrategyStepNode(
        id="step_lost", search_name="Unlisted", primary_input=_groups()
    )
    graph = _graph(root)
    graph.record_type = "group"
    sync_state = WDKSyncState(
        wdk_step_ids={"step_groups": 227284900, "step_lost": 227284901}
    )
    api.holds(graph.steps, sync_state)

    committed = await put_the_graph(graph, sync_state, "orthomcl")

    assert (committed.failures, api.calls) == (
        [StepPushFailure(step_id="step_lost", search_name="Unlisted", error=_UNSENT)],
        [],
    )
    assert graph.record_type == "group"


def _session(graph: StrategyGraph) -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    session.graph = graph
    return session


async def test_a_saved_group_subtree_is_pushed_and_saved_as_groups(
    api: StubAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = await save_subtree_as_strategy(
        session=_session(_graph(_groups())),
        site_id="orthomcl",
        source_step_id="step_groups",
        name="mammal groups",
    )

    assert (
        saved.record_type,
        [c.kwargs["record_type"] for c in api.named("create_step")],
    ) == ("group", ["group"])
    assert [saved.wdk_strategy_id] == list(api.wdk.strategies)


async def test_a_saved_subtree_of_no_listed_class_is_refused(
    api: StubAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValidationError) as refused:
        await save_subtree_as_strategy(
            session=_session(_graph(_unlisted())),
            site_id="orthomcl",
            source_step_id="step_lost",
            name="lost",
        )

    assert api.calls == []
    assert refused.value.detail is not None
    assert refused.value.detail.endswith(_UNSENT)


async def test_a_value_edit_is_read_under_the_class_of_its_step(
    api: StubAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    del api
    contexts: list[tuple[str, str]] = []

    async def _record(search: SearchContext, **_kwargs: object) -> ValidatedParams:
        contexts.append((search.search_name, search.record_type))
        return ValidatedParams(params={}, record_class="group")

    monkeypatch.setattr(stated_sides, "validate_parameters", _record)

    await canonical_batch(
        graph=_graph(_groups()),
        stated={},
        site_id="orthomcl",
        ops=[
            UpdateStepParamsOp(
                step_id="step_groups",
                parameters={"phyletic_expression": StringValue(value="MAMM>=1T")},
            )
        ],
    )

    assert contexts == [("GroupsByPhyleticPattern", "group")]
