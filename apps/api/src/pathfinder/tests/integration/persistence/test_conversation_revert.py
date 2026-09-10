from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.conversation.ui_message_reducer import user_message_chunk
from assistant_core.persistence.models import Conversation, ConversationEvent, Message
from assistant_core.persistence.repositories.message import MessagesRepository
from assistant_core.persistence.repositories.scratchpad import ScratchpadRepository
from assistant_core.platform import db
from assistant_core.scratchpad.models import NoteCreate
from sqlalchemy import func, select, text

from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import (
    RevertError,
    revert_conversation_to_message,
)


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


@pytest.fixture(autouse=True)
async def _truncate_langgraph_tables() -> AsyncIterator[None]:
    yield
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE checkpoints, checkpoint_blobs, "
                "checkpoint_writes RESTART IDENTITY",
            ),
        )
        await session.commit()


async def _seed_user() -> User:
    async with db.async_session_factory() as session:
        user = User(id=uuid4(), external_id=f"u{uuid4()}")
        session.add(user)
        await session.commit()
        return user


async def _seed_conversation(user_id: UUID) -> Conversation:
    async with db.async_session_factory() as session:
        row = Conversation(
            user_id=user_id,
            assistant_id=PATHFINDER_ASSISTANT_ID,
            site_id="plasmodb",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def _seed_message(conv_id: UUID, role: str) -> Message:
    async with db.async_session_factory() as session:
        msg = Message(
            id=uuid4(),
            conversation_id=conv_id,
            role=role,
            metadata_={},
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg


async def _seed_messages_distinct_ts(conv_id: UUID, roles: list[str]) -> list[Message]:
    """Seed messages with strictly increasing ``created_at`` (one txn each).

    Mirrors production, where every turn's message is committed in its own
    transaction, so each ``now()`` differs.
    """
    base = datetime.now(UTC)
    msgs: list[Message] = []
    async with db.async_session_factory() as session:
        for i, role in enumerate(roles):
            msg = Message(
                id=uuid4(),
                conversation_id=conv_id,
                role=role,
                metadata_={},
                created_at=base + timedelta(seconds=i),
            )
            session.add(msg)
            msgs.append(msg)
        await session.commit()
        for msg in msgs:
            await session.refresh(msg)
    return msgs


async def _seed_checkpoint(thread_id: UUID, ts: datetime, cid: str) -> None:
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO checkpoints
                  (thread_id, checkpoint_ns, checkpoint_id, type, checkpoint, metadata)
                VALUES
                  (:tid, '', :cid, 'test',
                   jsonb_build_object('v', 1, 'ts', CAST(:ts AS text), 'id', CAST(:cid AS text)),
                   '{}'::jsonb)
                """,
            ),
            {"tid": str(thread_id), "cid": cid, "ts": ts.isoformat()},
        )
        await session.commit()


class TestRevertConversation:
    async def test_deletes_messages_at_and_after_target(self) -> None:
        user = await _seed_user()
        conv = await _seed_conversation(user.id)
        t1 = await _seed_message(conv.id, "user")
        t2 = await _seed_message(conv.id, "assistant")
        t3 = await _seed_message(conv.id, "user")
        await _seed_message(conv.id, "assistant")

        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=conv.id,
                target_message_id=t3.id,
                user_id=user.id,
            )
            await session.commit()

        async with db.async_session_factory() as session:
            remaining = (
                await session.scalars(
                    select(Message).where(Message.conversation_id == conv.id),
                )
            ).all()
        assert {m.id for m in remaining} == {t1.id, t2.id}

    async def test_deletes_scratchpad_notes_at_and_after_target(self) -> None:
        user = await _seed_user()
        conv = await _seed_conversation(user.id)
        t1 = await _seed_message(conv.id, "user")

        async with db.async_session_factory() as session:
            repo = ScratchpadRepository(session)
            pre = await repo.create(
                conversation_id=conv.id,
                data=NoteCreate(title="before", summary="s", body="b"),
            )
            await session.commit()

        t2 = await _seed_message(conv.id, "user")

        async with db.async_session_factory() as session:
            repo = ScratchpadRepository(session)
            post = await repo.create(
                conversation_id=conv.id,
                data=NoteCreate(title="after", summary="s", body="b"),
            )
            await session.commit()

        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=conv.id,
                target_message_id=t2.id,
                user_id=user.id,
            )
            await session.commit()

        async with db.async_session_factory() as session:
            repo = ScratchpadRepository(session)
            notes = await repo.list_notes(conversation_id=conv.id, limit=50)
        ids = {n.id for n in notes}
        assert pre.id in ids
        assert post.id not in ids
        assert t1.role == "user"

    async def test_deletes_user_message_chunk_when_reverting_to_it(self) -> None:
        user = await _seed_user()
        conv = await _seed_conversation(user.id)
        target = await _seed_message(conv.id, "user")

        async with db.async_session_factory() as session:
            session.add(
                ConversationEvent(
                    conversation_id=conv.id,
                    chunk=user_message_chunk(
                        message_id=str(target.id),
                        parts=[{"type": "text", "text": "edit me"}],
                    ),
                    emitted_at=datetime.now(UTC),
                ),
            )
            await session.commit()

        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=conv.id,
                target_message_id=target.id,
                user_id=user.id,
            )
            await session.commit()

        async with db.async_session_factory() as session:
            remaining = (
                await session.scalars(
                    select(ConversationEvent).where(
                        ConversationEvent.conversation_id == conv.id,
                    ),
                )
            ).all()
        assert remaining == []

    async def test_deletes_conversation_events_at_and_after_target(self) -> None:
        user = await _seed_user()
        conv = await _seed_conversation(user.id)
        t1 = await _seed_message(conv.id, "user")

        async with db.async_session_factory() as session:
            session.add(
                ConversationEvent(
                    conversation_id=conv.id,
                    chunk={"type": "data-pre"},
                    emitted_at=t1.created_at,
                ),
            )
            await session.commit()

        t2 = await _seed_message(conv.id, "user")

        async with db.async_session_factory() as session:
            session.add(
                ConversationEvent(
                    conversation_id=conv.id,
                    chunk={"type": "data-post"},
                    emitted_at=datetime.now(UTC),
                ),
            )
            await session.commit()

        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=conv.id,
                target_message_id=t2.id,
                user_id=user.id,
            )
            await session.commit()

        async with db.async_session_factory() as session:
            remaining = (
                await session.scalars(
                    select(ConversationEvent).where(
                        ConversationEvent.conversation_id == conv.id,
                    ),
                )
            ).all()
        assert {e.chunk["type"] for e in remaining} == {"data-pre"}

    async def test_deletes_checkpoints_at_and_after_target(self) -> None:
        user = await _seed_user()
        conv = await _seed_conversation(user.id)
        t1 = await _seed_message(conv.id, "user")
        await _seed_checkpoint(conv.id, t1.created_at, f"{0:032d}")
        t2 = await _seed_message(conv.id, "user")
        await _seed_checkpoint(conv.id, t2.created_at, f"{1:032d}")

        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=conv.id,
                target_message_id=t2.id,
                user_id=user.id,
            )
            await session.commit()

        async with db.async_session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT checkpoint_id FROM checkpoints WHERE thread_id = :tid",
                    ),
                    {"tid": str(conv.id)},
                )
            ).all()
        assert [r[0] for r in rows] == [f"{0:032d}"]

    async def test_same_timestamp_siblings_cut_by_id_order(self) -> None:
        # Characterization: when messages genuinely share created_at, revert
        # cuts on the stable (created_at, id) ordering — rows with an id below
        # the target survive, the target and larger-id rows are deleted. The id
        # tiebreak is uuid4, NOT insertion order, so this is the deterministic
        # behaviour, not a recovery of true conversation order (which cannot be
        # recovered from a tie set with random PKs). Production avoids ties:
        # every turn commits in its own transaction and forks copy the source's
        # per-turn timestamps (see test_revert_forked_conversation_keeps_prefix).
        user = await _seed_user()
        conv = await _seed_conversation(user.id)
        ids = sorted(uuid4() for _ in range(4))
        async with db.async_session_factory() as session:
            session.add_all(
                Message(id=mid, conversation_id=conv.id, role="user", metadata_={})
                for mid in ids
            )
            await session.commit()
        target = ids[1]

        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=conv.id,
                target_message_id=target,
                user_id=user.id,
            )
            await session.commit()

        async with db.async_session_factory() as session:
            remaining = (
                await session.scalars(
                    select(Message).where(Message.conversation_id == conv.id),
                )
            ).all()
        assert {m.id for m in remaining} == {ids[0]}

    async def test_revert_forked_conversation_keeps_prefix(self) -> None:
        # Production trigger: fork copies the whole prefix in one transaction.
        # The copied messages must preserve the source's per-turn created_at
        # so the fork has a well-defined order; reverting the fork to its
        # second user turn then keeps the earlier copied turns.
        user = await _seed_user()
        source = await _seed_conversation(user.id)
        src_msgs = await _seed_messages_distinct_ts(
            source.id, ["user", "assistant", "user", "assistant"]
        )

        async with db.async_session_factory() as session:
            fork = await fork_conversation(
                session,
                source_conversation_id=source.id,
                from_message_id=src_msgs[-1].id,
                user_id=user.id,
            )
            await session.commit()
            fork_id = fork.id

        async with db.async_session_factory() as session:
            fork_rows = await MessagesRepository(
                session
            ).list_messages_for_conversation(fork_id)
        assert [r.role for r in fork_rows] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        second_user = fork_rows[2]

        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=fork_id,
                target_message_id=second_user.id,
                user_id=user.id,
            )
            await session.commit()

        async with db.async_session_factory() as session:
            remaining = await MessagesRepository(
                session
            ).list_messages_for_conversation(fork_id)
        assert [r.id for r in remaining] == [r.id for r in fork_rows[:2]]

    async def test_revert_into_branch_point_nulls_child_parent_message(
        self,
    ) -> None:
        # Characterization: a child conversation branched at message X keeps a
        # parent_message_id FK to X. Reverting the source past X deletes X; the
        # FK is ondelete=SET NULL, so the child's parent_message_id becomes
        # NULL (no IntegrityError, no dangling pointer) while
        # parent_conversation_id survives — the branch is still attached to the
        # source in the sidebar tree, it just loses its precise anchor row.
        user = await _seed_user()
        source = await _seed_conversation(user.id)
        msgs = await _seed_messages_distinct_ts(
            source.id, ["user", "assistant", "user", "assistant"]
        )
        branch_point = msgs[2]

        async with db.async_session_factory() as session:
            fork = await fork_conversation(
                session,
                source_conversation_id=source.id,
                from_message_id=branch_point.id,
                user_id=user.id,
            )
            await session.commit()
            fork_id = fork.id

        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=source.id,
                target_message_id=branch_point.id,
                user_id=user.id,
            )
            await session.commit()

        async with db.async_session_factory() as session:
            child = await session.scalar(
                select(Conversation).where(Conversation.id == fork_id),
            )
            assert child is not None
            assert child.parent_message_id is None
            assert child.parent_conversation_id == source.id
            src_remaining = await MessagesRepository(
                session
            ).list_messages_for_conversation(source.id)
        assert {m.id for m in src_remaining} == {msgs[0].id, msgs[1].id}

    async def test_checkpoint_just_before_target_message_survives(self) -> None:
        # Two clocks: checkpoint ts is app-side (LangGraph), message created_at
        # is DB now(). Revert deletes checkpoints with ts >= the target's
        # created_at. A checkpoint stamped a hair BEFORE the target message
        # (clock skew, or a mid-turn checkpoint that preceded the message
        # write) survives the revert even though it belongs to the deleted
        # turn — leaving a checkpoint with no surviving message. Documented gap.
        user = await _seed_user()
        conv = await _seed_conversation(user.id)
        keep = await _seed_message(conv.id, "user")
        target = await _seed_message(conv.id, "user")
        # cp_before: 1ms before target -> survives. cp_after: at target -> gone.
        await _seed_checkpoint(
            conv.id, target.created_at - timedelta(milliseconds=1), f"{0:032d}"
        )
        await _seed_checkpoint(conv.id, target.created_at, f"{1:032d}")

        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=conv.id,
                target_message_id=target.id,
                user_id=user.id,
            )
            await session.commit()

        async with db.async_session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT checkpoint_id FROM checkpoints "
                        "WHERE thread_id = :tid ORDER BY checkpoint_id",
                    ),
                    {"tid": str(conv.id)},
                )
            ).all()
            msgs_left = await MessagesRepository(
                session
            ).list_messages_for_conversation(conv.id)
        # The skewed checkpoint outlives its turn; only `keep`'s message remains.
        assert [r[0] for r in rows] == [f"{0:032d}"]
        assert {m.id for m in msgs_left} == {keep.id}

    async def test_wrong_user_raises(self) -> None:
        user = await _seed_user()
        conv = await _seed_conversation(user.id)
        t1 = await _seed_message(conv.id, "user")

        async with db.async_session_factory() as session:
            with pytest.raises(RevertError):
                await revert_conversation_to_message(
                    session,
                    conversation_id=conv.id,
                    target_message_id=t1.id,
                    user_id=uuid4(),
                )

    async def test_ghost_target_is_noop(self) -> None:
        # A target that was never persisted (e.g. a rejected/failed send) is a
        # no-op, not a 404 — the server is already at the pre-message state.
        user = await _seed_user()
        conv = await _seed_conversation(user.id)
        kept = await _seed_message(conv.id, "user")
        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=conv.id,
                target_message_id=uuid4(),
                user_id=user.id,
            )
            remaining = await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == conv.id,
                ),
            )
        assert remaining == 1
        assert kept is not None

    async def test_target_in_other_conversation_raises(self) -> None:
        user = await _seed_user()
        conv_a = await _seed_conversation(user.id)
        conv_b = await _seed_conversation(user.id)
        other = await _seed_message(conv_b.id, "user")
        async with db.async_session_factory() as session:
            with pytest.raises(RevertError):
                await revert_conversation_to_message(
                    session,
                    conversation_id=conv_a.id,
                    target_message_id=other.id,
                    user_id=user.id,
                )

    async def test_assistant_message_target_rejected(self) -> None:
        user = await _seed_user()
        conv = await _seed_conversation(user.id)
        await _seed_message(conv.id, "user")
        t2 = await _seed_message(conv.id, "assistant")

        async with db.async_session_factory() as session:
            with pytest.raises(RevertError):
                await revert_conversation_to_message(
                    session,
                    conversation_id=conv.id,
                    target_message_id=t2.id,
                    user_id=user.id,
                )
