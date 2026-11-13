"""Strategist as one assistant: its graph, state, parts, memory and identity."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from assistant_core.conversation.stream_parts.registry import StreamPartRegistry
from assistant_core.platform.db import async_session_factory
from assistant_core.spec import AssistantSpec, TurnContextRequest, TurnStart
from pydantic_ai.models import Model
from veupathdb.domain.strategy import CombineOp

from strategist.ai.agents.state import SearchOverview
from strategist.ai.audit.stream_parts import register_audit_stream_parts
from strategist.ai.conversation.turn_stop import restore_pre_turn_strategy
from strategist.ai.eda_stream_parts import register_eda_stream_parts
from strategist.ai.graph.builder import build_strategist_graph
from strategist.ai.graph.runtime import Context
from strategist.ai.graph.state import (
    FailureCause,
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from strategist.ai.graph.stream_events import strategy_revision_event
from strategist.ai.lead.intent import IntentClassification, UserIntent
from strategist.ai.models.mock import get_mock_model
from strategist.ai.strategy_stream_parts import register_strategy_stream_parts
from strategist.domain.memory import MEMORY_KINDS
from strategist.domain.separation import AttachedControls, SeparationOffer
from strategist.domain.strategy.build_outcome import (
    BuildOutcome,
    NodeResult,
    StepPushFailure,
)
from strategist.domain.strategy.constraints import ConstraintKind, ConstraintSource
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.domain.strategy.staleness import StaleBuild
from strategist.persistence.repositories import ConversationRepository
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID
from strategist.platform.tool_sources import RESEARCH_TOOL_SOURCE
from strategist.services.conversations.responses import conversation_strategy_revision
from strategist.services.conversations.turns import turn_start_revision_id
from strategist.services.memory_setting import the_researchers_store
from strategist.services.strategies.session_factory import (
    build_strategy_session,
    persisted_graph,
)
from strategist.services.wdk_identity import require_registered_wdk_login

STRATEGIST_CHECKPOINT_TYPES: tuple[type, ...] = (
    SearchOverview,
    PhaseDisposition,
    VerificationDigest,
    FailureCause,
    IntentClassification,
    UserIntent,
    BuildOutcome,
    NodeResult,
    StepPushFailure,
    ConstraintKind,
    ConstraintSource,
    CombineOp,
    OperationalSpec,
    StaleBuild,
    StrategyDomainState,
    SeparationOffer,
    AttachedControls,
)


def build_initial_state(start: TurnStart) -> PipelineState:
    return PipelineState(**start.state_kwargs())


async def build_turn_context(request: TurnContextRequest) -> Context:
    conversation = request.conversation
    strategy = None
    if conversation is not None:
        async with async_session_factory() as session:
            strategy = await ConversationRepository(session).get_strategy(
                conversation.id,
            )
    return Context(
        site_id=request.site_id,
        user_id=request.user_id,
        strategy_session=build_strategy_session(
            site_id=request.site_id,
            strategy_graph=(
                None
                if conversation is None or strategy is None
                else persisted_graph(conversation, strategy)
            ),
        ),
        db_session_factory=async_session_factory,
        tool_sources=dict(request.tool_sources),
        cancel_event=request.cancel_event,
        memory_store=await the_researchers_store(request.memory_store, request.user_id),
        phase_models=dict(request.phase_models),
        phase_reasoning=dict(request.phase_reasoning),
    )


async def strategy_revision_chunks(
    conversation_id: UUID,
) -> tuple[dict[str, Any], ...]:
    """Stamp the finished turn with the strategy state it described.

    Read after the graph has run so it reflects any build this turn did.
    A conversation with no strategy emits nothing: a message that quoted no
    strategy counts can never be superseded by an edit to one.
    """
    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)
    revision = conversation_strategy_revision(strategy)
    if not revision:
        return ()
    return (
        strategy_revision_event(revision=revision).model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        ),
    )


def _register_product_stream_parts(registry: StreamPartRegistry) -> None:
    """Every part this product emits: the strategy, EDA and audit surfaces."""
    register_strategy_stream_parts(registry)
    register_eda_stream_parts(registry)
    register_audit_stream_parts(registry)


def _mock_model() -> Model:
    return get_mock_model()


async def _discard_turn_strategy_writes(
    conversation_id: UUID, pre_turn_revision_id: Any
) -> None:
    """Undo the strategy a stopped turn half wrote, back to the prologue's revision."""
    await restore_pre_turn_strategy(
        conversation_id, pre_turn_revision_id=pre_turn_revision_id
    )


def build_strategist_spec() -> AssistantSpec:
    return AssistantSpec(
        assistant_id=STRATEGIST_ASSISTANT_ID,
        build_graph=build_strategist_graph,
        build_initial_state=build_initial_state,
        build_turn_context=build_turn_context,
        build_mock_model=_mock_model,
        checkpoint_types=STRATEGIST_CHECKPOINT_TYPES,
        register_stream_parts=_register_product_stream_parts,
        memory_kinds=frozenset(MEMORY_KINDS),
        identity_gate=require_registered_wdk_login,
        turn_epilogue=strategy_revision_chunks,
        turn_prologue=turn_start_revision_id,
        turn_cancel=_discard_turn_strategy_writes,
        tool_sources=(RESEARCH_TOOL_SOURCE,),
    )


__all__ = [
    "STRATEGIST_CHECKPOINT_TYPES",
    "build_initial_state",
    "build_strategist_spec",
    "build_turn_context",
    "strategy_revision_chunks",
]
