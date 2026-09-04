"""The probe that decides between the named database and a disposable one."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.engine import make_url

from pathfinder.tests._support.database import asyncpg_url, can_connect


@pytest.mark.asyncio
async def test_the_database_the_session_settled_on_answers() -> None:
    """The tier settles the URL, so a test that asks for no fixture still connects."""
    assert await can_connect(os.environ["DATABASE_URL"]) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "failure"),
    [
        (
            "postgresql+asyncpg://postgres:postgres@127.0.0.1:1/pathfinder_test",
            "a refused port",
        ),
        (
            "postgresql+asyncpg://postgres:postgres@no-such-host.invalid:5432/x",
            "a host that does not resolve",
        ),
    ],
    ids=["refused-port", "unknown-host"],
)
async def test_a_url_that_does_not_answer_is_reported_as_unusable(
    url: str, failure: str
) -> None:
    """Every connection failure reads the same, so the fixture starts its own."""
    assert await can_connect(url) is False, failure


@pytest.mark.asyncio
async def test_a_server_that_answers_under_another_role_is_reported_as_unusable() -> (
    None
):
    """A server on the port is not the test database unless it takes the role."""
    stranger = make_url(os.environ["DATABASE_URL"]).set(
        username="no_such_role", password="no_such_password"
    )
    assert await can_connect(stranger.render_as_string(hide_password=False)) is False


def test_a_sync_url_is_probed_on_the_async_driver() -> None:
    assert asyncpg_url("postgresql://postgres:postgres@db:5432/pathfinder_test") == (
        "postgresql+asyncpg://postgres:postgres@db:5432/pathfinder_test"
    )
