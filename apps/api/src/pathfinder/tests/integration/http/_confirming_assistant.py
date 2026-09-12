"""A site-help-shaped assistant whose one tool needs the user's approval.

Same architecture as site help - one agent over the bare turn state on
``single_agent_graph`` - with a tool the runtime must ask about before it
runs. It stands in for site help so the whole HTTP path (route, worker,
stream, resume) carries a real approval.
"""

from __future__ import annotations

from typing import Any

from assistant_core.graph.single_agent import single_agent_graph
from assistant_core.graph.turn_state import TurnState
from assistant_core.models.scripted import (
    RoleMarkers,
    RoleScript,
    ScriptedModel,
    ScriptedPart,
    last_user_text,
    scripted_text,
    tool_return_parts,
)
from assistant_core.spec import AssistantSpec
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from pathfinder.assistants.site_help.agent import SiteHelpDeps
from pathfinder.assistants.site_help.spec import (
    SiteHelpTurnContext,
    build_deps,
    build_initial_state,
    build_turn_context,
    charge_usage,
)
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID

CONFIRM_TOOL = "delete_saved_gene_set"
CONFIRM_CALL_ID = "call_delete_set"
CONFIRM_PROMPT = "delete my saved gene set on plasmodb"
CONFIRMED_REPLY = "Done: deleted kinase-candidates."
DENIED_REPLY = "Nothing to do."


async def delete_saved_gene_set(gene_set_id: str) -> str:
    """Delete one of the caller's saved gene sets."""
    return f"deleted {gene_set_id}"


def _script(messages: list[ModelMessage]) -> ScriptedPart:
    returns = tool_return_parts(messages)
    if returns:
        return scripted_text(f"Done: {returns[-1].content}.")
    text = last_user_text(messages)
    if CONFIRM_PROMPT in text:
        return ToolCallPart(
            tool_name=CONFIRM_TOOL,
            args={"gene_set_id": "kinase-candidates"},
            tool_call_id=CONFIRM_CALL_ID,
        )
    return scripted_text(DENIED_REPLY)


_SCRIPTS: dict[str, RoleScript] = {"confirming": _script}

_MODEL = ScriptedModel(
    roles=(RoleMarkers(role="confirming", markers=frozenset({CONFIRM_TOOL})),),
    scripts=_SCRIPTS,
    unknown=_script,
)


def build_confirming_mock() -> FunctionModel:
    return _MODEL.as_function_model()


def build_confirming_agent() -> Agent[SiteHelpDeps, str]:
    return Agent(
        build_confirming_mock(),
        output_type=str,
        deps_type=SiteHelpDeps,
        instructions="Help the user, and confirm anything destructive.",
        tools=[Tool(delete_saved_gene_set, requires_approval=True)],
        name="confirming",
        defer_model_check=True,
    )


def _build_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[TurnState, SiteHelpTurnContext, TurnState, TurnState]:
    return single_agent_graph(
        checkpointer=checkpointer,
        state_type=TurnState,
        context_type=SiteHelpTurnContext,
        build_agent=build_confirming_agent,
        build_deps=build_deps,
        charge_usage=charge_usage,
    )


def build_confirming_spec() -> AssistantSpec:
    """Registered under site help's id, so the route and the gate are unchanged."""
    return AssistantSpec(
        assistant_id=SITE_HELP_ASSISTANT_ID,
        build_graph=_build_graph,
        build_initial_state=build_initial_state,
        build_turn_context=build_turn_context,
        build_mock_model=build_confirming_mock,
    )


__all__ = [
    "CONFIRMED_REPLY",
    "CONFIRM_CALL_ID",
    "CONFIRM_PROMPT",
    "CONFIRM_TOOL",
    "DENIED_REPLY",
    "build_confirming_agent",
    "build_confirming_mock",
    "build_confirming_spec",
]
