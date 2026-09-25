"""A delete card names the step the call removes, and the reply names that step.

The strategy is the orthology transform over an INTERSECT of the signal
peptide and transmembrane searches; the call removes the transform.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import (
    SubAgentApprovalCall,
    SubAgentApprovalPending,
)
from pydantic import JsonValue
from pydantic_ai import Agent, DeferredToolRequests, Tool
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.lead import deleted_steps
from pathfinder.ai.lead.deleted_steps import ask_about_the_removals, delete_question
from pathfinder.ai.lead.lead_agent import LEAD_MODEL, LeadAgent
from pathfinder.ai.lead.lead_tools import delete_step
from pathfinder.ai.lead.live_state import LiveStepState, LiveStrategyState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_runtime,
    pipeline_state,
)
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    session_with,
)

TRANSFORM = "c_orthologs_pvivax_p01"
DELETE_REPLY = "The orthology transform goes, and the intersection becomes the root."
ASKED = "Delete step 'Transform by Orthology' (GenesByOrthologs, 142 genes)?"
MISNAMED = (
    "Removed the intersection step. Both underlying searches were kept exactly "
    "as they were: the predicted signal-peptide search retains 479 Plasmodium "
    "vivax P01 ortholog records, and the 2-99 transmembrane-domain search "
    "retains 840 Plasmodium vivax P01 ortholog records."
)
LIVE = LiveStrategyState(
    wdk_strategy_id=330703053,
    step_count=4,
    root_count=142,
    steps=[
        LiveStepState(
            step_id=TRANSFORM,
            display_name="Transform by Orthology",
            search_name="GenesByOrthologs",
            estimated_size=142,
        ),
        LiveStepState(
            step_id="step_497dcd2a", display_name="Intersect", estimated_size=116
        ),
        LiveStepState(
            step_id="step_sp",
            display_name="Predicted Signal Peptide",
            search_name="GenesWithSignalPeptide",
            estimated_size=479,
        ),
        LiveStepState(
            step_id="step_tm",
            display_name="Transmembrane Domain Count",
            search_name="GenesByTransmembraneDomains",
            estimated_size=840,
        ),
    ],
)


def _strategy() -> StrategyStepNode:
    return StrategyStepNode(
        id=TRANSFORM,
        search_name="GenesByOrthologs",
        display_name="Transform by Orthology",
        primary_input=combine(
            "step_497dcd2a",
            StrategyStepNode(
                id="step_sp",
                search_name="GenesWithSignalPeptide",
                display_name="Predicted Signal Peptide",
            ),
            StrategyStepNode(
                id="step_tm",
                search_name="GenesByTransmembraneDomains",
                display_name="Transmembrane Domain Count",
            ),
        ),
    )


def test_the_card_names_the_step_by_title_search_and_count() -> None:
    assert delete_question(LIVE, TRANSFORM) == ASKED
    assert (
        delete_question(LIVE, "step_497dcd2a") == "Delete step 'Intersect' (116 genes)?"
    )
    assert delete_question(LIVE, "step_gone") is None


def _quota_offline() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


def _calls_delete() -> FunctionModel:
    call = ToolCallPart(
        tool_name="delete_step",
        args={"step_id": TRANSFORM, "reply": DELETE_REPLY},
        tool_call_id="call_delete",
    )

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        return ModelResponse(parts=[call])

    async def _stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[dict[int, DeltaToolCall]]:
        del messages, info
        yield {
            0: DeltaToolCall(
                name=call.tool_name,
                json_args=call.args_as_json_str(),
                tool_call_id=call.tool_call_id,
            )
        }

    return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


async def test_a_parked_delete_writes_its_question_for_the_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _live(*_args: object) -> LiveStrategyState:
        return LIVE

    monkeypatch.setattr(deleted_steps, "read_live_state", _live)
    monkeypatch.setattr(_lead_model, "get_mock_model", _calls_delete)
    state = pipeline_state(
        user_prompt="Delete the intersection step.", user_message_id=uuid4()
    )
    deps = LeadDeps(
        state=state,
        intent=None,
        runtime=dataclasses.replace(lead_runtime(), db_session_factory=_quota_offline),
        retrieved_memories=[],
    )
    agent: LeadAgent = Agent(
        LEAD_MODEL,
        output_type=[LeadResponse, DeferredToolRequests],
        deps_type=LeadDeps,
        tools=[Tool(delete_step, requires_approval=True)],
        name="lead",
        defer_model_check=True,
    )
    writer = ChunkCollector()

    await _drive_lead_stream(
        state=state,
        agent=agent,
        deps=deps,
        capture=_LeadRunCapture(),
        writer=writer,
        message_id=uuid4(),
    )

    assert [c["delta"] for c in writer.chunks_of("text-delta")] == [DELETE_REPLY]
    summaries = writer.data_of("data-tool-summary")
    assert [(s["toolCallId"], s["summary"]) for s in summaries] == [
        ("call_delete", ASKED)
    ]
    assert writer.chunks_of("tool-approval-request")[0]["toolCallId"] == "call_delete"


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


async def _deleted_the_transform() -> list[str]:
    ctx = lead_run_context(
        user_prompt="Delete the intersection step but keep both searches.",
        strategy_session=session_with(_strategy(), {}),
        tool_call_id="call_delete",
    )
    await delete_step(
        ctx,
        step_id=TRANSFORM,
        reply="I will make this change and report what it takes with it.",
    )
    record = turn_record(ctx)
    return [
        mismatch.sentence
        for mismatch in reconcile(
            LeadResponse(prose=MISNAMED, strategy_changed=True), record
        )
        if mismatch.kind == "misnamed_deletion"
    ]


@pytest.mark.usefixtures("stub_api")
async def test_a_reply_naming_a_step_it_did_not_delete_is_corrected() -> None:
    sentences = await _deleted_the_transform()

    assert sentences == [
        (
            "Your reply says it removed the intersection step, and that step is "
            "still in the strategy. This turn deleted 'Transform by Orthology' "
            "(GenesByOrthologs). Name the step that was deleted, by its title."
        )
    ]


@pytest.mark.usefixtures("stub_api")
async def test_a_reply_naming_the_deleted_step_stands() -> None:
    ctx = lead_run_context(
        user_prompt="Delete the orthology step.",
        strategy_session=session_with(_strategy(), {}),
        tool_call_id="call_delete",
    )
    await delete_step(
        ctx,
        step_id=TRANSFORM,
        reply="I will make this change and report what it takes with it.",
    )

    kinds = [
        mismatch.kind
        for mismatch in reconcile(
            LeadResponse(
                prose="Removed the orthology transform step; the intersection stands.",
                strategy_changed=True,
            ),
            turn_record(ctx),
        )
    ]

    assert "misnamed_deletion" not in kinds


@pytest.mark.usefixtures("stub_api")
async def test_deleting_the_intersection_under_a_transform_removes_one_search() -> None:
    """The combine keeps its first input in its place; its second input leaves."""
    ctx = lead_run_context(
        user_prompt="Delete the intersection step but keep both searches.",
        strategy_session=session_with(_strategy(), {}),
        tool_call_id="call_delete",
    )

    answer = await delete_step(
        ctx,
        step_id="step_497dcd2a",
        reply="I will make this change and report what it takes with it.",
    )

    payload = returned(answer, dict[str, JsonValue])
    assert payload["deleted"] == ["step_497dcd2a", "step_tm"]
    graph = ctx.deps.runtime.strategy_session.graph
    assert graph is not None
    assert sorted(graph.steps) == [TRANSFORM, "step_sp"]


async def test_a_removal_a_building_pass_parked_is_asked_by_its_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _live(*_args: object) -> LiveStrategyState:
        return LIVE

    monkeypatch.setattr(deleted_steps, "read_live_state", _live)
    deps = LeadDeps(
        state=pipeline_state(user_prompt="Rebuild the orthology branch."),
        intent=None,
        runtime=lead_runtime(),
        retrieved_memories=[],
    )
    deps.pending_sub_agent_approvals["call_edit"] = SubAgentApprovalPending(
        role="execution",
        approvals=[
            SubAgentApprovalCall(
                tool_call_id="call_inner_delete",
                tool_name="delete_step",
                args={"step_id": "step_497dcd2a"},
            ),
            SubAgentApprovalCall(
                tool_call_id="call_inner_replace",
                tool_name="replace_subtree",
                args={"step_id": TRANSFORM, "new_subtree": {"id": "s_new"}},
            ),
        ],
    )
    writer = ChunkCollector()

    await ask_about_the_removals(
        deps,
        DeferredToolRequests(calls=[ToolCallPart("run_edit", {}, "call_edit")]),
        writer,
    )

    assert [
        (s["toolCallId"], s["summary"]) for s in writer.data_of("data-tool-summary")
    ] == [
        ("call_inner_delete", "Delete step 'Intersect' (116 genes)?"),
        (
            "call_inner_replace",
            (
                "Replace step 'Transform by Orthology' (GenesByOrthologs, 142 genes) "
                "and the steps under it?"
            ),
        ),
    ]
