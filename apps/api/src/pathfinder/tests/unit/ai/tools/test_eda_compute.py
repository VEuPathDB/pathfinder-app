"""run_eda_compute defers the work and ends the turn on the call."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from assistant_core.tasks import decorator
from assistant_core.tasks.declaration import durable_impl
from pydantic_ai.exceptions import CallDeferred
from pydantic_ai.tools import RunContext

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_compute
from pathfinder.ai.tools.standalone.eda_compute import EdaVariableSpecIn
from pathfinder.jobs.impls import register_all_tools
from pathfinder.jobs.impls.eda_compute_impl import run_eda_compute_impl
from pathfinder.tests.unit.ai.tools.conftest import lead_run_context


@pytest.fixture
def compute_ctx() -> RunContext[LeadDeps]:
    return lead_run_context(
        user_prompt="which genes respond to fever", tool_call_id="call_compute"
    )


class _Task:
    def __init__(self, deferred: list[dict[str, Any]]) -> None:
        self._deferred = deferred

    async def defer_async(self, **payload: Any) -> None:
        self._deferred.append(payload)


class _App:
    def __init__(self, deferred: list[dict[str, Any]]) -> None:
        self._deferred = deferred

    def configure_task(self, *, name: str, queue: str, lock: str) -> _Task:
        del name, queue, lock
        return _Task(self._deferred)


@pytest.fixture
def dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Capture what the decorator creates and defers, without a graph or a db."""
    created: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    async def create(**kwargs: Any) -> Any:
        created.append(dict(kwargs))
        return uuid4()

    monkeypatch.setattr(decorator, "create_background_task", create)
    monkeypatch.setattr(decorator, "task_app", lambda: _App(deferred))
    monkeypatch.setattr(decorator, "get_stream_writer", lambda: lambda _payload: None)
    return created, deferred


async def test_calling_the_tool_creates_a_task_and_defers_a_job(
    compute_ctx: RunContext[LeadDeps],
    dispatch: tuple[list[dict[str, Any]], list[dict[str, Any]]],
) -> None:
    created, deferred = dispatch

    with pytest.raises(CallDeferred):
        await eda_compute.run_eda_compute(
            compute_ctx,
            identifier_variable=EdaVariableSpecIn(
                entity_id="ENT_fd574cd6",
                variable_id="VEUPATHDB_GENE_ID",
            ),
            value_variable=EdaVariableSpecIn(
                entity_id="ENT_fd574cd6",
                variable_id="SEQUENCE_READ_COUNT_SENSE",
            ),
            comparator_variable=EdaVariableSpecIn(
                entity_id="ENT_8151325d",
                variable_id="VAR_081ab087",
            ),
            group_a_labels=["normal"],
            group_b_labels=["febrile"],
        )

    assert [entry["tool_name"] for entry in created] == ["run_eda_compute"]
    assert created[0]["conversation_id"] == compute_ctx.deps.state.conversation_id
    assert created[0]["user_id"] == compute_ctx.deps.runtime.user_id
    assert created[0]["tool_call_id"] == "call_compute"
    assert len(deferred) == 1
    assert deferred[0]["thread_id"] == str(compute_ctx.deps.state.conversation_id)


async def test_the_deferred_job_carries_the_arguments_the_impl_needs(
    compute_ctx: RunContext[LeadDeps],
    dispatch: tuple[list[dict[str, Any]], list[dict[str, Any]]],
) -> None:
    created, _deferred = dispatch

    with pytest.raises(CallDeferred):
        await eda_compute.run_eda_compute(
            compute_ctx,
            identifier_variable=EdaVariableSpecIn(
                entity_id="E",
                variable_id="VEUPATHDB_GENE_ID",
            ),
            value_variable=EdaVariableSpecIn(
                entity_id="E",
                variable_id="SEQUENCE_READ_COUNT",
            ),
            comparator_variable=EdaVariableSpecIn(entity_id="P", variable_id="C"),
            group_a_labels=["a"],
            group_b_labels=["b"],
            method="limma",
        )

    kwargs = created[0]["args"]["kwargs"]
    assert kwargs["method"] == "limma"
    assert kwargs["group_a_labels"] == ["a"]
    assert kwargs["group_b_labels"] == ["b"]
    assert kwargs["identifier_variable"] == {
        "entity_id": "E",
        "variable_id": "VEUPATHDB_GENE_ID",
    }
    assert kwargs["comparator_variable"] == {"entity_id": "P", "variable_id": "C"}


async def test_the_deferred_job_carries_the_caption_the_model_wrote(
    compute_ctx: RunContext[LeadDeps],
    dispatch: tuple[list[dict[str, Any]], list[dict[str, Any]]],
) -> None:
    """The worker draws the volcano, so the caption travels with the args."""
    created, _deferred = dispatch

    with pytest.raises(CallDeferred):
        await eda_compute.run_eda_compute(
            compute_ctx,
            identifier_variable=EdaVariableSpecIn(
                entity_id="E",
                variable_id="VEUPATHDB_GENE_ID",
            ),
            value_variable=EdaVariableSpecIn(
                entity_id="E",
                variable_id="SEQUENCE_READ_COUNT",
            ),
            comparator_variable=EdaVariableSpecIn(entity_id="P", variable_id="C"),
            group_a_labels=["normal"],
            group_b_labels=["febrile"],
            caption="Genes higher in febrile samples than in normal samples",
        )

    kwargs = created[0]["args"]["kwargs"]
    assert kwargs["caption"] == (
        "Genes higher in febrile samples than in normal samples"
    )


async def test_the_estimated_duration_is_declared(
    compute_ctx: RunContext[LeadDeps],
    dispatch: tuple[list[dict[str, Any]], list[dict[str, Any]]],
) -> None:
    created, _deferred = dispatch

    with pytest.raises(CallDeferred):
        await eda_compute.run_eda_compute(
            compute_ctx,
            identifier_variable=EdaVariableSpecIn(
                entity_id="E",
                variable_id="VEUPATHDB_GENE_ID",
            ),
            value_variable=EdaVariableSpecIn(
                entity_id="E",
                variable_id="SEQUENCE_READ_COUNT",
            ),
            comparator_variable=EdaVariableSpecIn(entity_id="P", variable_id="C"),
            group_a_labels=["a"],
            group_b_labels=["b"],
        )

    assert created[0]["estimated_duration_seconds"] == 120


def test_the_tool_is_registered_in_the_worker_registry() -> None:
    register_all_tools()

    assert durable_impl("run_eda_compute") == run_eda_compute_impl
