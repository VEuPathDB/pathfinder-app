from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKIdentifier, WDKStepTree
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.domain.strategy.build_outcome import StepPushFailure
from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import save_substrategy, stated_sides
from pathfinder.services.strategies.save_substrategy import save_subtree_as_strategy
from pathfinder.services.strategies.stated_sides import canonical_batch
from pathfinder.services.strategies.step_push_planner import (
    CreateAction,
    StepPushPlan,
)
from pathfinder.services.strategies.step_wdk_push import push_steps_with_plan
from pathfinder.services.strategies.sync import (
    UnclassedRootError,
    sync_strategy_for_site,
)
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.orthomcl_record_classes import (
    serve_orthomcl_record_classes,
)
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    install_stub_api,
)

_UNSENT = (
    "The site lists no record type for Unlisted, so PathFinder cannot address "
    "the step and did not send it."
)


@dataclass
class _Library:
    saved: list[WDKStepTree] = field(default_factory=list)

    async def create_strategy(
        self,
        step_tree: WDKStepTree,
        name: str,
        description: str | None = None,
        is_saved: bool = False,
    ) -> WDKIdentifier:
        del name, description, is_saved
        self.saved.append(step_tree)
        return WDKIdentifier(id=330534203)


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    api = install_stub_api(monkeypatch)
    serve_orthomcl_record_classes(monkeypatch)
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


def _create(step_id: str) -> StepPushPlan:
    return StepPushPlan(step_id=step_id, action=CreateAction(), reason="new")


async def test_a_pushed_group_step_is_sent_under_the_group_class(
    api: StubAPI,
) -> None:
    graph = _graph(_groups())

    outcome = await push_steps_with_plan(
        graph, WDKSyncState(), "orthomcl", [_create("step_groups")]
    )

    assert (outcome.failed, [c.kwargs["record_type"] for c in api.calls]) == (
        [],
        ["group"],
    )


async def test_a_pushed_step_of_no_listed_class_is_not_sent(api: StubAPI) -> None:
    sync_state = WDKSyncState()

    outcome = await push_steps_with_plan(
        _graph(_unlisted()), sync_state, "orthomcl", [_create("step_lost")]
    )

    assert (api.calls, [f.error for f in outcome.failures]) == ([], [_UNSENT])
    assert sync_state.wdk_push_errors == {"step_lost": _UNSENT}


async def test_a_sync_reads_the_strategys_class_off_its_root(api: StubAPI) -> None:
    graph = _graph(_groups())
    sync_state = WDKSyncState(wdk_step_ids={"step_groups": 227284900})

    await sync_strategy_for_site(graph=graph, sync_state=sync_state, site_id="orthomcl")

    assert (graph.record_type, [c.name for c in api.calls]) == (
        "group",
        ["create_strategy"],
    )


async def test_an_unlisted_transform_root_is_a_named_refusal(api: StubAPI) -> None:
    root = StrategyStepNode(
        id="step_lost", search_name="Unlisted", primary_input=_groups()
    )
    graph = _graph(root)
    graph.record_type = "group"
    sync_state = WDKSyncState(
        wdk_step_ids={"step_groups": 227284900, "step_lost": 227284901}
    )

    with pytest.raises(UnclassedRootError) as refused:
        await sync_strategy_for_site(
            graph=graph, sync_state=sync_state, site_id="orthomcl"
        )

    assert (refused.value.failure, refused.value.detail, api.calls) == (
        StepPushFailure(step_id="step_lost", search_name="Unlisted", error=_UNSENT),
        _UNSENT,
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
    library = _Library()
    monkeypatch.setattr(save_substrategy, "get_strategy_api", lambda _site: library)

    saved = await save_subtree_as_strategy(
        session=_session(_graph(_groups())),
        site_id="orthomcl",
        source_step_id="step_groups",
        name="mammal groups",
    )

    assert (saved.record_type, [c.kwargs["record_type"] for c in api.calls]) == (
        "group",
        ["group"],
    )
    assert len(library.saved) == 1


async def test_a_saved_subtree_of_no_listed_class_is_refused(
    api: StubAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _Library()
    monkeypatch.setattr(save_substrategy, "get_strategy_api", lambda _site: library)

    with pytest.raises(ValidationError) as refused:
        await save_subtree_as_strategy(
            session=_session(_graph(_unlisted())),
            site_id="orthomcl",
            source_step_id="step_lost",
            name="lost",
        )

    assert (api.calls, library.saved) == ([], [])
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
