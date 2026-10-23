from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from assistant_core.graph.turn_state import TurnState
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.retrievals import AuditRetrievalToolset
from pathfinder.ai.audit.turn import AuditTurnContext, build_deps
from pathfinder.tests._support.database import no_database

_DOI = "10.1000/example.1"
_PAGE = "https://example.org/paper"


def literature_search(query: str) -> dict[str, Any]:
    del query
    return {"results": [{"doi": _DOI, "url": _PAGE}]}


def _searching(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del info
    if len(messages) == 1:
        call = ToolCallPart(
            tool_name="research_literature_search", args={"query": "gene"}
        )
        return ModelResponse(parts=[call])
    return ModelResponse(parts=[TextPart("read")])


async def test_a_retrieved_reference_is_a_read_a_verdict_may_cite() -> None:
    served = FunctionToolset([literature_search]).prefixed("research")
    deps = AuditDeps(site_id="plasmodb", user_id=uuid4(), conversation_id=uuid4())
    agent = Agent(
        FunctionModel(_searching),
        deps_type=AuditDeps,
        toolsets=[AuditRetrievalToolset(served)],
    )

    await agent.run("find the paper", deps=deps)

    assert deps.held_reads() == frozenset({_DOI, _PAGE})


def test_the_deps_carry_the_turns_thread_site_and_message() -> None:
    user_id = uuid4()
    state = TurnState(
        conversation_id=uuid4(),
        user_id=user_id,
        site_id="toxodb",
        mode="chat",
        user_prompt="How far is the audit?",
    )
    context = AuditTurnContext(
        site_id="toxodb",
        user_id=user_id,
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )

    deps = build_deps(state, context)

    assert (deps.site_id, deps.user_id, deps.conversation_id) == (
        "toxodb",
        user_id,
        state.conversation_id,
    )
    assert (deps.request, deps.origin, deps.tool_sources) == (
        "How far is the audit?",
        "auditor",
        None,
    )
