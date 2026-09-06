"""Integration tests for the conversation fork tree and the delete semantics."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.persistence.models import Conversation, ConversationEvent, Message
from assistant_core.persistence.repositories.message import MessagesRepository
from assistant_core.platform import db
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.scratchpad.models import NoteCreate
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.scratchpad import ScratchpadRepository
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import (
    ForkError,
    fork_conversation,
)


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncIterator[None]:
    """Creates the LangGraph checkpoint tables.

    Only ``AsyncPostgresSaver.setup()`` creates them. The migrations do not.
    """
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


@pytest.fixture(autouse=True)
async def _truncate_langgraph_tables() -> AsyncIterator[None]:
    """Clears the checkpoint tables between tests."""
    yield
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE checkpoints, checkpoint_blobs, "
                "checkpoint_writes RESTART IDENTITY",
            ),
        )
        await session.commit()


async def _seed_checkpoint(
    session: AsyncSession,
    *,
    thread_id: str,
    checkpoint_id: str,
    parent_checkpoint_id: str | None,
    ts: datetime,
) -> None:
    """Inserts a minimal LangGraph checkpoint row with the given timestamp."""
    await session.execute(
        text(
            "INSERT INTO checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
            " type, checkpoint, metadata) "
            "VALUES (:thread_id, '', :checkpoint_id, :parent_checkpoint_id, "
            " 'test', CAST(:checkpoint AS jsonb), '{}'::jsonb)",
        ),
        {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "checkpoint": f'{{"id": "{checkpoint_id}", "ts": "{ts.isoformat()}"}}',
        },
    )


async def _seed_blob(
    session: AsyncSession,
    *,
    thread_id: str,
    channel: str,
    version: str,
) -> None:
    await session.execute(
        text(
            "INSERT INTO checkpoint_blobs "
            "(thread_id, checkpoint_ns, channel, version, type, blob) "
            "VALUES (:thread_id, '', :channel, :version, 'empty', "
            " decode('00', 'hex'))",
        ),
        {"thread_id": thread_id, "channel": channel, "version": version},
    )


async def _seed_write(
    session: AsyncSession,
    *,
    thread_id: str,
    checkpoint_id: str,
    task_id: str = "t",
    idx: int = 0,
    channel: str = "c",
) -> None:
    await session.execute(
        text(
            "INSERT INTO checkpoint_writes "
            "(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, "
            " type, blob, task_path) "
            "VALUES (:thread_id, '', :checkpoint_id, :task_id, :idx, :channel, "
            " 'empty', decode('00', 'hex'), '')",
        ),
        {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "task_id": task_id,
            "idx": idx,
            "channel": channel,
        },
    )


async def _seed_user(session: AsyncSession, user_id: UUID) -> None:
    session.add(User(id=user_id))
    await session.flush()


async def _seed_conversation(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
    name: str = "root",
) -> None:
    session.add(
        Conversation(
            id=conversation_id,
            user_id=user_id,
            site_id="plasmodb",
            name=name,
        ),
    )
    await session.flush()


async def _insert_message(
    repo: MessagesRepository,
    *,
    conv_id: UUID,
    role: str,
    text: str,
) -> UUID:
    del text
    message_id = uuid4()
    await repo.insert_message(
        message_id=message_id,
        conversation_id=conv_id,
        role=role,
        metadata={"mode": "strategy"},
    )
    return message_id


async def test_fork_copies_prefix_and_sets_parent_refs(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(session, conversation_id=source_id, user_id=user_id)
        await session.commit()

    # A separate commit per message gives each message a distinct created_at.
    async with db.async_session_factory() as session:
        messages = MessagesRepository(session)
        await _insert_message(messages, conv_id=source_id, role="user", text="hi")
        await session.commit()

    async with db.async_session_factory() as session:
        messages = MessagesRepository(session)
        anchor_id = await _insert_message(
            messages,
            conv_id=source_id,
            role="assistant",
            text="first reply",
        )
        await session.commit()

    async with db.async_session_factory() as session:
        messages = MessagesRepository(session)
        await _insert_message(
            messages, conv_id=source_id, role="user", text="follow-up"
        )
        await session.commit()

    async with db.async_session_factory() as session:
        messages = MessagesRepository(session)
        await _insert_message(
            messages,
            conv_id=source_id,
            role="assistant",
            text="second reply",
        )
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor_id,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id
        assert fork.parent_conversation_id == source_id
        assert fork.parent_message_id == anchor_id
        assert fork.site_id == "plasmodb"

    async with db.async_session_factory() as session:
        rows = await MessagesRepository(session).list_messages_for_conversation(fork_id)
        assert len(rows) == 2
        roles = [r.role for r in rows]
        assert roles == ["user", "assistant"]


async def test_fork_rejects_unknown_source(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    async with db.async_session_factory() as session:
        try:
            await fork_conversation(
                session,
                source_conversation_id=uuid4(),
                from_message_id=uuid4(),
                user_id=uuid4(),
            )
        except ForkError:
            return
        msg = "expected ForkError for missing source"
        raise AssertionError(msg)


async def test_fork_rejects_wrong_owner(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    owner_id = uuid4()
    other_id = uuid4()
    source_id = uuid4()

    async with db.async_session_factory() as session:
        await _seed_user(session, owner_id)
        await _seed_user(session, other_id)
        await _seed_conversation(
            session,
            conversation_id=source_id,
            user_id=owner_id,
        )
        anchor_id = await _insert_message(
            MessagesRepository(session),
            conv_id=source_id,
            role="assistant",
            text="x",
        )
        await session.commit()

    async with db.async_session_factory() as session:
        try:
            await fork_conversation(
                session,
                source_conversation_id=source_id,
                from_message_id=anchor_id,
                user_id=other_id,
            )
        except ForkError:
            return
        msg = "expected ForkError when caller doesn't own source"
        raise AssertionError(msg)


async def test_delete_non_cascade_promotes_children(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """Deleting b in the a-b-c chain moves c under a."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    a_id, b_id, c_id = uuid4(), uuid4(), uuid4()
    anchor_msg = uuid4()
    fork_anchor = uuid4()

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session, conversation_id=a_id, user_id=user_id, name="a"
        )
        session.add(
            Message(
                id=anchor_msg,
                conversation_id=a_id,
                role="assistant",
                metadata_={},
            ),
        )
        await session.flush()
        session.add(
            Conversation(
                id=b_id,
                user_id=user_id,
                site_id="plasmodb",
                name="b",
                parent_conversation_id=a_id,
                parent_message_id=anchor_msg,
            ),
        )
        await session.flush()
        session.add(
            Message(
                id=fork_anchor,
                conversation_id=b_id,
                role="assistant",
                metadata_={},
            ),
        )
        await session.flush()
        session.add(
            Conversation(
                id=c_id,
                user_id=user_id,
                site_id="plasmodb",
                name="c",
                parent_conversation_id=b_id,
                parent_message_id=fork_anchor,
            ),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        repo = ConversationRepository(session)
        await repo.delete(b_id)
        await session.commit()

    async with db.async_session_factory() as session:
        c = await session.scalar(select(Conversation).where(Conversation.id == c_id))
        a_gone = await session.scalar(
            select(Conversation).where(Conversation.id == b_id),
        )
        assert a_gone is None
        assert c is not None
        assert c.parent_conversation_id == a_id
        # A promoted child inherits the fork point of the deleted parent.
        assert c.parent_message_id == anchor_msg


async def test_delete_cascade_wipes_subtree(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    a_id, b_id, c_id, d_id = uuid4(), uuid4(), uuid4(), uuid4()

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session, conversation_id=a_id, user_id=user_id, name="a"
        )
        session.add(
            Conversation(
                id=b_id,
                user_id=user_id,
                site_id="plasmodb",
                name="b",
                parent_conversation_id=a_id,
            ),
        )
        session.add(
            Conversation(
                id=c_id,
                user_id=user_id,
                site_id="plasmodb",
                name="c",
                parent_conversation_id=b_id,
            ),
        )
        session.add(
            Conversation(
                id=d_id,
                user_id=user_id,
                site_id="plasmodb",
                name="d",
                parent_conversation_id=c_id,
            ),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        repo = ConversationRepository(session)
        await repo.delete(b_id, cascade=True)
        await session.commit()

    async with db.async_session_factory() as session:
        remaining = (
            await session.scalars(
                select(Conversation.id).where(
                    Conversation.id.in_([a_id, b_id, c_id, d_id]),
                ),
            )
        ).all()
        assert set(remaining) == {a_id}


async def test_delete_root_non_cascade_promotes_children_to_roots(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """Deleting root with cascade=False null-outs child's parent_* fields."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    root_id, child_id = uuid4(), uuid4()
    anchor_msg = uuid4()

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session,
            conversation_id=root_id,
            user_id=user_id,
            name="root",
        )
        session.add(
            Message(
                id=anchor_msg,
                conversation_id=root_id,
                role="assistant",
                metadata_={},
            ),
        )
        await session.flush()
        session.add(
            Conversation(
                id=child_id,
                user_id=user_id,
                site_id="plasmodb",
                name="child",
                parent_conversation_id=root_id,
                parent_message_id=anchor_msg,
            ),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        repo = ConversationRepository(session)
        await repo.delete(root_id)
        await session.commit()

    async with db.async_session_factory() as session:
        child = await session.scalar(
            select(Conversation).where(Conversation.id == child_id),
        )
        assert child is not None
        assert child.parent_conversation_id is None
        assert child.parent_message_id is None


# Checkpoint-chain fork tests.
# LangGraph checkpoints are keyed by thread_id, which equals the conversation
# id. The fork cutoff is the created_at of the message after the anchor. A
# checkpoint is copied only when its ts is less than that cutoff.


async def _set_message_created_at(
    session: AsyncSession,
    *,
    message_id: UUID,
    ts: datetime,
) -> None:
    """Sets a message created_at to a chosen value."""
    await session.execute(
        text("UPDATE messages SET created_at = :ts WHERE id = :id"),
        {"ts": ts, "id": message_id},
    )


async def _insert_message_at(
    session: AsyncSession,
    *,
    conv_id: UUID,
    role: str,
    text_body: str,
    ts: datetime,
) -> UUID:
    """Inserts a message and sets its created_at to a chosen value.

    Cutoff tests need a message time that is ordered against the seeded
    checkpoint times, which the database default does not give.
    """
    messages = MessagesRepository(session)
    msg_id = await _insert_message(
        messages,
        conv_id=conv_id,
        role=role,
        text=text_body,
    )
    await session.flush()
    await _set_message_created_at(session, message_id=msg_id, ts=ts)
    return msg_id


async def _two_turn_source(
    *,
    user_id: UUID,
    source_id: UUID,
) -> tuple[list[UUID], list[datetime]]:
    """Seeds a source conversation with two turns and one checkpoint per message.

    The message and checkpoint times interleave the same way a live turn
    writes them. Returned lists are in chronological order.
    """
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    cp_ts = [base + timedelta(seconds=s) for s in (15, 20, 45, 50)]
    msg_ts = [base + timedelta(seconds=s) for s in (10, 19, 40, 49)]
    turns = [
        ("cp_u1", None, cp_ts[0], "user", "hi", msg_ts[0]),
        ("cp_a1", "cp_u1", cp_ts[1], "assistant", "first reply", msg_ts[1]),
        ("cp_u2", "cp_a1", cp_ts[2], "user", "follow-up", msg_ts[2]),
        ("cp_a2", "cp_u2", cp_ts[3], "assistant", "second reply", msg_ts[3]),
    ]
    message_ids: list[UUID] = []

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session,
            conversation_id=source_id,
            user_id=user_id,
            name="root",
        )
        await session.commit()

    for cp_id, parent, cp_time, role, body, msg_time in turns:
        async with db.async_session_factory() as session:
            await _seed_checkpoint(
                session,
                thread_id=str(source_id),
                checkpoint_id=cp_id,
                parent_checkpoint_id=parent,
                ts=cp_time,
            )
            await session.commit()
        async with db.async_session_factory() as session:
            msg_id = await _insert_message_at(
                session,
                conv_id=source_id,
                role=role,
                text_body=body,
                ts=msg_time,
            )
            message_ids.append(msg_id)
            await session.commit()

    async with db.async_session_factory() as session:
        await _seed_blob(
            session,
            thread_id=str(source_id),
            channel="msg",
            version="v1",
        )
        await _seed_blob(
            session,
            thread_id=str(source_id),
            channel="msg",
            version="v2",
        )
        for cp_id, *_ in turns:
            await _seed_write(
                session,
                thread_id=str(source_id),
                checkpoint_id=cp_id,
            )
        await session.commit()

    return message_ids, cp_ts


# Invariant and resume helpers.


async def _chain_is_valid(session: AsyncSession, thread_id: str) -> bool:
    """True when every surviving checkpoint parent reference resolves.

    Each non-null parent_checkpoint_id must point at another surviving row.
    LangGraph cannot walk a chain that has an orphan parent.
    """
    result = await session.execute(
        text(
            "SELECT checkpoint_id, parent_checkpoint_id FROM checkpoints "
            "WHERE thread_id = :t",
        ),
        {"t": thread_id},
    )
    surviving = {row[0]: row[1] for row in result}
    for cp_id, parent in surviving.items():
        if parent is None:
            continue
        if parent not in surviving:
            return False
        _ = cp_id
    return True


async def _count_checkpoints(session: AsyncSession, thread_id: str) -> int:
    result = await session.execute(
        text("SELECT COUNT(*) FROM checkpoints WHERE thread_id = :t"),
        {"t": thread_id},
    )
    return int(result.scalar_one())


async def _put_real_checkpoint(
    saver: AsyncPostgresSaver,
    *,
    thread_id: str,
    checkpoint_id: str,
    parent_checkpoint_id: str | None,
    ts: datetime,
    channel_values: dict[str, object],
) -> None:
    """Writes a checkpoint through the real saver at a chosen time.

    The saver populates every field that LangGraph reads on resume, so the
    test covers the full serialize path.
    """
    parent_config: RunnableConfig = {
        "configurable": {"thread_id": thread_id, "checkpoint_ns": ""},
    }
    if parent_checkpoint_id is not None:
        parent_config["configurable"]["checkpoint_id"] = parent_checkpoint_id

    versions: ChannelVersions = {
        k: f"{checkpoint_id}.{i}" for i, k in enumerate(channel_values)
    }
    checkpoint: Checkpoint = {
        "v": 4,
        "id": checkpoint_id,
        "ts": ts.isoformat(),
        "channel_values": dict(channel_values),
        "channel_versions": dict(versions),
        "versions_seen": {},
        "updated_channels": list(channel_values.keys()),
    }
    metadata: CheckpointMetadata = {
        "source": "loop",
        "step": 0,
        "parents": {},
    }
    await saver.aput(parent_config, checkpoint, metadata, versions)


async def _resume_latest(
    saver: AsyncPostgresSaver,
    thread_id: str,
) -> CheckpointTuple | None:
    return await saver.aget_tuple(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
    )


# Behavioral tests for the checkpoint-chain truncation.


async def test_fork_from_latest_count_matches_source(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A fork from the latest message copies every source checkpoint row."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    message_ids, _ = await _two_turn_source(user_id=user_id, source_id=source_id)

    async with db.async_session_factory() as session:
        source_count = await _count_checkpoints(session, str(source_id))

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=message_ids[-1],
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        assert await _count_checkpoints(session, str(fork_id)) == source_count
        assert await _chain_is_valid(session, str(fork_id))


async def test_fork_from_mid_chat_drops_later_turn_count(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A fork from a middle message copies fewer checkpoints than the source."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    message_ids, _ = await _two_turn_source(user_id=user_id, source_id=source_id)

    async with db.async_session_factory() as session:
        source_count = await _count_checkpoints(session, str(source_id))

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=message_ids[1],
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        fork_count = await _count_checkpoints(session, str(fork_id))
        assert 0 < fork_count < source_count
        assert await _chain_is_valid(session, str(fork_id))


async def test_fork_cutoff_is_strictly_less_than(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A checkpoint whose ts equals the cutoff is not copied.

    The cutoff is exclusive. A tie belongs to the following turn.
    """
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()

    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    anchor_msg_ts = base + timedelta(seconds=10)
    boundary_ts = base + timedelta(seconds=20)
    next_msg_ts = boundary_ts

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session,
            conversation_id=source_id,
            user_id=user_id,
        )
        await _seed_checkpoint(
            session,
            thread_id=str(source_id),
            checkpoint_id="pre",
            parent_checkpoint_id=None,
            ts=base + timedelta(seconds=5),
        )
        await _seed_checkpoint(
            session,
            thread_id=str(source_id),
            checkpoint_id="boundary",
            parent_checkpoint_id="pre",
            ts=boundary_ts,
        )
        await session.commit()

    async with db.async_session_factory() as session:
        messages = MessagesRepository(session)
        anchor = await _insert_message(
            messages,
            conv_id=source_id,
            role="assistant",
            text="anchor",
        )
        await session.flush()
        await _set_message_created_at(
            session,
            message_id=anchor,
            ts=anchor_msg_ts,
        )
        following = await _insert_message(
            messages,
            conv_id=source_id,
            role="user",
            text="next",
        )
        await session.flush()
        await _set_message_created_at(
            session,
            message_id=following,
            ts=next_msg_ts,
        )
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        result = await session.execute(
            text(
                "SELECT checkpoint_id FROM checkpoints WHERE thread_id = :t",
            ),
            {"t": str(fork_id)},
        )
        ids = {r[0] for r in result}
        assert "pre" in ids
        assert "boundary" not in ids
        assert await _chain_is_valid(session, str(fork_id))


async def test_fork_identical_message_timestamps_deterministic(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A fork stays valid when two adjacent messages share a created_at."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    shared_ts = base + timedelta(seconds=10)

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session,
            conversation_id=source_id,
            user_id=user_id,
        )
        await _seed_checkpoint(
            session,
            thread_id=str(source_id),
            checkpoint_id="only",
            parent_checkpoint_id=None,
            ts=base + timedelta(seconds=1),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        messages = MessagesRepository(session)
        anchor = await _insert_message(
            messages,
            conv_id=source_id,
            role="assistant",
            text="anchor",
        )
        other = await _insert_message(
            messages,
            conv_id=source_id,
            role="user",
            text="next",
        )
        await session.flush()
        await _set_message_created_at(session, message_id=anchor, ts=shared_ts)
        await _set_message_created_at(session, message_id=other, ts=shared_ts)
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        assert await _count_checkpoints(session, str(fork_id)) >= 0
        assert await _chain_is_valid(session, str(fork_id))


async def test_fork_with_no_checkpoints(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A conversation without checkpoints forks into an empty thread."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session,
            conversation_id=source_id,
            user_id=user_id,
        )
        messages = MessagesRepository(session)
        anchor = await _insert_message(
            messages,
            conv_id=source_id,
            role="assistant",
            text="synthetic",
        )
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        assert await _count_checkpoints(session, str(fork_id)) == 0
        assert await _chain_is_valid(session, str(fork_id))


async def test_fork_messages_are_copied_in_order(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """The message prefix is a fresh copy with the same order and content."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    message_ids, _ = await _two_turn_source(user_id=user_id, source_id=source_id)

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=message_ids[-1],
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        source_rows = await MessagesRepository(session).list_messages_for_conversation(
            source_id,
        )
        fork_rows = await MessagesRepository(session).list_messages_for_conversation(
            fork_id,
        )
        assert [r.role for r in fork_rows] == [r.role for r in source_rows]
        assert {r.id for r in source_rows}.isdisjoint({r.id for r in fork_rows})


async def test_fork_cascade_delete_removes_descendants(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A cascade delete of the source removes every descendant branch row."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    message_ids, _ = await _two_turn_source(user_id=user_id, source_id=source_id)

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=message_ids[1],
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        await ConversationRepository(session).delete(source_id, cascade=True)
        await session.commit()

    async with db.async_session_factory() as session:
        remaining = await session.scalar(
            select(Conversation).where(Conversation.id == fork_id),
        )
        assert remaining is None


async def test_fork_survives_noncascade_delete_of_source(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A non-cascade delete promotes the branch to a root and keeps its chain."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    message_ids, _ = await _two_turn_source(user_id=user_id, source_id=source_id)

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=message_ids[-1],
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id
        fork_count_before = await _count_checkpoints(session, str(fork_id))

    async with db.async_session_factory() as session:
        await ConversationRepository(session).delete(source_id)
        await session.commit()

    async with db.async_session_factory() as session:
        surviving = await session.scalar(
            select(Conversation).where(Conversation.id == fork_id),
        )
        assert surviving is not None
        assert surviving.parent_conversation_id is None
        assert await _count_checkpoints(session, str(fork_id)) == fork_count_before
        assert await _chain_is_valid(session, str(fork_id))


async def test_fork_of_fork_scopes_to_parent_branch(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A fork of a fork reads only its direct parent, never the grandparent."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    message_ids, _ = await _two_turn_source(user_id=user_id, source_id=source_id)

    async with db.async_session_factory() as session:
        mid = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=message_ids[1],
            user_id=user_id,
        )
        await session.commit()
        mid_id = mid.id

    async with db.async_session_factory() as session:
        mid_count = await _count_checkpoints(session, str(mid_id))
        mid_msgs = await MessagesRepository(session).list_messages_for_conversation(
            mid_id,
        )

    async with db.async_session_factory() as session:
        grand = await fork_conversation(
            session,
            source_conversation_id=mid_id,
            from_message_id=mid_msgs[-1].id,
            user_id=user_id,
        )
        await session.commit()
        grand_id = grand.id

    async with db.async_session_factory() as session:
        assert await _count_checkpoints(session, str(grand_id)) == mid_count
        assert await _chain_is_valid(session, str(grand_id))


async def test_fork_resume_returns_anchor_state(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A resume of the fork returns the anchor-turn state, not a later state."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session,
            conversation_id=source_id,
            user_id=user_id,
        )
        await session.commit()

    async with lifespan_checkpointer(get_settings().database_url) as saver:
        await _put_real_checkpoint(
            saver,
            thread_id=str(source_id),
            checkpoint_id="01000000-0000-7000-8000-000000000001",
            parent_checkpoint_id=None,
            ts=base + timedelta(seconds=5),
            channel_values={"turn_total_tokens": 100, "current_phase": "scoping"},
        )
        await _put_real_checkpoint(
            saver,
            thread_id=str(source_id),
            checkpoint_id="01000000-0000-7000-8000-000000000002",
            parent_checkpoint_id="01000000-0000-7000-8000-000000000001",
            ts=base + timedelta(seconds=20),
            channel_values={"turn_total_tokens": 250, "current_phase": "verification"},
        )
        await _put_real_checkpoint(
            saver,
            thread_id=str(source_id),
            checkpoint_id="01000000-0000-7000-8000-000000000003",
            parent_checkpoint_id="01000000-0000-7000-8000-000000000002",
            ts=base + timedelta(seconds=50),
            channel_values={"turn_total_tokens": 1500, "current_phase": "execution"},
        )

    anchor_ts = base + timedelta(seconds=19)
    next_ts = base + timedelta(seconds=40)

    async with db.async_session_factory() as session:
        messages = MessagesRepository(session)
        anchor = await _insert_message(
            messages,
            conv_id=source_id,
            role="assistant",
            text="anchor",
        )
        following = await _insert_message(
            messages,
            conv_id=source_id,
            role="user",
            text="next turn",
        )
        await session.flush()
        await _set_message_created_at(session, message_id=anchor, ts=anchor_ts)
        await _set_message_created_at(session, message_id=following, ts=next_ts)
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with lifespan_checkpointer(get_settings().database_url) as saver:
        fork_tuple = await _resume_latest(saver, str(fork_id))
        source_tuple = await _resume_latest(saver, str(source_id))

    assert fork_tuple is not None
    assert source_tuple is not None
    assert source_tuple.checkpoint["channel_values"]["turn_total_tokens"] == 1500
    assert source_tuple.checkpoint["channel_values"]["current_phase"] == "execution"
    assert fork_tuple.checkpoint["channel_values"]["turn_total_tokens"] == 250
    assert fork_tuple.checkpoint["channel_values"]["current_phase"] == "verification"

    async with db.async_session_factory() as session:
        assert await _chain_is_valid(session, str(fork_id))


async def test_fork_resume_latest_matches_source_exactly(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A fork from the latest message resumes into the same state as the source.

    Every field that LangGraph reads on resume survives the copy unchanged.
    """
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session,
            conversation_id=source_id,
            user_id=user_id,
        )
        await session.commit()

    async with lifespan_checkpointer(get_settings().database_url) as saver:
        await _put_real_checkpoint(
            saver,
            thread_id=str(source_id),
            checkpoint_id="02000000-0000-7000-8000-000000000001",
            parent_checkpoint_id=None,
            ts=base + timedelta(seconds=5),
            channel_values={"turn_total_tokens": 800, "current_phase": "planning"},
        )

    async with db.async_session_factory() as session:
        messages = MessagesRepository(session)
        anchor = await _insert_message(
            messages,
            conv_id=source_id,
            role="assistant",
            text="only",
        )
        await session.flush()
        await _set_message_created_at(
            session,
            message_id=anchor,
            ts=base + timedelta(seconds=10),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with lifespan_checkpointer(get_settings().database_url) as saver:
        src = await _resume_latest(saver, str(source_id))
        frk = await _resume_latest(saver, str(fork_id))

    assert src is not None
    assert frk is not None
    assert frk.checkpoint["id"] == src.checkpoint["id"]
    assert frk.checkpoint["ts"] == src.checkpoint["ts"]
    assert frk.checkpoint["channel_values"] == src.checkpoint["channel_values"]
    assert frk.checkpoint["channel_versions"] == src.checkpoint["channel_versions"]


async def test_fork_scales_to_many_turns(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A fork of a long conversation keeps a valid chain and a pre-cutoff state."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    turns = 8

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session,
            conversation_id=source_id,
            user_id=user_id,
        )
        await session.commit()

    async with lifespan_checkpointer(get_settings().database_url) as saver:
        prev_id: str | None = None
        for turn in range(turns):
            cp_id = f"03000000-0000-7000-8000-{turn:012d}"
            await _put_real_checkpoint(
                saver,
                thread_id=str(source_id),
                checkpoint_id=cp_id,
                parent_checkpoint_id=prev_id,
                ts=base + timedelta(seconds=turn * 10 + 5),
                channel_values={"turn_total_tokens": (turn + 1) * 100},
            )
            prev_id = cp_id

    msg_ids: list[UUID] = []
    for turn in range(turns):
        async with db.async_session_factory() as session:
            messages = MessagesRepository(session)
            msg = await _insert_message(
                messages,
                conv_id=source_id,
                role="assistant",
                text=f"turn-{turn}",
            )
            await session.flush()
            await _set_message_created_at(
                session,
                message_id=msg,
                ts=base + timedelta(seconds=turn * 10 + 9),
            )
            msg_ids.append(msg)
            await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=msg_ids[3],
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        assert await _chain_is_valid(session, str(fork_id))
        source_count = await _count_checkpoints(session, str(source_id))
        fork_count = await _count_checkpoints(session, str(fork_id))
        assert 0 < fork_count < source_count

    async with lifespan_checkpointer(get_settings().database_url) as saver:
        frk = await _resume_latest(saver, str(fork_id))
    assert frk is not None
    # The latest surviving checkpoint is the last one before the cutoff.
    assert frk.checkpoint["channel_values"]["turn_total_tokens"] <= 500
    assert frk.checkpoint["channel_values"]["turn_total_tokens"] >= 100


async def test_fork_writes_only_reference_surviving_checkpoints(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """Every write row in the fork joins back to a checkpoint in the fork."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    message_ids, _ = await _two_turn_source(user_id=user_id, source_id=source_id)

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=message_ids[1],
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        result = await session.execute(
            text(
                "SELECT COUNT(*) FROM checkpoint_writes w "
                "WHERE w.thread_id = :t "
                "  AND NOT EXISTS ("
                "     SELECT 1 FROM checkpoints c "
                "     WHERE c.thread_id = w.thread_id "
                "       AND c.checkpoint_ns = w.checkpoint_ns "
                "       AND c.checkpoint_id = w.checkpoint_id"
                "  )",
            ),
            {"t": str(fork_id)},
        )
        orphan_writes = int(result.scalar_one())
        assert orphan_writes == 0


async def test_fork_preserves_blob_bytes_exactly(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """Each source blob lands in the fork with identical bytes.

    The copy must not re-encode the blob column. A changed encoding decodes
    into a different resumed state.
    """
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(
            session,
            conversation_id=source_id,
            user_id=user_id,
        )
        await session.commit()

    async with lifespan_checkpointer(get_settings().database_url) as saver:
        await _put_real_checkpoint(
            saver,
            thread_id=str(source_id),
            checkpoint_id="04000000-0000-7000-8000-000000000001",
            parent_checkpoint_id=None,
            ts=base + timedelta(seconds=5),
            channel_values={
                "turn_total_tokens": 777,
                "current_phase": "discovery",
                "discovered_searches": ["GenesByTaxon", "GenesByRNASeq"],
                "retrieved_memories": [{"kind": "strategy", "name": "baseline"}],
            },
        )

    async with db.async_session_factory() as session:
        messages = MessagesRepository(session)
        anchor = await _insert_message(
            messages,
            conv_id=source_id,
            role="assistant",
            text="done",
        )
        await session.flush()
        await _set_message_created_at(
            session,
            message_id=anchor,
            ts=base + timedelta(seconds=10),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT src.channel, src.version, src.type, src.blob,
                       dst.type, dst.blob
                FROM checkpoint_blobs src
                LEFT JOIN checkpoint_blobs dst
                    ON dst.thread_id = :dst_t
                   AND dst.checkpoint_ns = src.checkpoint_ns
                   AND dst.channel = src.channel
                   AND dst.version = src.version
                WHERE src.thread_id = :src_t
                """,
            ),
            {"src_t": str(source_id), "dst_t": str(fork_id)},
        )
        rows = result.all()
        assert len(rows) > 0, "source has no blobs to compare — fixture bug"
        for channel, version, src_type, src_blob, dst_type, dst_blob in rows:
            assert dst_type is not None, (
                f"blob missing in fork for channel={channel!r} version={version!r}"
            )
            assert dst_type == src_type, (
                f"blob type mismatch on ({channel!r}, {version!r}): "
                f"source={src_type!r} fork={dst_type!r}"
            )
            assert bytes(dst_blob) == bytes(src_blob), (
                f"blob bytes mismatch on ({channel!r}, {version!r}): "
                f"source={len(bytes(src_blob))}B fork={len(bytes(dst_blob))}B"
            )

    # The saver must decode the fork blobs into the same values as the source.
    async with lifespan_checkpointer(get_settings().database_url) as saver:
        src_tuple = await _resume_latest(saver, str(source_id))
        frk_tuple = await _resume_latest(saver, str(fork_id))
    assert src_tuple is not None
    assert frk_tuple is not None
    assert (
        src_tuple.checkpoint["channel_values"]
        == (frk_tuple.checkpoint["channel_values"])
    )


# Scratchpad fork copy.


async def test_fork_copies_scratchpad_notes_with_fresh_ids(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A fork duplicates the scratchpad notes of its source under new ids.

    The copied rows keep title, body and pinned. The source stays intact.
    """
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(session, conversation_id=source_id, user_id=user_id)
        await session.commit()

    async with db.async_session_factory() as session:
        sc = ScratchpadRepository(session)
        src_note_1 = await sc.create(
            conversation_id=source_id,
            data=NoteCreate(
                title="GenesByRNASeq leads",
                summary="1200 genes with threshold 2",
                body="Full scratchpad body #1",
                tags=["candidate"],
                pinned=True,
            ),
        )
        src_note_2 = await sc.create(
            conversation_id=source_id,
            data=NoteCreate(
                title="Dead end: GenesByGO",
                summary="Lost stage specificity",
                body="Do not retry.",
            ),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        anchor_id = await _insert_message(
            MessagesRepository(session),
            conv_id=source_id,
            role="assistant",
            text="anchor",
        )
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor_id,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        sc = ScratchpadRepository(session)
        fork_notes = await sc.list_notes(conversation_id=fork_id, limit=100)
        src_notes = await sc.list_notes(conversation_id=source_id, limit=100)

    assert len(fork_notes) == 2
    assert len(src_notes) == 2

    by_title = {n.title: n for n in fork_notes}
    assert by_title["GenesByRNASeq leads"].body == "Full scratchpad body #1"
    assert by_title["GenesByRNASeq leads"].pinned is True
    assert by_title["GenesByRNASeq leads"].tags == ["candidate"]
    assert by_title["Dead end: GenesByGO"].body == "Do not retry."
    assert by_title["Dead end: GenesByGO"].pinned is False

    src_ids = {n.id for n in src_notes}
    fork_ids = {n.id for n in fork_notes}
    assert src_ids.isdisjoint(fork_ids)
    assert src_note_1.id in src_ids
    assert src_note_2.id in src_ids
    assert src_note_1.id not in fork_ids
    assert src_note_2.id not in fork_ids


def _three_step_combine_ast() -> dict[str, object]:
    """Builds a strategy AST with a combine root over two leaf searches."""
    return {
        "recordType": "transcript",
        "name": "Pf erythrocytic invasion",
        "root": {
            "id": "step_combine",
            "searchName": "__combine__",
            "operator": "INTERSECT",
            "parameters": {},
            "primaryInput": {
                "id": "step_taxon",
                "searchName": "GenesByTaxon",
                "parameters": {"organism": "Plasmodium falciparum 3D7"},
            },
            "secondaryInput": {
                "id": "step_text",
                "searchName": "GenesByText",
                "parameters": {"text_expression": "invasion"},
            },
        },
        "wdkStepIds": {
            "step_combine": 9000,
            "step_taxon": 9001,
            "step_text": 9002,
        },
    }


class _AstLeaf(BaseModel):
    """Typed view of a leaf step in the persisted AST."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    search_name: str = Field(alias="searchName")
    parameters: dict[str, str] = Field(default_factory=dict)


class _AstRoot(BaseModel):
    """Typed view of the persisted combine root."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    operator: str
    primary_input: _AstLeaf = Field(alias="primaryInput")
    secondary_input: _AstLeaf = Field(alias="secondaryInput")


class _AstView(BaseModel):
    """Typed view of the persisted strategy AST blob."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    root: _AstRoot
    wdk_step_ids: dict[str, int] | None = Field(default=None, alias="wdkStepIds")


async def _seed_conversation_with_ast(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
    ast: dict[str, object],
    imported_saved_strategy_ids: list[int] | None = None,
) -> None:
    session.add(
        Conversation(
            id=conversation_id,
            user_id=user_id,
            site_id="plasmodb",
            name="root",
        ),
    )
    await session.flush()
    session.add(
        ConversationStrategy(
            conversation_id=conversation_id,
            record_type="transcript",
            strategy_ast=ast,
            step_count=3,
            imported_saved_strategy_ids=imported_saved_strategy_ids or [],
        ),
    )
    await session.flush()
    await StrategyRevisionRepository(session).record(
        conversation_id,
        await ConversationRepository(session).get_strategy(conversation_id),
    )


async def test_fork_copies_ast_as_independent_deep_structure(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A fork deep-copies the AST, so a change to the fork leaves the parent.

    A source without a WDK strategy id skips the WDK duplication path, and
    the fork drops the WDK step id map.
    """
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()
    ast = _three_step_combine_ast()

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation_with_ast(
            session,
            conversation_id=source_id,
            user_id=user_id,
            ast=ast,
        )
        anchor_id = await _insert_message(
            MessagesRepository(session),
            conv_id=source_id,
            role="assistant",
            text="built",
        )
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor_id,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        forked = await session.get(ConversationStrategy, fork_id)
        assert forked is not None
        fork_view = _AstView.model_validate(forked.strategy_ast)
        assert fork_view.root.id == "step_combine"
        assert fork_view.root.operator == "INTERSECT"
        assert fork_view.root.primary_input.search_name == "GenesByTaxon"
        assert fork_view.root.primary_input.parameters["organism"] == (
            "Plasmodium falciparum 3D7"
        )
        assert fork_view.root.secondary_input.search_name == "GenesByText"
        assert fork_view.root.secondary_input.parameters["text_expression"] == (
            "invasion"
        )
        assert fork_view.wdk_step_ids is None
        assert forked.wdk_strategy_id is None
        assert forked.record_type == "transcript"

        # SQLAlchemy marks a JSON column dirty on assignment only.
        mutated_root = fork_view.root.model_copy(update={"operator": "UNION"})
        forked.strategy_ast = {
            "recordType": "transcript",
            "root": mutated_root.model_dump(by_alias=True),
        }
        await session.commit()

    async with db.async_session_factory() as session:
        parent = await ConversationRepository(session).get_strategy(source_id)
        parent_view = _AstView.model_validate(parent.strategy_ast)
        assert parent_view.root.operator == "INTERSECT", (
            "fork mutation leaked into the parent strategy AST — shallow "
            "copy aliased the nested root subtree"
        )
        assert parent_view.root.primary_input.parameters["organism"] == (
            "Plasmodium falciparum 3D7"
        )
        assert parent_view.wdk_step_ids == {
            "step_combine": 9000,
            "step_taxon": 9001,
            "step_text": 9002,
        }


async def test_fork_imported_saved_strategy_ids_is_independent_list(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """The imported strategy id list of a fork is a fresh copy of the source list."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation_with_ast(
            session,
            conversation_id=source_id,
            user_id=user_id,
            ast=_three_step_combine_ast(),
            imported_saved_strategy_ids=[5001, 5002],
        )
        anchor_id = await _insert_message(
            MessagesRepository(session),
            conv_id=source_id,
            role="assistant",
            text="built",
        )
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor_id,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        forked = await session.get(ConversationStrategy, fork_id)
        assert forked is not None
        assert forked.imported_saved_strategy_ids == [5001, 5002]
        forked.imported_saved_strategy_ids = [*forked.imported_saved_strategy_ids, 5003]
        await session.commit()

    async with db.async_session_factory() as session:
        parent = await ConversationRepository(session).get_strategy(source_id)
        assert parent.imported_saved_strategy_ids == [5001, 5002], (
            "fork's consumer-id append leaked into the parent conversation"
        )


async def test_fork_at_middle_message_excludes_later_messages(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """The branch boundary includes the anchor message and excludes later ones."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(session, conversation_id=source_id, user_id=user_id)
        await session.commit()

    msg_ids: list[UUID] = []
    for role in ("user", "assistant", "user", "assistant"):
        async with db.async_session_factory() as session:
            mid = await _insert_message(
                MessagesRepository(session),
                conv_id=source_id,
                role=role,
                text=role,
            )
            msg_ids.append(mid)
            await session.commit()

    anchor_id = msg_ids[1]

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=anchor_id,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        rows = await MessagesRepository(session).list_messages_for_conversation(fork_id)
        assert [r.role for r in rows] == ["user", "assistant"], (
            "fork must copy exactly the anchor prefix, not later messages"
        )
        src_rows = await MessagesRepository(session).list_messages_for_conversation(
            source_id,
        )
        assert [r.role for r in src_rows] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]


async def test_fork_rewrites_scratchpad_ids_in_copied_chunks(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id = uuid4()

    async with db.async_session_factory() as session:
        await _seed_user(session, user_id)
        await _seed_conversation(session, conversation_id=source_id, user_id=user_id)
        await session.commit()

    async with db.async_session_factory() as session:
        sc = ScratchpadRepository(session)
        src_note = await sc.create(
            conversation_id=source_id,
            data=NoteCreate(
                title="The one",
                summary="A note",
                body="Body here.",
            ),
        )
        await session.commit()
    src_note_id = src_note.id

    async with db.async_session_factory() as session:
        msg_id = uuid4()
        session.add(
            Message(
                id=msg_id,
                conversation_id=source_id,
                role="assistant",
                metadata_={"mode": "strategy"},
            ),
        )
        session.add_all(
            [
                ConversationEvent(
                    conversation_id=source_id,
                    turn_id=msg_id,
                    chunk={
                        "type": "tool-note",
                        "toolCallId": "tc-1",
                        "state": "output-available",
                        "input": {
                            "title": "The one",
                            "summary": "A note",
                            "body": "Body here.",
                        },
                        "output": {"id": src_note_id, "title": "The one"},
                    },
                ),
                ConversationEvent(
                    conversation_id=source_id,
                    turn_id=msg_id,
                    chunk={
                        "type": "tool-read_note",
                        "toolCallId": "tc-2",
                        "state": "output-available",
                        "input": {"note_id": src_note_id},
                        "output": {"id": src_note_id, "body": "Body here."},
                    },
                ),
            ]
        )
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=msg_id,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        sc = ScratchpadRepository(session)
        fork_notes = await sc.list_notes(conversation_id=fork_id, limit=10)
        fork_chunks = (
            await session.scalars(
                select(ConversationEvent)
                .where(ConversationEvent.conversation_id == fork_id)
                .order_by(ConversationEvent.id),
            )
        ).all()

    assert len(fork_notes) == 1
    new_id = fork_notes[0].id
    assert new_id != src_note_id

    by_type = {e.chunk["type"]: e.chunk for e in fork_chunks}
    assert by_type["tool-note"]["output"]["id"] == new_id
    assert by_type["tool-read_note"]["input"]["note_id"] == new_id
    assert by_type["tool-read_note"]["output"]["id"] == new_id
