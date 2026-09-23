"""run_eda_compute defers the work and ends the turn on the call."""

from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.tasks.declaration import durable_impl
from pydantic import ValidationError
from pydantic_ai.exceptions import CallDeferred, ModelRetry
from pydantic_ai.tools import RunContext

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_compute
from pathfinder.ai.tools.standalone.eda_compute import EdaVariableSpecIn
from pathfinder.ai.tools.toolsets.eda import build_toolset
from pathfinder.jobs.impls import register_all_tools
from pathfinder.jobs.impls.eda_compute_impl import run_eda_compute_impl
from pathfinder.tests._support.durable_dispatch import (
    DurableDispatch,
    capture_durable_dispatch,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.tools.conftest import unwrap_function_toolset


@pytest.fixture
def compute_ctx() -> RunContext[LeadDeps]:
    return lead_run_context(
        user_prompt="which genes respond to fever", tool_call_id="call_compute"
    )


@pytest.fixture
def dispatch(monkeypatch: pytest.MonkeyPatch) -> DurableDispatch:
    return capture_durable_dispatch(monkeypatch)


async def test_calling_the_tool_creates_a_task_and_defers_a_job(
    compute_ctx: RunContext[LeadDeps],
    dispatch: DurableDispatch,
) -> None:
    created, deferred = dispatch.created, dispatch.deferred

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
    dispatch: DurableDispatch,
) -> None:
    created = dispatch.created

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
    dispatch: DurableDispatch,
) -> None:
    """The worker draws the volcano, so the caption travels with the args."""
    created = dispatch.created

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
    dispatch: DurableDispatch,
) -> None:
    created = dispatch.created

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


async def test_groups_that_share_a_label_are_refused_before_the_job(
    compute_ctx: RunContext[LeadDeps],
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await eda_compute.refuse_shared_labels(
            compute_ctx,
            identifier_variable=EdaVariableSpecIn(
                entity_id="E", variable_id="VEUPATHDB_GENE_ID"
            ),
            value_variable=EdaVariableSpecIn(
                entity_id="E", variable_id="SEQUENCE_READ_COUNT"
            ),
            comparator_variable=EdaVariableSpecIn(entity_id="P", variable_id="C"),
            group_a_labels=["24h pbm", "18h pbm"],
            group_b_labels=["18h pbm", "36h pbm"],
        )

    assert "18h pbm" in str(refused.value)
    assert "both groups" in str(refused.value)


def test_the_toolset_checks_the_groups_before_it_defers() -> None:
    tools = unwrap_function_toolset(build_toolset()).tools

    assert tools["run_eda_compute"].args_validator is eda_compute.refuse_shared_labels


def test_a_resumed_result_must_name_its_groups() -> None:
    """The trace line names each side by its group, so the groups are required."""
    with pytest.raises(ValidationError):
        eda_compute._compute_chunks_from_result(
            {
                "status": "success",
                "result": {"genesTested": 5, "retainedUp": 1, "retainedDown": 1},
            },
            uuid4(),
            "call_1",
        )
