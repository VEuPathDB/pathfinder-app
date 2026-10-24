"""One audit assistant turn: its context, the deps its agent runs on, and the usage it charges."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from assistant_core.graph.runtime import TurnContext
from assistant_core.graph.turn_state import TurnState
from assistant_core.platform.db import async_session_factory
from assistant_core.quota import accumulate
from assistant_core.spec import TurnContextRequest
from pydantic_ai.toolsets import AbstractToolset, CombinedToolset

from pathfinder.ai.audit.auditor import charged_model_id
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.retrievals import AuditRetrievalToolset
from pathfinder.platform.model_keys import turn_paid_by


@dataclass(frozen=True, kw_only=True)
class AuditTurnContext(TurnContext):
    tool_sources: Mapping[str, AbstractToolset[Any]] = field(default_factory=dict)


async def build_turn_context(request: TurnContextRequest) -> AuditTurnContext:
    return AuditTurnContext(
        site_id=request.site_id,
        user_id=request.user_id,
        db_session_factory=async_session_factory,
        cancel_event=request.cancel_event,
        memory_store=request.memory_store,
        phase_models=dict(request.phase_models),
        phase_reasoning=dict(request.phase_reasoning),
        tool_sources=dict(request.tool_sources),
    )


def build_deps(state: TurnState, context: AuditTurnContext) -> AuditDeps:
    sources = list(context.tool_sources.values())
    return AuditDeps(
        site_id=context.site_id,
        user_id=context.user_id,
        conversation_id=state.conversation_id,
        db_session_factory=context.db_session_factory,
        memory_store=context.memory_store,
        cancel_event=context.cancel_event,
        tool_sources=(
            AuditRetrievalToolset(CombinedToolset(sources)) if sources else None
        ),
        request=state.user_prompt,
    )


async def charge_usage(user_id: UUID, tokens: int, cost_usd: Decimal) -> None:
    if tokens == 0 and cost_usd == 0:
        return
    async with async_session_factory() as session:
        await accumulate(
            session,
            user_id=user_id,
            tokens=tokens,
            cost_usd=cost_usd,
            paid_by=turn_paid_by(charged_model_id()),
        )
        await session.commit()
