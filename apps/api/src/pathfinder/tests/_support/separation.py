"""Two separation runs the tool server returned on plasmodb, as recorded."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

from assistant_core.graph.turn_state import (
    DurableCall,
    DurableTaskResult,
    PendingDurableCall,
)
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, UserPromptPart
from veupathdb_mcp.separation import SeparationResult

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.separation import AttachedControls, SeparationOffer
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.separation.offer import separation_report
from pathfinder.tests._support.database import no_database

_RECORDED = Path(__file__).resolve().parents[1] / "fixtures" / "separation"

# Exact mode on "PF3D7 Signal Peptide Genes": 80 positives, 40 negatives.
SIGNAL_PEPTIDE = "signal_peptide_exact"
# Similar mode on "PF3D7 Erythrocyte Invasion Machinery": 80 positives, 55 negatives.
ERYTHROCYTE_INVASION = "erythrocyte_invasion_similar"

TASK_ID = UUID("0c6100d2-0000-4000-8000-00000000a16a")


def recorded_separation(name: str) -> SeparationResult:
    """One recorded run, as the library returns it."""
    return SeparationResult.model_validate_json(
        (_RECORDED / f"{name}.json").read_text()
    )


def recorded_offer(name: str = SIGNAL_PEPTIDE) -> SeparationOffer:
    """The offer PathFinder reads from one recorded run."""
    offer = separation_report(recorded_separation(name), task_id=TASK_ID).offer
    assert offer is not None
    return offer


ATTACHED_CONTROLS = AttachedControls(
    task_id=str(TASK_ID),
    control_set_id="5f1c6a2e-0000-4000-8000-00000000c0de",
    positives=["PF3D7_0100600", "PF3D7_0100800"],
    negatives=["PF3D7_0508800"],
)


SEPARATION_CALL = "call_separate"
_HISTORY = ModelMessagesTypeAdapter.dump_json(
    [ModelRequest(parts=[UserPromptPart(content="separate my controls")])],
).decode()


def lead_answered_by_a_separation(result: SeparationResult) -> LeadDeps:
    """A Lead parked on one ``separate_controls`` call the worker has answered."""
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="separate my controls",
        user_message_id=uuid4(),
    )
    state.pending_durable_call = PendingDurableCall(
        phase="lead",
        tool_call_id=SEPARATION_CALL,
        tool_name="separate_controls",
        tool_args={"mode": "exact"},
        prior_messages_json=_HISTORY,
        durable_calls=[
            DurableCall(
                tool_call_id=SEPARATION_CALL,
                tool_name="separate_controls",
                args={"mode": "exact"},
                task_id=TASK_ID,
                durable_tool_name="separate_controls",
            ),
        ],
    )
    state.durable_result = DurableTaskResult(
        task_id=TASK_ID,
        status="success",
        result=separation_report(result, task_id=TASK_ID).model_dump(
            by_alias=True, mode="json"
        ),
    )
    context = Context(
        site_id="plasmodb",
        user_id=state.user_id,
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )
    return LeadDeps(state=state, intent=None, runtime=context, retrieved_memories=[])
