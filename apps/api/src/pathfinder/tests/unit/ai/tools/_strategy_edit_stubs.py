"""Stub WDK strategy API and tree builders for the strategy-edit tool tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    StepsMixin,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import _spec_edit_checks, strategy_edits
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import commit, step_wdk_push, sync
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState

_STEP_PUSHES = frozenset(
    {
        "create_step",
        "create_combined_step",
        "create_transform_step",
        "update_step_search_config",
        "update_step_properties",
    }
)


@dataclass
class Call:
    name: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class StubAPI:
    """Records every WDK strategy write and hands back fresh step ids."""

    calls: list[Call] = field(default_factory=list)
    next_id: int = 9000
    refuse: Exception | None = None
    """Raised by every step push, so a test can play WDK turning an edit down."""

    def _record(self, name: str, **kwargs: Any) -> None:
        self.calls.append(Call(name, kwargs))
        if self.refuse is not None and name in _STEP_PUSHES:
            raise self.refuse

    def _alloc(self) -> int:
        self.next_id += 1
        return self.next_id

    def step_ids(self, name: str) -> set[int]:
        return {call.kwargs["step_id"] for call in self.calls if call.name == name}

    def named(self, name: str) -> list[Call]:
        return [call for call in self.calls if call.name == name]

    delete_orphaned_steps = StepsMixin.delete_orphaned_steps

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        self._record("delete_step", step_id=step_id)

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del user_id
        self._record(
            "create_step", search_name=spec.search_name, record_type=record_type
        )
        return WDKIdentifier(id=self._alloc())

    async def create_combined_step(
        self, spec: CombinedStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del user_id
        self._record(
            "create_combined_step",
            primary_step_id=spec.primary_step_id,
            secondary_step_id=spec.secondary_step_id,
            boolean_operator=spec.boolean_operator.value,
            record_type=record_type,
        )
        return WDKIdentifier(id=self._alloc())

    async def create_transform_step(
        self,
        spec: NewStepSpec,
        input_step_id: int,
        record_type: str = "transcript",
        *,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id
        self._record(
            "create_transform_step",
            search_name=spec.search_name,
            input_step_id=input_step_id,
            record_type=record_type,
        )
        return WDKIdentifier(id=self._alloc())

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
    ) -> None:
        del user_id
        self._record(
            "update_step_search_config",
            step_id=step_id,
            search_name=search_name,
            record_type=record_type,
            parameters=dict(search_config.parameters),
        )

    async def update_step_properties(
        self, step_id: int, spec: PatchStepSpec, *, user_id: str | None = None
    ) -> None:
        del user_id
        self._record("update_step_properties", step_id=step_id, spec=spec)

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByTaxon",
            search_config=WDKSearchConfig(parameters={}),
        )


async def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


async def _echo_parameters(*_args: Any, **kwargs: Any) -> ValidatedParams:
    """Accept every value, in the shape the catalog answers with."""
    params: dict[str, ParamValue] = dict(kwargs.get("parameters") or {})
    return ValidatedParams(params=params, record_class="transcript")


async def _no_plan_params(*_args: Any, **_kwargs: Any) -> set[str]:
    return set()


async def _fake_sync(**_kwargs: Any) -> SyncResult:
    return SyncResult(
        wdk_strategy_id=42,
        wdk_url="http://example",
        root_step_id=0,
        counts={},
        root_count=None,
        zero_step_ids=[],
        step_count=0,
    )


def pin_validator(monkeypatch: pytest.MonkeyPatch, validator: Any) -> None:
    """Serve one parameter validator to both seams a leaf patch calls."""
    for module in (strategy_edits, _spec_edit_checks):
        monkeypatch.setattr(module, "validate_parameters", validator)


def install_stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    """Serve one StubAPI to every strategy write path and stub the side effects."""
    api = StubAPI()
    for module in (commit, step_wdk_push, sync):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", _noop)
    monkeypatch.setattr(commit, "sync_strategy_for_site", _fake_sync)
    monkeypatch.setattr(commit, "persist_strategy_ast_to_conversation", _noop)
    pin_validator(monkeypatch, _echo_parameters)
    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _no_plan_params)
    return api


def leaf(id_: str, params: dict[str, Any] | None = None) -> StrategyStepNode:
    return StrategyStepNode(id=id_, search_name="GenesByTaxon", parameters=params or {})


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
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(wdk_step_ids), wdk_strategy_id=42
    )
    return session


def seed(root: StrategyStepNode, wdk_step_ids: dict[str, int]) -> AgentDeps:
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(root, wdk_step_ids),
        conversation_id=uuid4(),
    )


def ctx(deps: AgentDeps, *, tool_call_id: str | None = None) -> RunContext[AgentDeps]:
    return RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        messages=[],
        tool_call_id=tool_call_id,
    )
