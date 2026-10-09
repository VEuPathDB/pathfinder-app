from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_10_04_0001"
REVISION = "2026_10_09_0001"
STATUSES = ("todo", "doing", "succeeded", "failed", "cancelled", "aborted")


def _queue_one_job_per_status(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        for status in STATUSES:
            job = connection.execute(
                "INSERT INTO procrastinate_jobs "
                "(queue_name, task_name, args, status) "
                "VALUES ('chat_turn', 'chat_turn:run', %s, %s) RETURNING id",
                ('{"payload": {"text": "a request"}}', status),
            ).fetchone()
            assert job is not None
            connection.execute(
                "INSERT INTO procrastinate_events (job_id, type) "
                "VALUES (%s, 'deferred')",
                (job[0],),
            )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_finished_jobs"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _queue_one_job_per_status(url)
    yield url
    drop_database(base_url, name)


def test_the_upgrade_deletes_every_finished_job_and_keeps_the_rest(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    kept = rows(
        seeded_database, "SELECT status::text FROM procrastinate_jobs ORDER BY id"
    )
    assert kept == [("todo",), ("doing",)]


def test_the_upgrade_deletes_the_events_of_the_deleted_jobs(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    events = rows(
        seeded_database,
        "SELECT DISTINCT j.status::text FROM procrastinate_events e "
        "JOIN procrastinate_jobs j ON j.id = e.job_id ORDER BY 1",
    )
    orphans = rows(
        seeded_database,
        "SELECT count(*) FROM procrastinate_events e WHERE NOT EXISTS "
        "(SELECT 1 FROM procrastinate_jobs j WHERE j.id = e.job_id)",
    )
    assert (events, orphans) == ([("doing",), ("todo",)], [(0,)])


def test_the_downgrade_restores_nothing_and_succeeds(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert rows(seeded_database, "SELECT count(*) FROM procrastinate_jobs") == [(2,)]
