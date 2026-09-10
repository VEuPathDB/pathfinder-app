"""A worker job runs under the application that holds the conversation."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import application_id_ctx
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.scope import attach_conversation_application

from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID

OTHER = "companion"


async def _seed_conversation(application_id: str) -> UUID:
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
                name="kinases",
                application_id=application_id,
            ),
        )
        await session.commit()
    return conversation_id


@pytest.mark.asyncio
async def test_the_job_reads_the_application_from_the_conversation_row(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    conversation_id = await _seed_conversation(OTHER)

    async with attach_conversation_application(conversation_id):
        inside = application_id_ctx.get()

    assert inside == OTHER
    assert application_id_ctx.get() == "pathfinder"


@pytest.mark.asyncio
async def test_a_conversation_that_is_gone_fails_loudly(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine

    with pytest.raises(LookupError):
        async with attach_conversation_application(uuid4()):
            pass
