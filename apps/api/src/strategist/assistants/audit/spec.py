"""The audit assistant as one installed assistant: one auditor agent on the single-agent graph."""

from __future__ import annotations

from typing import Any

from assistant_core.graph.single_agent import (
    SingleAgent,
    TypedReply,
    single_agent_graph,
)
from assistant_core.graph.turn_state import TurnState
from assistant_core.spec import AssistantSpec, TurnStart
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from strategist.ai.audit.auditor import AUDITOR_LIMITS, build_auditor_agent
from strategist.ai.audit.mock import build_audit_mock
from strategist.ai.audit.reply import AuditReply, reply_text
from strategist.ai.audit.stream_parts import register_audit_stream_parts
from strategist.ai.audit.turn import (
    AuditTurnContext,
    build_deps,
    build_turn_context,
    charge_usage,
)
from strategist.platform.identity import AUDIT_ASSISTANT_ID
from strategist.platform.tool_sources import RESEARCH_TOOL_SOURCE
from strategist.services.wdk_identity import require_registered_wdk_login


def build_initial_state(start: TurnStart) -> TurnState:
    return TurnState(**start.state_kwargs())


def build_audit_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[TurnState, AuditTurnContext, TurnState, TurnState]:
    return single_agent_graph(
        checkpointer=checkpointer,
        state_type=TurnState,
        context_type=AuditTurnContext,
        agent=SingleAgent(
            build_agent=build_auditor_agent,
            build_deps=build_deps,
            usage_limits=AUDITOR_LIMITS,
            reply=TypedReply(output_type=AuditReply, text=reply_text),
        ),
        charge_usage=charge_usage,
    )


def build_audit_spec() -> AssistantSpec:
    return AssistantSpec(
        assistant_id=AUDIT_ASSISTANT_ID,
        build_graph=build_audit_graph,
        build_initial_state=build_initial_state,
        build_turn_context=build_turn_context,
        build_mock_model=build_audit_mock,
        register_stream_parts=register_audit_stream_parts,
        identity_gate=require_registered_wdk_login,
        tool_sources=(RESEARCH_TOOL_SOURCE,),
    )
