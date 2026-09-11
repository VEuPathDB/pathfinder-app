"""The two database seams a unit test runs on: a detached session, and none."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import UnboundExecutionError

from pathfinder.tests._support.database import detached_session, no_database


async def test_it_opens_and_commits_without_a_bind() -> None:
    """A tool that only writes through the session reaches no database."""
    async with detached_session() as session:
        await session.commit()

        assert session.in_transaction() is False


async def test_a_read_through_it_names_the_missing_bind() -> None:
    """A test that needs real rows is told what it lacks, not given none."""
    async with detached_session() as session:
        with pytest.raises(UnboundExecutionError):
            await session.execute(text("select 1"))


def test_each_call_opens_its_own_session() -> None:
    assert detached_session() is not detached_session()


def test_the_no_database_factory_names_the_call_it_refuses() -> None:
    """A tool that must open no session fails on the call, not on a later read."""
    with pytest.raises(AssertionError, match="db factory should not be called"):
        no_database()
