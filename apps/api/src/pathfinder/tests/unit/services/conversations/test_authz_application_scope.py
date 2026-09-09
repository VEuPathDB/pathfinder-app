"""The ownership helpers scope a conversation by user and application."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import application_id_ctx

from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.errors import ForbiddenError, NotFoundError
from pathfinder.platform.identity import PATHFINDER_APPLICATION_ID
from pathfinder.services.conversations.authz import (
    get_owned_conversation_or_404,
    get_owned_or_404,
)

OWNER = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture(autouse=True)
def calling_application() -> Iterator[None]:
    """A served request names this application, the way security does."""
    token = application_id_ctx.set(PATHFINDER_APPLICATION_ID)
    try:
        yield
    finally:
        application_id_ctx.reset(token)


class OneRowRepository(ConversationRepository):
    """Answers every lookup with the same row, without a database."""

    def __init__(self, conversation: Conversation) -> None:
        self.conversation = conversation

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        del conversation_id
        return self.conversation


def _repo(application_id: str) -> OneRowRepository:
    return OneRowRepository(
        Conversation(
            id=uuid4(),
            user_id=OWNER,
            site_id="plasmodb",
            name="kinases",
            application_id=application_id,
        ),
    )


async def test_the_owner_reaches_a_conversation_of_the_calling_application() -> None:
    found = await get_owned_or_404(_repo(PATHFINDER_APPLICATION_ID), uuid4(), OWNER)

    assert found.user_id == OWNER


async def test_the_same_user_under_another_application_gets_404() -> None:
    with pytest.raises(NotFoundError):
        await get_owned_or_404(_repo("genomics"), uuid4(), OWNER)


async def test_the_403_helper_also_refuses_another_application() -> None:
    with pytest.raises(ForbiddenError):
        await get_owned_conversation_or_404(_repo("genomics"), uuid4(), OWNER)


async def test_the_calling_application_comes_from_the_context() -> None:
    token = application_id_ctx.set("genomics")
    try:
        found = await get_owned_or_404(_repo("genomics"), uuid4(), OWNER)
    finally:
        application_id_ctx.reset(token)

    assert found.application_id == "genomics"
