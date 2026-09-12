"""What a finished PathFinder turn is worth remembering.

Turns the turn's spec, gene sets and verification digest into memory
candidates with deterministic keys, so a later turn updates a memory rather
than duplicating it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from assistant_core.memory.autowrite import MemoryCandidate
from assistant_core.memory.schemas import MemoryEntryDraft, MemoryValue
from assistant_core.memory.tombstones import SessionFactory
from assistant_core.persistence.models import Conversation, Message
from assistant_core.platform.context import calling_application
from assistant_core.platform.db import async_session_factory
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.case_memory import collect_case_candidates
from pathfinder.ai.lead.intent import BUILDING_INTENTS

__all__ = [
    "collect_memory_candidates",
    "collect_turn_memory_candidates",
]

PREFERENCE_MIN_SUCCESSES = 3


def _asked_to_build(domain: StrategyDomainState) -> bool:
    """Whether the turn's classification asks for a change to the strategy.

    A turn the model never classified keeps the strategy memory it earns from
    the spec alone.
    """
    intent = domain.user_intent
    return intent is None or intent.classification in BUILDING_INTENTS


def collect_memory_candidates(state: PipelineState) -> list[MemoryCandidate]:
    """The strategies, gene sets and verification findings of one turn."""
    domain = state.domain
    candidates: list[MemoryCandidate] = []
    if (
        domain.operational_spec is not None
        and domain.operational_spec.criteria
        and _asked_to_build(domain)
    ):
        candidates.append(
            (
                _build_strategy_value(state),
                f"strategy:{state.conversation_id.hex}",
            )
        )
    candidates.extend(
        (_build_gene_set_value(state, gs_id), f"gene_set_note:{gs_id}")
        for gs_id in domain.created_gene_set_ids
    )
    if domain.verification_digest is not None:
        for idx, entry in enumerate(domain.verification_digest.remember):
            candidates.append(
                (
                    _build_knowledge_value(state, entry),
                    f"knowledge:{state.conversation_id.hex}:{idx}",
                )
            )
    candidates.extend(collect_case_candidates(state))
    return candidates


async def collect_turn_memory_candidates(
    state: PipelineState,
    *,
    session_factory: SessionFactory = async_session_factory,
) -> list[MemoryCandidate]:
    """Every candidate of one turn, including the site preference the user
    earns after enough successful verifications."""
    candidates = collect_memory_candidates(state)
    if not state.site_id:
        return candidates
    earned = await _has_min_successful_verifications(
        user_id=state.user_id,
        session_factory=session_factory,
        threshold=PREFERENCE_MIN_SUCCESSES,
    )
    if earned:
        candidates.append(
            (_build_preference_value(state), f"preferred_site:{state.site_id}")
        )
    return candidates


def _build_strategy_value(state: PipelineState) -> MemoryValue:
    spec = state.domain.operational_spec
    if spec is None:
        msg = "_build_strategy_value requires state.domain.operational_spec to be set"
        raise ValueError(msg)
    return MemoryValue(
        kind="strategy",
        name=f"chat-{state.conversation_id.hex[:8]}",
        summary=_summarize_spec(state),
        tags=_spec_tags(state),
        site_id=state.site_id,
        content={
            "spec": spec.model_dump(mode="json"),
            "user_prompt": state.user_prompt,
        },
        source_conversation_id=state.conversation_id,
        created_at=datetime.now(UTC),
    )


def _build_gene_set_value(state: PipelineState, gs_id: str) -> MemoryValue:
    return MemoryValue(
        kind="gene_set_note",
        name=gs_id,
        summary=f"Gene set {gs_id} created in chat-{state.conversation_id.hex[:8]}",
        tags=[state.site_id] if state.site_id else [],
        site_id=state.site_id,
        content={"gene_set_id": gs_id},
        source_conversation_id=state.conversation_id,
        created_at=datetime.now(UTC),
    )


def _build_knowledge_value(
    state: PipelineState,
    entry: MemoryEntryDraft,
) -> MemoryValue:
    """Lift a verification-authored draft to a full ``MemoryValue``.

    Site id and source conversation id come from pipeline state. The draft
    does not author them, so the LLM cannot cross-link to a different chat.
    """
    tags = list(entry.tags)
    if state.site_id and state.site_id not in tags:
        tags.append(state.site_id)
    return MemoryValue(
        kind="knowledge",
        name=entry.name,
        summary=entry.summary,
        tags=tags,
        site_id=state.site_id,
        content=dict(entry.content),
        source_conversation_id=state.conversation_id,
        created_at=datetime.now(UTC),
    )


def _build_preference_value(state: PipelineState) -> MemoryValue:
    return MemoryValue(
        kind="preference",
        name=f"preferred_site:{state.site_id}",
        summary=f"Frequently uses {state.site_id}",
        tags=[state.site_id] if state.site_id else [],
        site_id=state.site_id,
        content={"preferred_site": state.site_id},
        source_conversation_id=state.conversation_id,
        created_at=datetime.now(UTC),
    )


async def _has_min_successful_verifications(
    *,
    user_id: UUID,
    session_factory: SessionFactory,
    threshold: int,
) -> bool:
    """Return True iff the user has ``>= threshold`` successful verifications.

    Uses EXISTS with LIMIT to avoid an unbounded COUNT(*) over the user's full
    message history. The query is O(threshold) rows in the worst case.
    """
    async with session_factory() as session:
        return await _check_verifications_threshold(session, user_id, threshold)


async def _check_verifications_threshold(
    session: AsyncSession,
    user_id: UUID,
    threshold: int,
) -> bool:
    inner = (
        select(Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == user_id,
            Conversation.application_id == calling_application(),
            Message.role == "assistant",
            Message.metadata_["phase"].as_string() == "verification",
            Message.metadata_["turnCompleted"].as_boolean().is_(True),
        )
        .limit(threshold)
    ).subquery()
    row_count_stmt = select(
        exists().select_from(select(inner.c.id).offset(threshold - 1).subquery())
    )
    result = await session.execute(row_count_stmt)
    return bool(result.scalar())


def _summarize_spec(state: PipelineState) -> str:
    spec = state.domain.operational_spec
    if spec and spec.interpreted_goal:
        return spec.interpreted_goal[:120]
    if spec and spec.goal:
        return spec.goal[:120]
    return state.user_prompt[:120]


def _spec_tags(state: PipelineState) -> list[str]:
    tags = [state.site_id] if state.site_id else []
    spec = state.domain.operational_spec
    if spec and spec.organism_scope:
        tags.append(spec.organism_scope)
    return tags
