"""PathFinder as one assistant: its graph, state, parts, memory and identity."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from assistant_core.conversation.stream_parts.registry import StreamPartRegistry
from assistant_core.platform.db import async_session_factory
from assistant_core.spec import AssistantSpec, TurnContextRequest, TurnStart
from pydantic_ai.models import Model
from veupathdb.domain.strategy.build_outcome import (
    BuildOutcome,
    NodeResult,
    StepPushFailure,
)
from veupathdb.domain.strategy.constraints import ConstraintKind, ConstraintSource
from veupathdb.domain.strategy.operational_spec import OperationalSpec
from veupathdb.domain.strategy.ops import CombineOp

from pathfinder.ai.agents.state import SearchOverview
from pathfinder.ai.eda_stream_parts import register_eda_stream_parts
from pathfinder.ai.graph.builder import build_pathfinder_graph
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.graph.stream_events import strategy_revision_event
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.memory_candidates import PRODUCT_MEMORY_KINDS
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.ai.strategy_stream_parts import register_strategy_stream_parts
from pathfinder.assistants._stub_services import (
    StubLiteratureSearchService,
    StubWebSearchService,
)
from pathfinder.domain.strategy.staleness import StaleBuild
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.responses import conversation_strategy_revision
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.web_search import WebSearchService
from pathfinder.services.strategies.session_factory import (
    build_strategy_session,
    persisted_graph,
)
from pathfinder.services.wdk_identity import require_registered_wdk_login

PATHFINDER_ASSISTANT_ID = "pathfinder"

PATHFINDER_CHECKPOINT_TYPES: tuple[type, ...] = (
    SearchOverview,
    PhaseDisposition,
    VerificationDigest,
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
    is_mock = get_settings().pathfinder_chat_provider.strip().lower() == "mock"
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
        web_search_service=StubWebSearchService() if is_mock else WebSearchService(),
        literature_search_service=(
            StubLiteratureSearchService() if is_mock else LiteratureSearchService()
        ),
        cancel_event=request.cancel_event,
        memory_store=request.memory_store,
        experiment_id=None if strategy is None else strategy.experiment_id,
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
    """Every part this product emits: the strategy surface and the EDA surface."""
    register_strategy_stream_parts(registry)
    register_eda_stream_parts(registry)


def _mock_model() -> Model:
    return get_mock_model()


def build_pathfinder_spec() -> AssistantSpec:
    return AssistantSpec(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        build_graph=build_pathfinder_graph,
        build_initial_state=build_initial_state,
        build_turn_context=build_turn_context,
        build_mock_model=_mock_model,
        checkpoint_types=PATHFINDER_CHECKPOINT_TYPES,
        register_stream_parts=_register_product_stream_parts,
        memory_kinds=frozenset(PRODUCT_MEMORY_KINDS),
        identity_gate=require_registered_wdk_login,
        turn_epilogue=strategy_revision_chunks,
    )


__all__ = [
    "PATHFINDER_ASSISTANT_ID",
    "PATHFINDER_CHECKPOINT_TYPES",
    "build_initial_state",
    "build_pathfinder_spec",
    "build_turn_context",
    "strategy_revision_chunks",
]
