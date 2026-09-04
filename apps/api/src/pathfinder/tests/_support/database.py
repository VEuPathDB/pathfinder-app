"""Whether a Postgres URL answers, for the fixture that picks the test database."""

from __future__ import annotations

from asyncpg.exceptions import PostgresError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
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
