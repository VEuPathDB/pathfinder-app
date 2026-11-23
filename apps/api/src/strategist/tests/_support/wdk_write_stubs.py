"""Stand-ins for the catalog and WDK reads a strategy write makes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.domain.strategy import (
    StepSettings,
    StrategyAst,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
    pushable_root_id,
    settings_of,
    walk,
)
from veupathdb.errors import WDKError
from veupathdb.wdk import StrategyAPI, WDKSearch, WDKStrategyDetails
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.strategy_description import strategy_description
from strategist.services.strategies import (
    commit_tree,
    live_counts,
    reconcile,
    stated_sides,
)
from strategist.services.strategies._tree_write import (
    StrategyLabels,
    TreeTarget,
    WrittenTree,
    put_the_strategy_labels,
)
from strategist.services.strategies.commit_tree import CommitTarget, CommittedTree
from strategist.services.strategies.naming import name_for_the_push
from strategist.services.strategies.sync import step_tree_is_current
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.recorded_searches import (
    serve_recorded_definitions,
    serve_recorded_record_types,
)


async def accepts_every_value(*_args: Any, **kwargs: Any) -> ValidatedParams:
    """Answer a validation with the values as sent, in the catalog's shape."""
    return ValidatedParams(params=dict(kwargs["stated"]), record_class="transcript")


async def keeps_every_value(*_args: Any, **kwargs: Any) -> ValidatedParams:
    return ValidatedParams(params=dict(kwargs["stated"]))


def held_as(ast: StrategyAst) -> dict[str, StepSettings]:
    """WDK holds every step of ``ast`` as the tree states it."""
    roots = [ast.root, *ast.detached_roots]
    return {node.id: settings_of(node) for root in roots for node in walk(root)}


def wdk_holds_the_tree_before_the_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    """WDK holds every mapped step as the tree before the edit states it."""

    async def _read(*_args: object) -> dict[str, StepSettings]:
        return {}

    def _before(
        old: StrategyAst | None,
        root: StrategyStepNode,
        steps: dict[str, StrategyStep],
        held: Mapping[str, StepSettings],
    ) -> dict[str, StepSettings]:
        reconcile.held_before_the_commit(old, root, steps, held)
        return {} if old is None else held_as(old)

    monkeypatch.setattr(commit_tree, "reconcile_sync_state_with_wdk", _read)
    monkeypatch.setattr(commit_tree, "held_before_the_commit", _before)


def stub_every_catalog_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """A write reaches no catalog and no WDK: every read answers its input."""
    monkeypatch.setattr(commit_tree, "validate_parameters", accepts_every_value)
    monkeypatch.setattr(stated_sides, "validate_parameters", accepts_every_value)
    list_every_search_under(monkeypatch, "transcript")
    wdk_holds_the_tree_before_the_edit(monkeypatch)


class NoStrategyRead:
    """A site that answers no read of the strategy, so a commit keeps its counts."""

    async def get_strategy(self, strategy_id: int) -> WDKStrategyDetails:
        msg = f"strategy {strategy_id} is not read here"
        raise WDKError(msg, status=404)


def serve_the_site(monkeypatch: pytest.MonkeyPatch, api: object) -> None:
    for module in (commit_tree, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(commit_tree, "validate_parameters", keeps_every_value)
    list_every_search_under(monkeypatch, "transcript")
    wdk_holds_the_tree_before_the_edit(monkeypatch)


def skip_the_tree_put(monkeypatch: pytest.MonkeyPatch, strategy_id: int = 42) -> None:

    async def _put(
        api: StrategyAPI,
        site_id: str,
        root: StrategyStepNode,
        record_type: str,
        sync_state: WDKSyncState,
        target: TreeTarget,
    ) -> WrittenTree | None:
        del site_id, record_type
        if step_tree_is_current(root, sync_state):
            labels = StrategyLabels(name=target.name, description=target.description)
            await put_the_strategy_labels(api, sync_state, labels)
            return None
        return WrittenTree(strategy_id=strategy_id, root_step_id=0, created=False)

    monkeypatch.setattr(commit_tree, "put_the_tree", _put)


async def commit_against(
    monkeypatch: pytest.MonkeyPatch,
    api: object,
    root: StrategyStepNode,
    *,
    before: StrategyStepNode | None,
    held: Mapping[str, int],
) -> tuple[CommittedTree, WDKSyncState]:
    serve_the_site(monkeypatch, api)
    skip_the_tree_put(monkeypatch)
    sync_state = WDKSyncState(wdk_step_ids=dict(held))
    committed = await commit_tree.commit_tree(
        site_id="plasmodb",
        steps=flatten_tree(root),
        root_id=root.id,
        old=None
        if before is None
        else StrategyAst(record_type="transcript", root=before),
        sync_state=sync_state,
        target=CommitTarget(name="test", description=""),
    )
    return committed, sync_state


async def put_the_graph(
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    site_id: str,
    *,
    user_prompt: str = "",
) -> CommittedTree:
    primary = graph.primary_root_id()
    root_id = None if primary is None else pushable_root_id(primary, graph.steps)
    assert root_id is not None
    committed = await commit_tree.commit_tree(
        site_id=site_id,
        steps=graph.steps,
        root_id=root_id,
        old=graph.to_strategy_ast(sync_state=sync_state),
        sync_state=sync_state,
        target=CommitTarget(
            name=name_for_the_push(graph, user_prompt),
            description=strategy_description(graph, root_id),
        ),
    )
    if committed.record_type is not None:
        graph.record_type = committed.record_type
    return committed


def validate_against(
    monkeypatch: pytest.MonkeyPatch, definitions: Sequence[WDKSearch]
) -> None:
    """A write validates its values against these recorded definitions, and
    finds each record type in plasmodb's recorded listing."""
    serve_recorded_record_types(monkeypatch)
    serve_recorded_definitions(monkeypatch, definitions)


@dataclass
class RecordedPushes:
    """A tree put that records the strategy name each one carries."""

    result: WrittenTree
    pushed: list[str] = field(default_factory=list)

    async def put(
        self,
        api: StrategyAPI,
        site_id: str,
        root: StrategyStepNode,
        record_type: str,
        sync_state: WDKSyncState,
        target: TreeTarget,
    ) -> WrittenTree:
        del api, site_id, root, record_type, sync_state
        self.pushed.append(target.name)
        return self.result


def landed_pushes(wdk_strategy_id: int, *, root_step_id: int = 0) -> RecordedPushes:
    """Puts that each land on ``wdk_strategy_id``."""
    return RecordedPushes(
        result=WrittenTree(
            strategy_id=wdk_strategy_id, root_step_id=root_step_id, created=False
        )
    )
