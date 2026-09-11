"""One throwaway database per migration test, and the reads the tests make of it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
from alembic.config import Config
from psycopg.abc import QueryNoTemplate
from psycopg.sql import SQL, Identifier
from sqlalchemy.engine import make_url

ALEMBIC_INI = Path(__file__).resolve().parents[5] / "alembic.ini"


def psycopg_url(url: str) -> str:
    """The same database, addressed by the driver psycopg speaks."""
    return (
        make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    )


def create_database(base_url: str, name: str) -> str:
    with psycopg.connect(psycopg_url(base_url), autocommit=True) as connection:
        connection.execute(SQL("DROP DATABASE IF EXISTS {}").format(Identifier(name)))
        connection.execute(SQL("CREATE DATABASE {}").format(Identifier(name)))
    return make_url(base_url).set(database=name).render_as_string(hide_password=False)


def drop_database(base_url: str, name: str) -> None:
    with psycopg.connect(psycopg_url(base_url), autocommit=True) as connection:
        connection.execute(SQL("DROP DATABASE IF EXISTS {}").format(Identifier(name)))


def alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    return config


def rows(
    url: str, query: QueryNoTemplate, params: tuple[Any, ...] = ()
) -> list[tuple[Any, ...]]:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        return connection.execute(query, params).fetchall()


def columns(url: str, table: str) -> set[str]:
    found = rows(
        url,
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table,),
    )
    return {row[0] for row in found}


def indexes(url: str, table: str) -> set[str]:
    found = rows(url, "SELECT indexname FROM pg_indexes WHERE tablename = %s", (table,))
    return {row[0] for row in found}


def tables(url: str) -> set[str]:
    found = rows(
        url,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public'",
    )
    return {row[0] for row in found}
