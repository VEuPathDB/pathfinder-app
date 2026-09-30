"""The first message of a thread records the thread as created, once."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.ai.conversation import dispatcher
from pathfinder.platform.langfuse.events import ProductEvent
from pathfinder.tests.integration.chat._helpers import run_one_chat_turn

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb"
)


async def test_a_new_thread_is_recorded_with_its_assistant_and_site(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[ProductEvent] = []
    monkeypatch.setattr(dispatcher, "record_product_event", recorded.append)

    await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt="Which genes have a signal peptide?",
    )

    assert [(e.name, e.user_id) for e in recorded] == [
        ("conversation_created", authed_user_id)
    ]
    assert recorded[0].conversation_id is not None
    assert recorded[0].attributes == {
        "assistant_id": "pathfinder",
        "site_id": "plasmodb",
    }


async def test_a_later_message_on_the_thread_records_nothing(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[ProductEvent] = []
    monkeypatch.setattr(dispatcher, "record_product_event", recorded.append)
    conversation_id = uuid4()

    for prompt in ("Which genes have a signal peptide?", "Only the kinases."):
        await run_one_chat_turn(
            app=app,
            user_id=authed_user_id,
            connector=in_memory_jobs,
            prompt=prompt,
            conversation_id=conversation_id,
        )

    assert [(e.name, e.conversation_id) for e in recorded] == [
        ("conversation_created", conversation_id)
    ]
