"""The four durable tools this application declares, and the seam they ride.

One declaration binds the decorator, the procrastinate job and the worker body
to one name, so a registration that names another tool is refused.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.tasks import decorator
from assistant_core.tasks.declaration import (
    DurableTool,
    UndeclaredDurableToolError,
    declared_durable_tools,
    durable_impl,
    register_durable_impl,
)
from assistant_core.tasks.job_context import (
    install_durable_job_context,
    reset_durable_job_context,
)
from assistant_core.tasks.names import DURABLE_TASK_QUEUE
from assistant_core.tasks.payloads import DurableTaskPayload
from pydantic_ai.exceptions import CallDeferred
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy.session import StrategySession

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.eda_compute import EDA_COMPUTE
from pathfinder.ai.tools.standalone.experiment import CONTROL_TESTS
from pathfinder.ai.tools.standalone.optimization import PARAMETER_SWEEP
from pathfinder.ai.tools.standalone.workbench import GENESET_ENRICHMENT
from pathfinder.jobs.impls import register_all_tools
from pathfinder.jobs.job_context import WdkJobContext, WdkJobState

_TASK_ID = UUID("00000000-0000-0000-0000-000000000001")
_TOKEN = "wdk-session-cookie"


class _Job:
    def __init__(self, deferred: list[dict[str, Any]]) -> None:
        self._deferred = deferred

    async def defer_async(self, **kwargs: Any) -> int:
        self._deferred.append(kwargs)
        return 7


class _App:
    def __init__(self, deferred: list[dict[str, Any]]) -> None:
        self.deferred = deferred
        self.configured: list[dict[str, str]] = []

    def configure_task(self, *, name: str, queue: str, lock: str) -> _Job:
        self.configured.append({"name": name, "queue": queue, "lock": lock})
        return _Job(self.deferred)


class _Ctx:
    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps
        self.tool_call_id = "call_1"


def _deps() -> AgentDeps:
    return AgentDeps(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        conversation_id=uuid4(),
    )


@pytest.fixture
def dispatch(monkeypatch: pytest.MonkeyPatch) -> Iterator[_App]:
    app = _App([])

    async def _create(**kwargs: Any) -> UUID:
        del kwargs
        return _TASK_ID

    monkeypatch.setattr(decorator, "create_background_task", _create)
    monkeypatch.setattr(decorator, "task_app", lambda: app)
    monkeypatch.setattr(decorator, "get_stream_writer", lambda: lambda _p: None)
    install_durable_job_context(WdkJobContext())
    try:
        yield app
    finally:
        reset_durable_job_context()


def test_the_four_tools_are_declared_with_their_budgets() -> None:
    """The declared name, queue and budget are what the worker consumes."""
    declared = {tool.tool_name: tool for tool in declared_durable_tools()}

    assert declared["geneset_enrichment"] is GENESET_ENRICHMENT
    assert declared["run_control_tests_on_step"] is CONTROL_TESTS
    assert declared["optimize_search_parameters"] is PARAMETER_SWEEP
    assert declared["run_eda_compute"] is EDA_COMPUTE
    assert GENESET_ENRICHMENT.estimated_duration_seconds == 120
    assert CONTROL_TESTS.estimated_duration_seconds == 180
    assert PARAMETER_SWEEP.estimated_duration_seconds == 900
    assert CONTROL_TESTS.job_name == "durable:run_control_tests_on_step"


def test_every_declared_tool_has_a_body_on_the_worker() -> None:
    """The worker binds one body per declaration before it pulls a job."""
    register_all_tools()

    missing = [
        tool.tool_name
        for tool in declared_durable_tools()
        if durable_impl(tool.tool_name) is None
    ]

    assert missing == []


def test_a_registration_that_names_no_declaration_is_refused() -> None:
    """The three names are one string, and a fourth name fails at registration."""
    invented = DurableTool(tool_name="cruncg", estimated_duration_seconds=10)

    async def _body(**kwargs: Any) -> dict[str, Any]:
        del kwargs
        return {}

    with pytest.raises(UndeclaredDurableToolError) as caught:
        register_durable_impl(invented, _body)

    assert "durable tool 'cruncg' is not declared here" in str(caught.value)


async def test_a_deferred_call_carries_the_wdk_token_under_the_job_context(
    dispatch: _App,
) -> None:
    """The worker inherits no context variable, so the token rides the payload."""
    reset = veupathdb_auth_token_ctx.set(_TOKEN)
    try:
        with pytest.raises(CallDeferred):
            await run_control_tests(_Ctx(_deps()))
    finally:
        veupathdb_auth_token_ctx.reset(reset)

    assert dispatch.configured == [
        {
            "name": "durable:run_control_tests_on_step",
            "queue": DURABLE_TASK_QUEUE,
            "lock": dispatch.configured[0]["lock"],
        },
    ]
    assert dispatch.deferred[0]["job_context"] == {"veupathdb_auth_token": _TOKEN}


def test_the_carried_token_masks_itself_and_reads_back_at_the_point_of_use() -> None:
    """A repr of the state never prints the credential the worker restores."""
    reset = veupathdb_auth_token_ctx.set(_TOKEN)
    try:
        state = WdkJobContext().capture()
    finally:
        veupathdb_auth_token_ctx.reset(reset)

    assert _TOKEN not in repr(state)
    assert state.veupathdb_auth_token is not None
    assert state.veupathdb_auth_token.get_secret_value() == _TOKEN
    assert DurableTaskPayload(
        task_id=_TASK_ID,
        thread_id=_TASK_ID,
        job_context=state,
    ).model_dump(mode="json")["job_context"] == {"veupathdb_auth_token": _TOKEN}


async def test_restoring_the_state_installs_the_token_for_the_body() -> None:
    """The body reads the caller's token, not the service account's."""
    state = WdkJobState.model_validate({"veupathdb_auth_token": _TOKEN})

    async with WdkJobContext().restore(state):
        assert veupathdb_auth_token_ctx.get() == _TOKEN

    assert veupathdb_auth_token_ctx.get() is None


@decorator.durable_tool(CONTROL_TESTS)
async def run_control_tests(ctx: _Ctx) -> dict[str, Any]:
    """A stand-in for the agent-side tool, decorated with the real declaration."""
    del ctx
    msg = "the body runs on the worker"
    raise AssertionError(msg)
