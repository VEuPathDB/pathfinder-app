from uuid import uuid4

from assistant_core.persistence.models import Conversation
from assistant_core.persistence.repositories.message import MessagesRepository
from assistant_core.platform import db

from pathfinder.persistence.models import User


async def test_insert_and_fetch_message(
    patch_app_db_engine: None, db_cleaner: None
) -> None:
    """A single insert round-trips parts + metadata as JSONB."""
    del patch_app_db_engine, db_cleaner
    conversation_id = uuid4()
    user_id = uuid4()
    message_id = uuid4()
    metadata: dict[str, object] = {
        "phase": "scoping",
        "model": "anthropic:claude-sonnet-4-5",
    }

    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(Conversation(id=conversation_id, user_id=user_id))
        await session.flush()

        repo = MessagesRepository(session)
        await repo.insert_message(
            message_id=message_id,
            conversation_id=conversation_id,
            role="user",
            metadata=metadata,
        )
        await session.commit()

    async with db.async_session_factory() as session:
        repo = MessagesRepository(session)
        rows = await repo.list_messages_for_conversation(conversation_id)

    assert len(rows) == 1
    assert rows[0].id == message_id
    assert rows[0].conversation_id == conversation_id
    assert rows[0].role == "user"
    assert rows[0].metadata_ == metadata
