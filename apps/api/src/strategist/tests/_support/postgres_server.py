from __future__ import annotations

import asyncio
import os
from collections.abc import Generator

import pytest
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

from strategist.tests._support.database import can_connect
from strategist.tests._support.worker_database import (
    create_worker_database,
    shared_database_url,
)


@pytest.fixture(scope="session")
def database_url() -> str:
    # An empty result makes the session start a disposable Postgres.
    return os.environ.get("DATABASE_URL", "").strip()


@pytest.fixture(scope="session")
def postgres_container(
    database_url: str,
) -> Generator[PostgresContainer | None]:
    url = database_url or os.environ.get("DATABASE_URL", "").strip()
    # Another server can hold the port, so the URL counts only when it answers.
    if (
        url
        and "postgresql" in url
        and not asyncio.run(can_connect(shared_database_url(url)))
    ):
        url = ""
        os.environ.pop("DATABASE_URL", None)

    if url:
        create_worker_database(url)
        yield None
        return

    # This requires Docker
    container = PostgresContainer(
        "pgvector/pgvector:pg16",
        username="postgres",
        password="postgres",
        dbname="strategist_test",
    )
    try:
        container.start()
    except Exception as exc:
        msg = (
            "DATABASE_URL was not set and Postgres could not be started via Docker. "
            "Fix by either:\n"
            "- setting DATABASE_URL to a test database URL, or\n"
            "- installing/running Docker so testcontainers can start Postgres.\n"
            f"Underlying error: {exc}"
        )
        raise RuntimeError(msg) from exc

    url_obj = make_url(container.get_connection_url()).set(
        drivername="postgresql+asyncpg"
    )
    os.environ["DATABASE_URL"] = url_obj.render_as_string(hide_password=False)
    yield container
    container.stop()
