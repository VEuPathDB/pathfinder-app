"""``durable_tool``: what it creates, what it defers, what it refuses, and the
identity protocol it needs from the caller's deps."""

from __future__ import annotations

import json
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from pydantic_ai.exceptions import CallDeferred

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools import durable as durable_mod
from pathfinder.ai.tools.durable import DurableIdentity, durable_tool
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests.unit.ai.tools.conftest import lead_deps, turn_runtime

_TASK_ID = UUID("00000000-0000-0000-0000-000000000001")


class _FakeRepo:
    created: ClassVar[list[dict[str, Any]]] = []


async def _fake_create_background_task(
    *,
    conversation_id: UUID,
    user_id: UUID,
    tool_name: str,
    args: dict[str, Any],
    tool_call_id: str,
    estimated_duration_seconds: int,
) -> UUID:
    _FakeRepo.created.append(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "tool_name": tool_name,
            "args": args,
            "tool_call_id": tool_call_id,
            "estimated_duration_seconds": estimated_duration_seconds,
        }
    )
    return _TASK_ID


class _FakeTask:
    deferred: ClassVar[list[dict[str, Any]]] = []

    async def defer_async(self, **kwargs: Any) -> int:
        _FakeTask.deferred.append(kwargs)
        return 42


class _FakeAppCtx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeApp:
    def __init__(self) -> None:
        self.configured: list[dict[str, str]] = []

    def configure_task(self, *, name: str, queue: str, lock: str) -> _FakeTask:
        self.configured.append({"name": name, "queue": queue, "lock": lock})
        return _FakeTask()

    def open_async(self) -> _FakeAppCtx:
        return _FakeAppCtx()


class _RunCtx:
    def __init__(self, deps: AgentDeps, tool_call_id: str = "call_stub") -> None:
        self.deps = deps
        self.tool_call_id = tool_call_id


class _Writer:
    """Stands in for the langgraph stream writer."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


def _pin_seams(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeApp, _Writer]:
    _FakeRepo.created.clear()
    _FakeTask.deferred.clear()
    monkeypatch.setattr(
        durable_mod, "create_background_task", _fake_create_background_task
    )
    app = _FakeApp()
    monkeypatch.setattr(durable_mod, "procrastinate_app", app)
    writer = _Writer()
    monkeypatch.setattr(durable_mod, "get_stream_writer", lambda: writer)
    return app, writer


def _fresh_deps(conversation_id: UUID | None, user_id: UUID | None) -> AgentDeps:
    return AgentDeps(
        site_id="plasmodb",
        user_id=user_id,
        strategy_session=StrategySession(site_id="plasmodb"),
        conversation_id=conversation_id,
    )


async def test_durable_tool_submits_job_and_defers_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, writer = _pin_seams(monkeypatch)

    @durable_tool(tool_name="stub_tool", estimated_duration_seconds=60)
    async def stub_tool(ctx: _RunCtx, x: int) -> dict[str, Any]:
        del ctx, x
        msg = "agent-side body must not execute"
        raise AssertionError(msg)

    conversation_id = uuid4()
    user_id = uuid4()
    ctx = _RunCtx(deps=_fresh_deps(conversation_id, user_id))

    with pytest.raises(CallDeferred):
        await stub_tool(ctx, x=5)

    assert [p["chunk"] for p in writer.payloads] == [
        {
            "type": "data-background-task-started",
            "data": {
                "taskId": str(_TASK_ID),
                "toolName": "stub_tool",
                "estimatedDurationSeconds": 60,
            },
        },
    ]
    deferral = ctx.deps.durable_deferrals["call_stub"]
    assert deferral.task_id == _TASK_ID
    assert deferral.tool_name == "stub_tool"

    assert len(_FakeRepo.created) == 1
    created = _FakeRepo.created[0]
    assert created["tool_name"] == "stub_tool"
    assert created["conversation_id"] == conversation_id
    assert created["user_id"] == user_id
    assert created["estimated_duration_seconds"] == 60
    assert created["tool_call_id"] == "call_stub"
    assert created["args"] == {"args": [], "kwargs": {"x": 5}}

    assert len(_FakeTask.deferred) == 1
    deferred = _FakeTask.deferred[0]
    assert deferred["task_id"] == str(_TASK_ID)
    assert deferred["thread_id"] == str(conversation_id)
    assert deferred["args"] == {"args": [], "kwargs": {"x": 5}}

    assert app.configured == [
        {
            "name": "durable:stub_tool",
            "queue": "verification",
            "lock": str(conversation_id),
        },
    ]


class _SampleTarget(BaseModel):
    name: str
    thresholds: list[float]


async def test_durable_tool_serializes_pydantic_kwargs_to_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Procrastinate persists job args with ``json.dumps``, so a BaseModel
    kwarg must be dumped before the defer."""
    _pin_seams(monkeypatch)

    @durable_tool(tool_name="stub", estimated_duration_seconds=10)
    async def stub(ctx: _RunCtx, target: _SampleTarget) -> dict[str, Any]:
        del ctx, target
        msg = "must not execute"
        raise AssertionError(msg)

    ctx = _RunCtx(deps=_fresh_deps(conversation_id=uuid4(), user_id=uuid4()))

    with pytest.raises(CallDeferred):
        await stub(ctx, target=_SampleTarget(name="x", thresholds=[0.1, 0.05]))

    assert len(_FakeTask.deferred) == 1
    round_tripped = json.loads(json.dumps(_FakeTask.deferred[0]["args"]))
    assert round_tripped["kwargs"]["target"] == {
        "name": "x",
        "thresholds": [0.1, 0.05],
    }
    assert json.loads(json.dumps(_FakeRepo.created[0]["args"])) == round_tripped


