"""Stand-ins for the catalog and WDK reads a strategy write makes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.domain.strategy import (
    StepSettings,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
    pushable_root_id,
    settings_of,
    walk,
)
from veupathdb.wdk import StrategyAPI, WDKSearch
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.strategy_description import strategy_description
from strategist.services.strategies import (
    commit_tree,
    live_counts,
    stated_sides,
)
from strategist.services.strategies._tree_write import (
    TreeTarget,
    WrittenTree,
    put_the_tree,
)
from strategist.services.strategies.commit_tree import CommitTarget, CommittedTree
from strategist.services.strategies.naming import name_for_the_push
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.recorded_searches import (
    serve_recorded_definitions,
    serve_recorded_record_types,
)
from strategist.tests._support.recording_wdk import RecordingWDK


async def accepts_every_value(*_args: Any, **kwargs: Any) -> ValidatedParams:
    """Answer a validation with the values as sent, in the catalog's shape."""
    return ValidatedParams(params=dict(kwargs["stated"]), record_class="transcript")


async def keeps_every_value(*_args: Any, **kwargs: Any) -> ValidatedParams:
    return ValidatedParams(params=dict(kwargs["stated"]))


def held_as(ast: StrategyAst) -> dict[str, StepSettings]:
    """WDK holds every step of ``ast`` as the tree states it."""
    roots = [ast.root, *ast.detached_roots]
    return {node.id: settings_of(node) for root in roots for node in walk(root)}


def stub_every_catalog_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """A write reaches no catalog and no WDK: every read answers its input."""
    monkeypatch.setattr(commit_tree, "validate_parameters", accepts_every_value)
    monkeypatch.setattr(stated_sides, "validate_parameters", accepts_every_value)
    list_every_search_under(monkeypatch, "transcript")


def serve_the_site(monkeypatch: pytest.MonkeyPatch, api: RecordingWDK) -> None:
    for module in (commit_tree, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(commit_tree, "validate_parameters", keeps_every_value)
    list_every_search_under(monkeypatch, "transcript")


async def commit_against(
    monkeypatch: pytest.MonkeyPatch,
    api: RecordingWDK,
    root: StrategyStepNode,
    *,
    before: StrategyStepNode | None,
    held: Mapping[str, int],
) -> tuple[CommittedTree, WDKSyncState]:
    serve_the_site(monkeypatch, api)
    sync_state = WDKSyncState(wdk_step_ids=dict(held))
    if before is not None:
        api.holds(flatten_tree(before), sync_state)
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
    """The real tree put, recording the strategy name each one carries."""

    pushed: list[str] = field(default_factory=list)

    async def put(
        self,
        api: StrategyAPI,
        site_id: str,
        root: StrategyStepNode,
        record_type: str,
        sync_state: WDKSyncState,
        target: TreeTarget,
    ) -> WrittenTree | None:
        self.pushed.append(target.name)
        return await put_the_tree(api, site_id, root, record_type, sync_state, target)
