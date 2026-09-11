"""The database seams the suite runs on: whether a URL answers, a detached session, none."""

from __future__ import annotations

from asyncpg.exceptions import PostgresError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool


def asyncpg_url(url: str) -> str:
    """The same URL on the asyncpg driver."""
    parsed = make_url(url)
    if "asyncpg" in (parsed.drivername or ""):
        return url
    return parsed.set(drivername="postgresql+asyncpg").render_as_string(
        hide_password=False
    )


async def can_connect(url: str) -> bool:
    """True when the URL opens a transaction. Any failure answers False.

    A wrong host, a refused port, a missing role and a missing database are one
    answer to the caller: this URL is not the test database, so start one.
    """
    engine = create_async_engine(asyncpg_url(url), poolclass=NullPool)
    try:
        async with engine.begin():
            return True
    except SQLAlchemyError, OSError, PostgresError:
        return False
    finally:
        await engine.dispose()


def detached_session() -> AsyncSession:
    """A session bound to no engine: it opens and commits, and reads nothing."""
    return AsyncSession()


def no_database() -> AsyncSession:
    """The factory a caller that must not open a database session is given."""
    msg = "db factory should not be called in this test"
    raise AssertionError(msg)
