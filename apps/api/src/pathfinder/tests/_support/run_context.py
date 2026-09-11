"""The contexts a tool runs under: the turn runtime, and a Lead-mounted tool's context."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from assistant_core.platform.db import DBSessionFactory
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database


def run_context_for[DepsT](
    deps: DepsT, tool_call_id: str | None = None
) -> RunContext[DepsT]:
    """The run context a tool sees, around the dependencies it is given."""
    return RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        messages=[],
        tool_call_id=tool_call_id,
    )


def turn_runtime(
    *,
    site_id: str = "plasmodb",
    db_session_factory: DBSessionFactory = no_database,
    strategy_session: StrategySession | None = None,
    user_id: UUID | None = None,
) -> Context:
    """The runtime one turn carries, on the site a test names."""
    return Context(
        site_id=site_id,
        user_id=user_id if user_id is not None else uuid4(),
        strategy_session=strategy_session or StrategySession(site_id=site_id),
        db_session_factory=db_session_factory,
        cancel_event=asyncio.Event(),
    )


def lead_run_context(
    *,
    user_prompt: str = "find kinases",
    conversation_id: UUID | None = None,
    strategy_session: StrategySession | None = None,
    tool_call_id: str | None = None,
    db_session_factory: DBSessionFactory = no_database,
) -> RunContext[LeadDeps]:
    """The context a Lead-mounted tool runs under."""
    state = PipelineState(
        conversation_id=conversation_id or uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt=user_prompt,
    )
    runtime = turn_runtime(
        db_session_factory=db_session_factory,
        strategy_session=strategy_session,
        user_id=state.user_id,
    )
    deps = LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])
    return run_context_for(deps, tool_call_id)
