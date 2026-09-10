"""An edit turn changes the steps it names and leaves the rest alone.

The filed run rebuilt every step, so four WDK step ids changed and a hand
edit was reverted. The edit dispatch pushes operations instead.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from pydantic_ai.exceptions import ModelRetry
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters.values import MultiPickValue, NumberValue
from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from veupathdb.domain.strategy.graph_model import flatten_tree
from veupathdb.domain.strategy.operational_spec import OperationalSpec
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.session import StrategyGraph, StrategySession
from veupathdb.domain.strategy.spec_diff import CriterionChange
from veupathdb.domain.strategy.strategy_ast import StrategyAst
from veupathdb.wdk.wdk_models import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
    WDKStepTree,
    WDKStrategyDetails,
)

from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, frame_dispatch
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.spec_hydration import spec_from_ast
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies import commit, live_counts, step_wdk_push, sync
from pathfinder.services.strategies.sync_state import WDKSyncState

WDK_IDS = {"step_text": 100, "step_go": 200, "step_join": 300}


@dataclass
class _Call:
    name: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class _RecordingAPI:
    """Records every WDK write the edit makes."""

    calls: list[_Call] = field(default_factory=list)
    next_id: int = 9000

    def named(self, name: str) -> list[_Call]:
        return [c for c in self.calls if c.name == name]

    def _alloc(self) -> int:
        self.next_id += 1
        return self.next_id

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        self.calls.append(_Call("delete_step", {"step_id": step_id}))

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(_Call("create_step", {"search_name": spec.search_name}))
        del record_type
        return WDKIdentifier(id=self._alloc())

    async def create_combined_step(
        self, spec: CombinedStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del user_id, record_type
        self.calls.append(
            _Call("create_combined_step", {"primary": spec.primary_step_id})
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
        del user_id, record_type
        self.calls.append(
            _Call(
                "create_transform_step",
                {"search_name": spec.search_name, "input_step_id": input_step_id},
            )
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
        del user_id, record_type
        self.calls.append(
            _Call(
                "update_step_search_config",
                {
                    "step_id": step_id,
                    "search_name": search_name,
                    "parameters": dict(search_config.parameters),
                },
            )
        )

    async def update_step_properties(
        self, step_id: int, spec: PatchStepSpec, *, user_id: str | None = None
    ) -> None:
        del user_id, spec
        self.calls.append(_Call("update_step_properties", {"step_id": step_id}))

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByText",
            search_config=WDKSearchConfig(parameters={}),
        )

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        self.calls.append(_Call("get_strategy", {"strategy_id": strategy_id}))
        return WDKStrategyDetails(
            strategy_id=strategy_id,
            name="Test strategy",
            root_step_id=300,
            step_tree=WDKStepTree(step_id=300),
            steps={
                "100": WDKStep(
                    id=100,
                    search_name="GenesByText",
                    search_config=WDKSearchConfig(parameters={}),
                    estimated_size=2122,
                ),
                "200": WDKStep(
                    id=200,
                    search_name="GenesByGoTerm",
                    search_config=WDKSearchConfig(parameters={}),
                    estimated_size=45,
                ),
                "300": WDKStep(
                    id=300,
                    search_name="boolean",
                    search_config=WDKSearchConfig(parameters={}),
                    estimated_size=7,
                ),
            },
        )


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> _RecordingAPI:
    api = _RecordingAPI()
    for module in (commit, step_wdk_push, sync, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)

    async def _noop_validate(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _noop_validate)

    async def _noop_reconcile(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", _noop_reconcile)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _chunk: None)
    return api


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


def _root() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_text",
            search_name="GenesByText",
            display_name="protease text",
            parameters={
                "text_expression": MultiPickValue(values=["protease"]),
                "organism": MultiPickValue(values=["Plasmodium"]),
            },
        ),
        secondary_input=StrategyStepNode(
            id="step_go",
            search_name="GenesByGoTerm",
            display_name="proteolysis GO",
            parameters={
                "organism": MultiPickValue(values=["Plasmodium"]),
                "min_evidence": NumberValue(value=2),
            },
        ),
    )


async def _seed(db_session: AsyncSession, user: User) -> UUID:
    ast = StrategyAst(
        record_type="transcript", root=_root(), wdk_step_ids=dict(WDK_IDS)
    )
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        id=uuid4(),
        user_id=user.id,
        site_id="plasmodb",
        name="Test strategy",
    )
    db_session.add(conv)
    await db_session.flush()
    db_session.add(
        ConversationStrategy(
            conversation_id=conv.id,
            wdk_strategy_id=555,
            strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
    )
    await db_session.commit()
    return conv.id


def _graph(conv_id: UUID) -> StrategyGraph:
    graph = StrategyGraph(
        graph_id=str(conv_id), name="Test strategy", site_id="plasmodb"
    )
    graph.record_type = "transcript"
    graph.steps = flatten_tree(_root())
    graph.recompute_roots()
    graph.last_step_id = "step_join"
    return graph


def _before() -> OperationalSpec:
    return spec_from_ast(
        StrategyAst(record_type="transcript", root=_root()),
        goal="proteases in Plasmodium",
    )


def _deps(conv_id: UUID, session_maker: Any) -> LeadDeps:
    session = StrategySession(site_id="plasmodb")
    session.graph = _graph(conv_id)
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(WDK_IDS), wdk_strategy_id=555, step_counts={}
    )
    before = _before()
    state = PipelineState(
        conversation_id=conv_id,
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="use P. vivax for the GO criterion, keep the rest",
        domain=StrategyDomainState(
            operational_spec=before.model_copy(deep=True),
            spec_before_turn=before.model_copy(deep=True),
        ),
    )
    runtime = Context(
        site_id="plasmodb",
        user_id=state.user_id,
        strategy_session=session,
        db_session_factory=session_maker,
        cancel_event=asyncio.Event(),
    )
    return LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])


def _organism_swap(before: OperationalSpec) -> OperationalSpec:
    after = before.model_copy(deep=True)
    for criterion in after.criteria:
        if criterion.id == "step_go":
            criterion.resolved_params["organism"] = MultiPickValue(
                values=["Plasmodium vivax P01"]
            )
    return after


def _stub_frame(
    monkeypatch: pytest.MonkeyPatch,
    after: OperationalSpec,
    changes: list[CriterionChange],
) -> None:
    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft = after.model_copy(deep=True)
        return FrameResult(
            disposition="spec_ready", summary="organism swapped", changes=changes
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)


_SWAP_CHANGES = [
    CriterionChange(criterion_id="step_text", disposition="kept"),
    CriterionChange(
        criterion_id="step_go",
        disposition="changed",
        changed_params={"organism": "Plasmodium vivax P01"},
    ),
]


async def test_edit_preserves_step_ids(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _RecordingAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conv_id = await _seed(db_session, seed_user)
    deps = _deps(conv_id, session_maker)
    _stub_frame(monkeypatch, _organism_swap(_before()), _SWAP_CHANGES)

    result = await run_edit(deps=deps, parent_tool_call_id="t1", reason="swap organism")

    assert isinstance(result, EditDelta)
    patches = stub_api.named("update_step_search_config")
    assert [c.kwargs["step_id"] for c in patches] == [200]
    assert stub_api.named("create_step") == []
    assert stub_api.named("create_combined_step") == []
    assert stub_api.named("delete_step") == []
    sync_state = deps.runtime.strategy_session.sync_state
    assert sync_state is not None
    assert sync_state.wdk_step_ids == WDK_IDS


async def test_the_untouched_criterion_keeps_its_values(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _RecordingAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del stub_api
    conv_id = await _seed(db_session, seed_user)
    deps = _deps(conv_id, session_maker)
    _stub_frame(monkeypatch, _organism_swap(_before()), _SWAP_CHANGES)

    result = await run_edit(deps=deps, parent_tool_call_id="t1", reason="swap organism")

    assert isinstance(result, EditDelta)
    assert result.diff.render() == "kept 1, changed 1, added 0, dropped 0"
    assert result.preserved_step_ids == ["step_text"]
    graph = deps.runtime.strategy_session.get_graph(None)
    assert graph is not None
    untouched = _before().criteria[0]
    assert untouched.id == "step_text"
    assert graph.steps["step_text"].parameters == untouched.resolved_params


async def test_edit_does_not_re_put_the_step_tree_when_topology_is_unchanged(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _RecordingAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _record_sync(**kwargs: Any) -> None:
        del kwargs
        calls.append("sync")

    monkeypatch.setattr(commit, "sync_strategy_for_site", _record_sync)
    conv_id = await _seed(db_session, seed_user)
    deps = _deps(conv_id, session_maker)
    _stub_frame(monkeypatch, _organism_swap(_before()), _SWAP_CHANGES)

    await run_edit(deps=deps, parent_tool_call_id="t1", reason="swap organism")

    assert calls == []
    assert stub_api.named("create_step") == []


async def test_edit_refuses_on_a_changed_revision(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _RecordingAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conv_id = await _seed(db_session, seed_user)
    deps = _deps(conv_id, session_maker)
    after = _organism_swap(_before())

    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft = after.model_copy(deep=True)
        # The researcher saves an editor change while the pass is running.
        graph = deps.runtime.strategy_session.get_graph(None)
        assert graph is not None
        graph.steps["step_text"].parameters["organism"] = MultiPickValue(
            values=["Plasmodium falciparum 3D7"]
        )
        return FrameResult(
            disposition="spec_ready", summary="swapped", changes=_SWAP_CHANGES
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)

    with pytest.raises(ModelRetry) as excinfo:
        await run_edit(deps=deps, parent_tool_call_id="t1", reason="swap organism")

    assert "changed while this edit was being planned" in str(excinfo.value)
    assert stub_api.named("update_step_search_config") == []
    # The refusal puts back the spec the turn found, so a retry still sees the
    # criteria it has to preserve.
    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert {c.id for c in spec.criteria} == {"step_text", "step_go"}
    assert spec.criteria[1].resolved_params["organism"] == MultiPickValue(
        values=["Plasmodium"]
    )
