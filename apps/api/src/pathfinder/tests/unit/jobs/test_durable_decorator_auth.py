"""@durable_tool propagates veupathdb_auth_token_ctx into the deferred payload
so the worker-side run_durable_task can restore it before the impl runs."""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from pydantic_ai.exceptions import CallDeferred
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy.session import StrategySession

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools import durable
from pathfinder.ai.tools.durable import durable_tool


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
        },
    )
    return UUID("00000000-0000-0000-0000-000000000001")


class _FakeTask:
    deferred: ClassVar[list[dict[str, Any]]] = []

    async def defer_async(self, **kwargs: Any) -> int:
        _FakeTask.deferred.append(kwargs)
        return 42


class _FakeApp:
    def configure_task(self, *, name: str, queue: str, lock: str) -> _FakeTask:
        del name, queue, lock
        return _FakeTask()


class _RunCtx:
    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps
        self.tool_call_id = "call_stub"


def _fresh_deps() -> AgentDeps:
    return AgentDeps(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        conversation_id=uuid4(),
    )


@pytest.fixture
def patch_durable_infra(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeRepo.created.clear()
    _FakeTask.deferred.clear()
    monkeypatch.setattr(durable, "get_stream_writer", lambda: lambda _p: None)
    monkeypatch.setattr(
        durable,
        "create_background_task",
        _fake_create_background_task,
    )
    monkeypatch.setattr(durable, "procrastinate_app", _FakeApp())


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_durable_infra")
async def test_durable_tool_forwards_token_from_ctxvar() -> None:
    @durable_tool(tool_name="stub", estimated_duration_seconds=5)
    async def stub(ctx: _RunCtx) -> dict[str, Any]:
        del ctx
        msg = "must not run"
        raise AssertionError(msg)

    token_value = "user-cookie-propagated"
    reset = veupathdb_auth_token_ctx.set(token_value)
    try:
        with pytest.raises(CallDeferred):
            await stub(_RunCtx(deps=_fresh_deps()))
    finally:
        veupathdb_auth_token_ctx.reset(reset)

    assert len(_FakeTask.deferred) == 1
    deferred = _FakeTask.deferred[0]
    assert deferred["veupathdb_auth_token"] == token_value


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_durable_infra")
async def test_durable_tool_forwards_none_when_ctxvar_unset() -> None:
    @durable_tool(tool_name="stub", estimated_duration_seconds=5)
    async def stub(ctx: _RunCtx) -> dict[str, Any]:
        del ctx
        msg = "must not run"
        raise AssertionError(msg)

    assert veupathdb_auth_token_ctx.get() is None
    with pytest.raises(CallDeferred):
        await stub(_RunCtx(deps=_fresh_deps()))

    assert len(_FakeTask.deferred) == 1
    assert _FakeTask.deferred[0]["veupathdb_auth_token"] is None
