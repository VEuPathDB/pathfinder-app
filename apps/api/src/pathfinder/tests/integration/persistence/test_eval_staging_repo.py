"""The staging queue: what a row carries, and what promotion takes away."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.evals.extract import (
    EvalExtract,
    ExtractedStrategy,
    ExtractedTurn,
    ExtractedVerification,
)
from pathfinder.persistence.models import EvalStagedCase, User
from pathfinder.persistence.repositories.eval_staging import EvalStagingRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")


def _extract(request: str = "find kinases") -> EvalExtract:
    return EvalExtract(
        site_id="plasmodb",
        assistant_id="pathfinder",
        turns=[ExtractedTurn(request=request, reply="built it")],
        strategy=ExtractedStrategy(
            record_type="transcript",
            step_count=3,
            structure="(A INTERSECT B)",
            strategy_ast={"recordType": "transcript"},
        ),
        verification=ExtractedVerification(success=True, reason="root size holds"),
    )


@pytest.fixture
async def seeded(
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
    user_id = uuid4()
    conversation_id = uuid4()
    async with session_maker() as session:
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
    return user_id, conversation_id


@pytest.fixture
def repo() -> EvalStagingRepository:
    return EvalStagingRepository(session_factory=async_session_factory)


async def test_a_staged_row_carries_the_user_and_the_thread(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
) -> None:
    user_id, conversation_id = seeded

    staged = await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract(),
    )

    assert staged is not None
    rows = await repo.list_staged()
    assert [row.id for row in rows] == [staged]


async def test_the_same_conversation_stages_once(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
) -> None:
    user_id, conversation_id = seeded
    await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract(),
    )

    again = await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract("find proteases"),
    )

    assert again is None
    assert len(await repo.list_staged()) == 1


async def test_the_same_content_stages_once_across_threads(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, conversation_id = seeded
    other_conversation = uuid4()
    async with session_maker() as session:
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=other_conversation,
                user_id=user_id,
                site_id="plasmodb",
            ),
        )
        await session.commit()
    await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract(),
    )

    again = await repo.stage(
        user_id=user_id,
        conversation_id=other_conversation,
        extract=_extract(),
    )

    assert again is None


async def test_promotion_removes_the_user_and_the_thread_and_the_extract(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
) -> None:
    user_id, conversation_id = seeded
    staged = await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract(),
    )
    assert staged is not None

    await repo.promote(staging_id=staged, corpus_name="a-case")

    row = await repo.get(staged)
    assert row is not None
    assert row.user_id is None
    assert row.source_conversation_id is None
    assert row.extract is None
    assert row.status == "promoted"
    assert row.corpus_name == "a-case"
    assert row.site_id == "plasmodb"


async def test_a_promoted_row_is_no_longer_staged(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
) -> None:
    user_id, conversation_id = seeded
    staged = await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract(),
    )
    assert staged is not None
    await repo.promote(staging_id=staged, corpus_name="a-case")

    assert await repo.list_staged() == []


async def test_a_promoted_thread_does_not_stage_again(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
) -> None:
    """The content hash survives promotion, so the same case cannot come back."""
    user_id, conversation_id = seeded
    staged = await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract(),
    )
    assert staged is not None
    await repo.promote(staging_id=staged, corpus_name="a-case")

    again = await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract(),
    )

    assert again is None


async def test_deleting_the_user_deletes_their_staged_rows(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, conversation_id = seeded
    staged = await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract(),
    )
    assert staged is not None

    async with session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        await session.delete(user)
        await session.commit()

    assert await repo.get(staged) is None


async def test_the_database_refuses_a_promoted_row_that_still_names_a_user(
    seeded: tuple[UUID, UUID],
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The linkage rule is a constraint, not a convention."""
    user_id, conversation_id = seeded

    async with session_maker() as session:
        session.add(
            EvalStagedCase(
                id=uuid4(),
                user_id=user_id,
                source_conversation_id=conversation_id,
                site_id="plasmodb",
                assistant_id="pathfinder",
                content_hash="f" * 64,
                extract=None,
                status="promoted",
            ),
        )
        with pytest.raises(IntegrityError, match="linkage_ends_at_promotion"):
            await session.commit()


async def test_a_rated_message_stages_beside_the_thread_s_own_row(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
) -> None:
    user_id, conversation_id = seeded
    await repo.stage(
        user_id=user_id, conversation_id=conversation_id, extract=_extract()
    )
    first, second = uuid4(), uuid4()

    rated = [
        await repo.stage(
            user_id=user_id,
            conversation_id=conversation_id,
            extract=_extract(request),
            rated_message_id=message_id,
        )
        for request, message_id in (
            ("find proteases", first),
            ("find kinesins", second),
        )
    ]
    again = await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract("find something else"),
        rated_message_id=first,
    )

    assert None not in rated
    assert again is None
    staged = await repo.list_staged()
    assert sorted(str(row.rated_message_id) for row in staged) == sorted(
        ["None", str(first), str(second)]
    )


async def test_a_rated_stage_of_known_content_marks_the_thread_s_row(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
) -> None:
    """The dislike is kept on the row extraction already queued for that content."""
    user_id, conversation_id = seeded
    staged = await repo.stage(
        user_id=user_id, conversation_id=conversation_id, extract=_extract()
    )
    message_id = uuid4()

    marked = await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract(),
        rated_message_id=message_id,
    )

    assert staged is not None
    assert marked == staged
    row = await repo.get(staged)
    assert row is not None
    assert row.rated_message_id == message_id


async def test_unstaging_a_rated_message_removes_only_its_staged_row(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
) -> None:
    user_id, conversation_id = seeded
    thread_row = await repo.stage(
        user_id=user_id, conversation_id=conversation_id, extract=_extract()
    )
    message_id = uuid4()
    await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract("find proteases"),
        rated_message_id=message_id,
    )

    removed = await repo.unstage_rated(message_id)

    assert removed == 1
    assert [row.id for row in await repo.list_staged()] == [thread_row]


async def test_promotion_ends_the_rated_message_handle(
    repo: EvalStagingRepository,
    seeded: tuple[UUID, UUID],
) -> None:
    user_id, conversation_id = seeded
    message_id = uuid4()
    staged = await repo.stage(
        user_id=user_id,
        conversation_id=conversation_id,
        extract=_extract(),
        rated_message_id=message_id,
    )
    assert staged is not None

    await repo.promote(staging_id=staged, corpus_name="a-disliked-case")

    row = await repo.get(staged)
    assert row is not None
    assert row.rated_message_id is None
    assert row.status == "promoted"
    assert await repo.unstage_rated(message_id) == 0