@pytest.mark.parametrize(
    ("conversation_id", "user_id", "missing"),
    [
        (None, uuid4(), "conversation_id"),
        (uuid4(), None, "user_id"),
    ],
    ids=["no-conversation", "no-user"],
)
async def test_durable_tool_raises_when_the_identity_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    conversation_id: UUID | None,
    user_id: UUID | None,
    missing: str,
) -> None:
    _pin_seams(monkeypatch)

    @durable_tool(tool_name="stub_tool", estimated_duration_seconds=60)
    async def stub_tool(ctx: _RunCtx) -> dict[str, Any]:
        del ctx
        msg = "agent-side body must not execute"
        raise AssertionError(msg)

    ctx = _RunCtx(deps=_fresh_deps(conversation_id, user_id))
    with pytest.raises(RuntimeError, match=missing):
        await stub_tool(ctx)

    assert _FakeRepo.created == []
    assert _FakeTask.deferred == []


@pytest.fixture
def turn_deps() -> LeadDeps:
    return lead_deps(turn_runtime())


class TestTheIdentityProtocol:
    """``durable_tool`` needs an identity, not the whole of AgentDeps."""

    def test_lead_deps_conversation_id_comes_from_the_turn_state(
        self, turn_deps: LeadDeps
    ) -> None:
        assert turn_deps.conversation_id == turn_deps.state.conversation_id

    def test_lead_deps_user_id_comes_from_the_turn_context(
        self, turn_deps: LeadDeps
    ) -> None:
        assert turn_deps.user_id == turn_deps.runtime.user_id

    def test_lead_deps_user_id_is_not_the_state_copy(self, turn_deps: LeadDeps) -> None:
        """The turn context is the account the worker acts as."""
        assert turn_deps.runtime.user_id != turn_deps.state.user_id
        assert turn_deps.user_id != turn_deps.state.user_id

    def test_lead_deps_satisfies_the_durable_identity_protocol(
        self, turn_deps: LeadDeps
    ) -> None:
        identity: DurableIdentity = turn_deps
        assert (identity.conversation_id, identity.user_id) == (
            turn_deps.state.conversation_id,
            turn_deps.runtime.user_id,
        )

    def test_agent_deps_satisfies_the_durable_identity_protocol(self) -> None:
        conversation_id = uuid4()
        user_id = uuid4()
        identity: DurableIdentity = AgentDeps(
            site_id="plasmodb",
            user_id=user_id,
            conversation_id=conversation_id,
            strategy_session=StrategySession(site_id="plasmodb"),
        )
        assert (identity.conversation_id, identity.user_id) == (
            conversation_id,
            user_id,
        )
