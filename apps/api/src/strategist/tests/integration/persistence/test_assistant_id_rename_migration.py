from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from psycopg.types.json import Jsonb
from testcontainers.community.postgres import PostgresContainer

from strategist.tests.integration.persistence._migration_db import (
    alembic_config,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_11_13_0001"
REVISION = "2026_11_13_0002"
USER_ID = uuid4()
OLD_THREAD = uuid4()
AUDIT_THREAD = uuid4()


def _turn(assistant: str) -> dict[str, Any]:
    return {
        "payload": {
            "assistant_id": assistant,
            "turn_id": str(uuid4()),
            "body": {"conversationId": str(OLD_THREAD), "assistantId": assistant},
        }
    }


def _seed(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        for thread, assistant in ((OLD_THREAD, "pathfinder"), (AUDIT_THREAD, "audit")):
            connection.execute(
                "INSERT INTO conversations (id, user_id, site_id, name, assistant_id) "
                "VALUES (%s, %s, 'plasmodb', 'a thread', %s)",
                (str(thread), str(USER_ID), assistant),
            )
            connection.execute(
                "INSERT INTO eval_staged_cases "
                "(id, user_id, source_conversation_id, site_id, assistant_id, "
                "content_hash, extract, status) "
                "VALUES (%s, %s, %s, 'plasmodb', %s, %s, %s, 'staged')",
                (
                    str(uuid4()),
                    str(USER_ID),
                    str(thread),
                    assistant,
                    assistant.ljust(64, "x"),
                    Jsonb({"siteId": "plasmodb", "assistantId": assistant}),
                ),
            )
            connection.execute(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, lock, args) "
                "VALUES ('chat_turns', 'chat_turn:run', %s, %s)",
                (str(thread), Jsonb(_turn(assistant))),
            )


def _assistants(url: str) -> list[tuple[Any, ...]]:
    return rows(
        url,
        "SELECT c.assistant_id, e.assistant_id, e.extract ->> 'assistantId', "
        "j.args #>> '{payload,assistant_id}', "
        "j.args #>> '{payload,body,assistantId}' "
        "FROM conversations c "
        "JOIN eval_staged_cases e ON e.source_conversation_id = c.id "
        "JOIN procrastinate_jobs j ON j.lock = c.id::text "
        "ORDER BY c.assistant_id",
    )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_assistant_id_rename"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed(url)
    yield url
    drop_database(base_url, name)


def test_the_upgrade_names_every_stored_strategist_thread_strategist(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert _assistants(seeded_database) == [
        ("audit",) * 5,
        ("strategist",) * 5,
    ]


def test_the_downgrade_restores_the_former_id(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert _assistants(seeded_database) == [
        ("audit",) * 5,
        ("pathfinder",) * 5,
    ]
