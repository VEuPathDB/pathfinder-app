"""run_eda_dimensionality_reduction defers the work, its resumed result names the
components in one line, and the resume files its statistic as a fact."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import (
    DurableCall,
    DurableTaskResult,
    PendingDurableCall,
)
from assistant_core.tasks.declaration import durable_impl
from pydantic_ai.exceptions import CallDeferred
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, UserPromptPart
from pydantic_ai.tools import RunContext
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph._lead_turn import resolve_turn_resumption
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_statistics
from pathfinder.ai.tools.standalone.eda_compute import EdaVariableSpecIn
from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.jobs.impls import register_all_tools
from pathfinder.jobs.impls.eda_pca_impl import run_eda_dimensionality_reduction_impl
from pathfinder.tests._support.durable_dispatch import (
    DurableDispatch,
    capture_durable_dispatch,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.tools.conftest import summary_chunks

_RESULT = {
    "statistic": {
        "id": "stat_1c2d3e4f",
        "kind": "pca",
        "title": "PCA of 12 samples",
        "rows": [
            {"name": "PC1", "value": "54.35%"},
            {"name": "PC2", "value": "12.79%"},
            {"name": "samples", "value": "12 samples"},
            {"name": "groups", "value": "3 groups"},
        ],
    },
    "guidance": "State each value with [stat:<id>.<row name>].",
}


@pytest.fixture
def pca_ctx() -> RunContext[LeadDeps]:
    return lead_run_context(
        user_prompt="do the conditions separate", tool_call_id="call_pca"
    )


@pytest.fixture
def dispatch(monkeypatch: pytest.MonkeyPatch) -> DurableDispatch:
    return capture_durable_dispatch(monkeypatch)


async def test_calling_the_tool_defers_a_job_with_the_arguments_the_impl_reads(
    pca_ctx: RunContext[LeadDeps], dispatch: DurableDispatch
) -> None:
    with pytest.raises(CallDeferred):
        await eda_statistics.run_eda_dimensionality_reduction(
            pca_ctx,
            identifier_variable=EdaVariableSpecIn(
                entity_id="ENT_fd574cd6", variable_id="VEUPATHDB_GENE_ID"
            ),
            value_variable=EdaVariableSpecIn(
                entity_id="ENT_fd574cd6", variable_id="SEQUENCE_READ_COUNT_SENSE"
            ),
            data_format="rawCounts",
            color_by_variable=EdaVariableSpecIn(
                entity_id="ENT_8151325d", variable_id="VAR_84f17484"
            ),
            caption="The samples by genotype on the first two components",
        )

    (created,) = dispatch.created
    assert created["tool_name"] == "run_eda_dimensionality_reduction"
    assert created["tool_call_id"] == "call_pca"
    assert created["estimated_duration_seconds"] == 120
    kwargs = created["args"]["kwargs"]
    assert kwargs["data_format"] == "rawCounts"
    assert kwargs["color_by_variable"] == {
        "entity_id": "ENT_8151325d",
        "variable_id": "VAR_84f17484",
    }
    assert kwargs["caption"] == "The samples by genotype on the first two components"
    assert len(dispatch.deferred) == 1


def test_the_tool_is_registered_in_the_worker_registry() -> None:
    register_all_tools()

    assert (
        durable_impl("run_eda_dimensionality_reduction")
        == run_eda_dimensionality_reduction_impl
    )


def test_the_resumed_result_names_both_components_in_one_line() -> None:
    chunks = eda_statistics._pca_chunks_from_result(
        {"status": "success", "result": _RESULT}, uuid4(), "call_pca"
    )

    (summary,) = summary_chunks(chunks)
    assert summary.data["summary"] == (
        "12 samples, 3 groups; PC1 explains 54.35% of the variance and PC2 12.79%"
    )


def _offline() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


async def test_a_finished_reduction_files_its_statistic_on_resume() -> None:
    task_id = uuid4()
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="do the conditions separate",
        user_message_id=uuid4(),
    )
    state.pending_durable_call = PendingDurableCall(
        phase="lead",
        tool_call_id="call_pca",
        tool_name="run_eda_dimensionality_reduction",
        prior_messages_json=ModelMessagesTypeAdapter.dump_json(
            [ModelRequest(parts=[UserPromptPart(content="do the conditions separate")])]
        ).decode(),
        durable_calls=[
            DurableCall(
                tool_call_id="call_pca",
                tool_name="run_eda_dimensionality_reduction",
                task_id=task_id,
                durable_tool_name="run_eda_dimensionality_reduction",
            )
        ],
    )
    state.durable_result = DurableTaskResult(
        task_id=task_id, status="success", result=_RESULT
    )
    deps = LeadDeps(
        state=state,
        intent=None,
        runtime=Context(
            site_id="plasmodb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=_offline,
            cancel_event=asyncio.Event(),
        ),
        retrieved_memories=[],
    )

    await resolve_turn_resumption(state=state, deps=deps)

    assert state.domain.statistics == [
        StatisticFact(
            id="stat_1c2d3e4f",
            kind="pca",
            title="PCA of 12 samples",
            rows=[
                StatisticRowFact(name="PC1", value="54.35%"),
                StatisticRowFact(name="PC2", value="12.79%"),
                StatisticRowFact(name="samples", value="12 samples"),
                StatisticRowFact(name="groups", value="3 groups"),
            ],
        )
    ]
