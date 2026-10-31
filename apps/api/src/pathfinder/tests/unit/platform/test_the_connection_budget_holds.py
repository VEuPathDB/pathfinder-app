from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import assistant_core
import veupathdb_mcp

import pathfinder
from pathfinder.platform.config import Settings
from pathfinder.platform.connection_budget import (
    CONNECTION_BUDGET,
    DATABASE_CONNECTION_LIMIT,
    OPENER_CALLS,
    connection_budget,
)

_OPENERS = re.compile(
    r"\bcreate_async_engine\(|\bcreate_engine\(|\bPsycopgConnector\(|"
    r"\.from_conn_string\(|\basyncpg\.connect\(|\bpsycopg\.connect\(|"
    r"\bAsyncConnection\.connect\(|\bAsyncConnectionPool\(|\bConnectionPool\(|"
    r"\bcreate_pool\(",
)
_NOT_SERVED = ("tests", "devtools", "alembic")
_OUTSIDE_THE_SCANNED_PACKAGES = {"procrastinate.psycopg_connector"}


def _defaults() -> Settings:
    return Settings.model_construct()


def _opener_calls() -> Counter[str]:
    found = Counter[str]()
    for package in (pathfinder, assistant_core, veupathdb_mcp):
        root = Path(next(iter(package.__path__)))
        for path in root.rglob("*.py"):
            relative = path.relative_to(root.parent)
            if any(part in _NOT_SERVED for part in relative.parts):
                continue
            calls = len(_OPENERS.findall(path.read_text()))
            if calls:
                found[".".join(relative.with_suffix("").parts)] = calls
    return found


def test_every_process_fits_the_budget_with_the_default_settings() -> None:
    budget = connection_budget(_defaults())
    per_process = Counter[str]()
    for pool in budget:
        per_process[pool.process] += pool.worst_case

    assert dict(per_process) == {"api": 42, "worker": 33, "wdk-mcp": 11}
    assert sum(per_process.values()) == 86
    assert sum(per_process.values()) <= CONNECTION_BUDGET
    assert DATABASE_CONNECTION_LIMIT - CONNECTION_BUDGET == 10


def test_every_connection_opener_is_counted_in_the_budget() -> None:
    counted = {
        module for pool in connection_budget(_defaults()) for module in pool.opened_by
    }

    assert dict(_opener_calls()) == OPENER_CALLS
    assert set(OPENER_CALLS) == counted - _OUTSIDE_THE_SCANNED_PACKAGES
