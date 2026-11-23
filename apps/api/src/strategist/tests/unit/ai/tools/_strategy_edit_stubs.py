"""Stub WDK strategy API and tree builders for the strategy-edit tool tests."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb_mcp.catalog import ValidatedParams

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.graph.turn_records import TurnMarkers
from strategist.ai.tools.standalone._stated_values import StatedStepNode
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.strategies import (
    commit,
    commit_tree,
    live_counts,
    spec_build,
    stated_sides,
)
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import (
    list_every_search_under,
    recorded_searches,
)
from strategist.tests._support.recorded_searches import serve_stated_reads
from strategist.tests._support.recording_wdk import (
    RecordingWDK,
    held_by_the_site,
    served,
)
from strategist.tests._support.wdk_write_stubs import keeps_every_value


class StubAPI(RecordingWDK):
    def created_searches(self) -> list[str]:
        return [call.kwargs["search_name"] for call in self.named("create_step")]

    def combines(self) -> list[tuple[int, int, str]]:
        return [
            (
                call.kwargs["primary_step_id"],
                call.kwargs["secondary_step_id"],
                call.kwargs["boolean_operator"],
            )
            for call in self.named("create_combined_step")
        ]

    def search_configs(self) -> list[tuple[int, dict[str, str]]]:
        return [
            (call.kwargs["step_id"], call.kwargs["parameters"])
            for call in self.named("update_step_search_config")
        ]


async def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


async def _echo_parameters(*_args: Any, **kwargs: Any) -> ValidatedParams:
    """Accept every value, in the shape the catalog answers with."""
    params: dict[str, ParamValue] = dict(kwargs["stated"])
    return ValidatedParams(params=params, record_class="transcript")


def pin_validator(monkeypatch: pytest.MonkeyPatch, validator: Any) -> None:
    """Serve one parameter validator to every seam a write passes."""
    monkeypatch.setattr(stated_sides, "validate_parameters", validator)


def install_stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    """Serve one StubAPI to every strategy write path and stub the side effects."""
    api = StubAPI()
    monkeypatch.setitem(served, "site", api)
    for module in (commit_tree, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)
    for module in (commit, spec_build):
        monkeypatch.setattr(module, "persist_strategy_ast_to_conversation", _noop)
        monkeypatch.setattr(module, "defer_the_gene_set_refresh", _noop)
    pin_validator(monkeypatch, _echo_parameters)
    monkeypatch.setattr(commit_tree, "validate_parameters", keeps_every_value)
    list_every_search_under(monkeypatch, "transcript")
    serve_stated_reads(monkeypatch, list(recorded_searches().values()))
    return api


def leaf(
    id_: str,
    params: dict[str, Any] | None = None,
    *,
    search_name: str = "GenesByTaxon",
) -> StrategyStepNode:
    return StrategyStepNode(id=id_, search_name=search_name, parameters=params or {})


def stated_leaf(id_: str) -> StatedStepNode:
    """A GenesByTaxon step as the model states it, with no values."""
    return StatedStepNode(id=id_, search_name="GenesByTaxon")


def combine(
    id_: str,
    primary: StrategyStepNode,
    secondary: StrategyStepNode,
    op: CombineOp = CombineOp.INTERSECT,
) -> StrategyStepNode:
    return StrategyStepNode(
        id=id_,
        search_name="__combine__",
        primary_input=primary,
        secondary_input=secondary,
        operator=op,
    )


def session_with(
    root: StrategyStepNode, wdk_step_ids: dict[str, int]
) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Test", site_id="plasmodb")
    graph.record_type = "transcript"
    stack = [root]
    while stack:
        node = stack.pop()
        graph.steps.update(flatten_tree(node))
        if node.primary_input is not None:
            stack.append(node.primary_input)
        if node.secondary_input is not None:
            stack.append(node.secondary_input)
    graph.recompute_roots()
    session.graph = graph
    sync_state = WDKSyncState(
        wdk_step_ids=dict(wdk_step_ids),
        wdk_strategy_id=42 if wdk_step_ids else None,
    )
    session.sync_state = sync_state
    held_by_the_site(session)
    return session


def seed(root: StrategyStepNode, wdk_step_ids: dict[str, int]) -> AgentDeps:
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(root, wdk_step_ids),
        conversation_id=uuid4(),
        turn_markers=TurnMarkers(),
    )


def ctx(deps: AgentDeps, *, tool_call_id: str | None = None) -> RunContext[AgentDeps]:
    return RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        messages=[],
        tool_call_id=tool_call_id,
    )
