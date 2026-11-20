from __future__ import annotations

import os

import psycopg
from psycopg.sql import SQL, Identifier
from sqlalchemy.engine import make_url


def _worker() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "")


def worker_scoped(name: str) -> str:
    worker = _worker()
    return f"{name}_{worker}" if worker else name


def worker_database_url(url: str) -> str:
    parsed = make_url(url)
    return parsed.set(database=worker_scoped(str(parsed.database))).render_as_string(
        hide_password=False
    )


def shared_database_url(url: str) -> str:
    parsed = make_url(url)
    name = str(parsed.database)
    suffix = f"_{_worker()}"
    if not _worker() or not name.endswith(suffix):
        return url
    return parsed.set(database=name.removesuffix(suffix)).render_as_string(
        hide_password=False
    )


def create_worker_database(url: str) -> None:
    shared = shared_database_url(url)
    if url == shared:
        return
    server = make_url(shared).set(drivername="postgresql")
    name = Identifier(str(make_url(url).database))
    with psycopg.connect(
        server.render_as_string(hide_password=False), autocommit=True
    ) as connection:
        connection.execute(SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
        connection.execute(SQL("CREATE DATABASE {}").format(name))
