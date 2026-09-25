"""A disliked turn's case leaves the store, and a liked turn's case is pinned."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.memory.retrieval import RetrievalScope, retrieve_relevant_memories
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation, ConversationEvent
from assistant_core.platform.db import async_session_factory
from langgraph.runtime import Runtime
from langgraph.store.postgres.aio import AsyncPostgresStore
from sqlalchemy import func, select
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.graph import nodes
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.domain.message_rating import Rating
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.persistence.models import MessageRating, MessageRatingView, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.message_ratings import (
    clear_message_rating,
    rate_message,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

GOAL = "find every kinase in P. falciparum"


@dataclass(frozen=True)
class _Thread:
    user_id: UUID
    conversation_id: UUID
    store: MemoryStore
    raw: AsyncPostgresStore


def _state(thread: _Thread, message_id: UUID, *, verified: bool) -> PipelineState:
    spec = OperationalSpec(
        goal="kinases",
        interpreted_goal="Plasmodium falciparum kinases",
        criteria=[
            Criterion(
                id="s1",
                text="kinase domain",
                search_name="GenesByGoTerm",
                role="seed",
                resolved_params={"go_term": StringValue(value="GO:0004672")},
            ),
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="s1")),
    )
    state = PipelineState(
        conversation_id=thread.conversation_id,
        user_id=thread.user_id,
        site_id="plasmodb",
        mode="strategy",
        user_prompt="find the kinases",
        domain=StrategyDomainState(
            operational_spec=spec,
            answered_spec=spec.model_copy(deep=True),
            original_request=GOAL,
            last_build_outcome=BuildOutcome(
                pushed_step_ids=["s1"],
                wdk_strategy_id=330423363,
                counts={"s1": 142},
                root_count=142,
                node_results=[
                    NodeResult(
                        node_id="s1",
                        search_name="GenesByGoTerm",
                        count=142,
                        status="ok",
                    ),
                ],
            ),
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="142 kinases",
                reason="verified",
                success=True,
            ),
        ),
        turn_message_id=message_id,
    )
    state.turn_markers.verification_dispatched = verified
    return state


async def _run_turn(
    thread: _Thread,
    *,
    message_id: UUID | None = None,
    verified: bool = True,
) -> UUID:
    """Log one reply under the message id, then finalize the turn."""
    turn_id = message_id or uuid4()
    async with async_session_factory() as session:
        cursor = await session.scalar(
            select(func.coalesce(func.max(ConversationEvent.id), 0)),
        )
        for chunk in (
            {"type": "start", "messageId": str(turn_id)},
            {"type": "text-start", "id": "t"},
            {"type": "text-delta", "id": "t", "delta": "142 kinases."},
            {"type": "text-end", "id": "t"},
        ):
            session.add(
                ConversationEvent(
                    conversation_id=thread.conversation_id,
                    turn_id=turn_id,
                    chunk=chunk,
                ),
            )
        await session.commit()
    state = _state(thread, turn_id, verified=verified)
    state.turn_start_event_id = int(cursor or 0)
    context = Context(
        site_id="plasmodb",
        user_id=thread.user_id,
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=async_session_factory,
        cancel_event=asyncio.Event(),
        memory_store=thread.raw,
    )
    await nodes.finalize_turn_node(state, Runtime(context=context))
    return turn_id


async def _rate(thread: _Thread, message_id: UUID, rating: Rating | None) -> None:
    if rating is None:
        await clear_message_rating(
            store=thread.store,
            user_id=thread.user_id,
            conversation_id=thread.conversation_id,
            message_id=message_id,
        )
        return
    await rate_message(
        store=thread.store,
        user_id=thread.user_id,
        conversation_id=thread.conversation_id,
        message_id=message_id,
        rating=rating,
    )


async def _cases(thread: _Thread) -> list[tuple[str, list[str]]]:
    stored = await thread.store.list_all(user_id=thread.user_id, kind="case")
    return [(memory.key, memory.value.tags) for memory in stored]


@pytest.fixture
async def no_compaction(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _skip(**kwargs: Any) -> None:
        del kwargs

    monkeypatch.setattr(nodes, "compact_scratchpad", _skip)


@pytest.fixture
async def thread(no_compaction: None) -> AsyncIterator[_Thread]:
    del no_compaction
    user_id = uuid4()
    conversation_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
            ),
        )
        await session.commit()
    async with lifespan_memory_store(os.environ["DATABASE_URL"]) as raw:
        yield _Thread(user_id, conversation_id, MemoryStore(store=raw), raw)


async def test_a_dislike_takes_the_turn_s_case_out_of_the_store(
    thread: _Thread,
) -> None:
    message_id = await _run_turn(thread)
    [(key, _tags)] = await _cases(thread)

    await _rate(thread, message_id, "dislike")

    assert await thread.store.get(user_id=thread.user_id, kind="case", key=key) is None
    assert (
        await thread.store.semantic_search(
            user_id=thread.user_id, kind="case", query=GOAL
        )
        == []
    )


async def test_a_later_turn_reaching_a_disliked_case_writes_nothing(
    thread: _Thread,
) -> None:
    first = await _run_turn(thread)
    await _rate(thread, first, "dislike")

    await _run_turn(thread)

    assert await _cases(thread) == []


async def test_a_like_pins_the_case_and_it_ranks_above_an_equal_one(
    thread: _Thread,
) -> None:
    message_id = await _run_turn(thread)
    [(key, _tags)] = await _cases(thread)
    stored = await thread.store.get(user_id=thread.user_id, kind="case", key=key)
    assert stored is not None
    await thread.store.put(
        user_id=thread.user_id, value=stored.value, key="case:unrated-copy"
    )

    await _rate(thread, message_id, "like")

    liked = await thread.store.get(user_id=thread.user_id, kind="case", key=key)
    assert liked is not None
    assert liked.value.tags == ["plasmodb", "pinned"]
    ranked = await retrieve_relevant_memories(
        store=thread.store,
        user_id=thread.user_id,
        query=GOAL,
        scope=RetrievalScope(kinds=("case",)),
    )
    assert [memory.key for memory in ranked] == [key, "case:unrated-copy"]


async def test_a_later_turn_reaching_a_liked_case_writes_it_pinned(
    thread: _Thread,
) -> None:
    first = await _run_turn(thread)
    await _rate(thread, first, "like")

    await _run_turn(thread)

    assert [tags for _key, tags in await _cases(thread)] == [["plasmodb", "pinned"]]


@pytest.mark.parametrize(
    ("then", "tags"),
    [(None, ["plasmodb"]), ("like", ["plasmodb", "pinned"])],
)
async def test_a_dislike_taken_back_puts_the_case_back(
    thread: _Thread,
    then: Rating | None,
    tags: list[str],
) -> None:
    message_id = await _run_turn(thread)
    await _rate(thread, message_id, "dislike")

    await _rate(thread, message_id, then)

    assert [found for _key, found in await _cases(thread)] == [tags]


async def test_a_parked_turn_disliked_before_its_continuation_writes_no_case(
    thread: _Thread,
) -> None:
    """The continuation finalizes the same message and keeps its case withheld."""
    message_id = await _run_turn(thread, verified=False)
    await _rate(thread, message_id, "dislike")

    await _run_turn(thread, message_id=message_id)

    assert await _cases(thread) == []
    async with async_session_factory() as session:
        row = await session.scalar(
            select(MessageRating).where(MessageRating.message_id == message_id)
        )
    assert row is not None
    view = MessageRatingView.model_validate(row)
    assert [case.key for case in view.withheld_cases] == view.case_keys
    assert len(view.case_keys) == 1

    await _rate(thread, message_id, None)

    assert [tags for _key, tags in await _cases(thread)] == [["plasmodb"]]


async def test_a_like_on_a_turn_that_wrote_no_case_changes_no_memory(
    thread: _Thread,
) -> None:
    message_id = await _run_turn(thread, verified=False)

    await _rate(thread, message_id, "like")

    assert await _cases(thread) == []
