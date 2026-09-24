"""A disliked message stages one eval case: the thread cut at that message."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.ui_message_reducer import user_message_chunk
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation, ConversationEvent, Message
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import JSONObject
from pydantic_ai.ui.vercel_ai.response_types import TextDeltaChunk
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.devtools import evals
from pathfinder.domain.message_rating import Rating
from pathfinder.evals.case import ExpectedOutcome
from pathfinder.persistence.models import StrategyRevision, User
from pathfinder.persistence.repositories.eval_staging import EvalStagingRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.message_ratings import (
    clear_message_rating,
    rate_message,
)
from pathfinder.services.eval_data.curation import (
    PromotionEdits,
    promote_staged_case,
    staged_extract,
)
from pathfinder.services.eval_data.extraction import extract_eval_candidates

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_FIRST_AST: JSONObject = {
    "recordType": "transcript",
    "root": {
        "id": "step_root",
        "searchName": "__combine__",
        "operator": "INTERSECT",
        "primaryInput": {"id": "step_a", "searchName": "GenesByText"},
        "secondaryInput": {"id": "step_b", "searchName": "GenesByTaxon"},
    },
}
_SECOND_AST: JSONObject = {
    "recordType": "transcript",
    "root": {"id": "step_a", "searchName": "GenesByText"},
}
_T0 = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


@dataclass(frozen=True)
class _Thread:
    user_id: UUID
    conversation_id: UUID
    first_reply: UUID
    second_reply: UUID


def _reply_chunk(text: str) -> JSONObject:
    return TextDeltaChunk(id="lead-prose-1", delta=text).model_dump(
        by_alias=True, mode="json", exclude_none=True
    )


async def _seed_turn(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    request: str,
    reply: str,
    at: datetime,
) -> UUID:
    """One exchange: the log rows, both message rows and no verdict."""
    user_message = uuid4()
    reply_message = uuid4()
    session.add(
        ConversationEvent(
            conversation_id=conversation_id,
            turn_id=user_message,
            chunk=user_message_chunk(
                message_id=str(user_message),
                parts=[{"type": "text", "text": request}],
            ),
        ),
    )
    session.add(
        ConversationEvent(
            conversation_id=conversation_id,
            turn_id=reply_message,
            chunk=_reply_chunk(reply),
        ),
    )
    session.add(
        Message(
            id=user_message,
            conversation_id=conversation_id,
            role="user",
            metadata_={},
            created_at=at,
        ),
    )
    session.add(
        Message(
            id=reply_message,
            conversation_id=conversation_id,
            role="assistant",
            metadata_={"traceId": str(uuid4())},
            created_at=at + timedelta(seconds=30),
        ),
    )
    await session.flush()
    return reply_message


async def _seed(
    session_maker: async_sessionmaker[AsyncSession], *, consent: bool = True
) -> _Thread:
    user_id = uuid4()
    conversation_id = uuid4()
    async with session_maker() as session:
        session.add(User(id=user_id, eval_data_consent=consent))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
            ),
        )
        await session.flush()
        first = await _seed_turn(
            session,
            conversation_id=conversation_id,
            request="find kinases",
            reply="Built an intersect of 142.",
            at=_T0,
        )
        second = await _seed_turn(
            session,
            conversation_id=conversation_id,
            request="drop the organism",
            reply="Kept only the text search.",
            at=_T0 + timedelta(minutes=5),
        )
        for revision, ast, steps, message_id in (
            ("r1", _FIRST_AST, 3, first),
            ("r2", _SECOND_AST, 1, second),
        ):
            session.add(
                StrategyRevision(
                    conversation_id=conversation_id,
                    revision=revision,
                    record_type="transcript",
                    strategy_ast=ast,
                    step_count=steps,
                    message_id=message_id,
                ),
            )
        await session.commit()
    return _Thread(user_id, conversation_id, first, second)


@pytest.fixture
async def store() -> AsyncIterator[MemoryStore]:
    async with lifespan_memory_store(os.environ["DATABASE_URL"]) as raw:
        yield MemoryStore(store=raw)


@pytest.fixture
def staging() -> EvalStagingRepository:
    return EvalStagingRepository(session_factory=async_session_factory)


async def _rate(
    thread: _Thread, store: MemoryStore, message_id: UUID, rating: Rating | None
) -> None:
    if rating is None:
        await clear_message_rating(
            store=store,
            user_id=thread.user_id,
            conversation_id=thread.conversation_id,
            message_id=message_id,
        )
        return
    await rate_message(
        store=store,
        user_id=thread.user_id,
        conversation_id=thread.conversation_id,
        message_id=message_id,
        rating=rating,
    )


async def test_a_dislike_stages_the_thread_cut_at_that_message(
    session_maker: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    staging: EvalStagingRepository,
) -> None:
    thread = await _seed(session_maker)

    await _rate(thread, store, thread.first_reply, "dislike")

    rows = await staging.list_staged()
    assert len(rows) == 1
    row = rows[0]
    assert row.source_conversation_id == thread.conversation_id
    assert row.rated_message_id == thread.first_reply
    extract = staged_extract(row)
    assert [turn.request for turn in extract.turns] == ["find kinases"]
    assert extract.turns[-1].reply == "Built an intersect of 142."
    assert extract.verification is None
    assert extract.strategy is not None
    assert extract.strategy.structure == "(GenesByText INTERSECT GenesByTaxon)"
    assert extract.strategy.step_count == 3


async def test_a_rating_flipped_back_and_forth_stages_one_row(
    session_maker: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    staging: EvalStagingRepository,
) -> None:
    thread = await _seed(session_maker)

    ratings: tuple[Rating, ...] = ("dislike", "like", "dislike")
    for rating in ratings:
        await _rate(thread, store, thread.second_reply, rating)

    rows = await staging.list_staged()
    assert [row.rated_message_id for row in rows] == [thread.second_reply]
    assert [turn.request for turn in staged_extract(rows[0]).turns] == [
        "find kinases",
        "drop the organism",
    ]


@pytest.mark.parametrize("after", ["like", None])
async def test_a_like_or_a_clear_removes_the_staged_row(
    session_maker: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    staging: EvalStagingRepository,
    after: Rating | None,
) -> None:
    thread = await _seed(session_maker)
    await _rate(thread, store, thread.first_reply, "dislike")

    await _rate(thread, store, thread.first_reply, after)

    assert await staging.list_staged() == []


async def test_a_non_consenting_user_s_dislike_stages_nothing(
    session_maker: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    staging: EvalStagingRepository,
) -> None:
    thread = await _seed(session_maker, consent=False)

    rated = await rate_message(
        store=store,
        user_id=thread.user_id,
        conversation_id=thread.conversation_id,
        message_id=thread.first_reply,
        rating="dislike",
    )

    assert rated.rating == "dislike"
    assert await staging.list_staged() == []


async def test_two_disliked_messages_on_one_thread_stage_two_rows(
    session_maker: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    staging: EvalStagingRepository,
) -> None:
    thread = await _seed(session_maker)

    await _rate(thread, store, thread.first_reply, "dislike")
    await _rate(thread, store, thread.second_reply, "dislike")

    rows = await staging.list_staged()
    assert sorted(len(staged_extract(row).turns) for row in rows) == [1, 2]


async def test_the_nightly_pass_skips_a_thread_that_holds_a_dislike(
    session_maker: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    staging: EvalStagingRepository,
) -> None:
    thread = await _seed(session_maker)
    await _rate(thread, store, thread.first_reply, "dislike")

    report = await extract_eval_candidates()

    assert report.staged == 0
    assert len(await staging.list_staged()) == 1


async def test_promotion_ends_the_message_handle_and_needs_an_expectation(
    session_maker: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    staging: EvalStagingRepository,
    tmp_path: Path,
) -> None:
    thread = await _seed(session_maker)
    await _rate(thread, store, thread.first_reply, "dislike")
    staging_id = (await staging.list_staged())[0].id

    with pytest.raises(ValueError, match="state what the case expects"):
        await promote_staged_case(
            staging=staging,
            staging_id=staging_id,
            edits=PromotionEdits(name="a-disliked-case", rationale="wrong operator"),
            directory=tmp_path,
        )
    await promote_staged_case(
        staging=staging,
        staging_id=staging_id,
        edits=PromotionEdits(
            name="a-disliked-case",
            rationale="wrong operator",
            expected=ExpectedOutcome(builds_strategy=True, step_count=3),
        ),
        directory=tmp_path,
    )

    promoted = await staging.get(staging_id)
    assert promoted is not None
    assert promoted.rated_message_id is None
    assert promoted.source_conversation_id is None


async def test_the_curation_desk_names_the_disliked_turn(
    session_maker: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    staging: EvalStagingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    thread = await _seed(session_maker)
    await _rate(thread, store, thread.second_reply, "dislike")
    staging_id = (await staging.list_staged())[0].id

    assert await evals._show(staging_id) == 0

    printed = capsys.readouterr().out
    assert "origin     : disliked turn 2" in printed
    assert '"buildsStrategy": null' in printed


async def test_a_strategy_that_does_not_parse_stages_with_its_texts_redacted(
    session_maker: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    staging: EvalStagingRepository,
) -> None:
    thread = await _seed(session_maker)
    async with session_maker() as session:
        session.add(
            StrategyRevision(
                conversation_id=thread.conversation_id,
                revision="r1-unparsed",
                record_type="transcript",
                strategy_ast={
                    "recordType": "transcript",
                    "description": "send the list to ada@example.org",
                    "root": {"id": "step_a"},
                },
                step_count=1,
                message_id=thread.first_reply,
            ),
        )
        await session.commit()

    rated = await rate_message(
        store=store,
        user_id=thread.user_id,
        conversation_id=thread.conversation_id,
        message_id=thread.first_reply,
        rating="dislike",
    )

    assert rated.rating == "dislike"
    [row] = await staging.list_staged()
    strategy = staged_extract(row).strategy
    assert strategy is not None
    assert strategy.strategy_ast["description"] == "send the list to [redacted-email]"
