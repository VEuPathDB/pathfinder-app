"""Every process but the api is switched off from the writes the api owns.

A process that rebuilds a catalog or syncs an embedding index races the api, so
the compose description of the worker and of wdk-mcp carries the guards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[7]
_COMPOSE = _REPO_ROOT / "docker-compose.yml"

# The writes only the api may make.
_GUARDS = {
    "CATALOG_REFRESH_ENABLED": "false",
    "EMBEDDING_INDEX_SYNC_ENABLED": "false",
}

_GUARDED_SERVICES = ("worker", "wdk-mcp")

# Tunables the operator sets.
_NOT_PINNED = ("WORKER_DEAD_HEARTBEAT_SECONDS", "WORKER_STALLED_JOB_TIMEOUT_SECONDS")


def _compose_environment(service: str) -> dict[str, str]:
    document: dict[str, Any] = yaml.safe_load(_COMPOSE.read_text())
    environment: dict[str, str] = document["services"][service]["environment"]
    return environment


@pytest.mark.parametrize("service", _GUARDED_SERVICES)
def test_every_guarded_compose_service_pins_the_same_guards(service: str) -> None:
    environment = _compose_environment(service)

    assert {key: environment.get(key) for key in _GUARDS} == _GUARDS


def test_the_api_is_the_process_that_syncs() -> None:
    """The guards mean nothing unless exactly one process is allowed to write."""
    assert _compose_environment("api")["EMBEDDING_INDEX_SYNC_ENABLED"] == "true"


def test_compose_passes_the_tunables_through_rather_than_hardcoding_them() -> None:
    environment = _compose_environment("worker")

    for key in _NOT_PINNED:
        assert environment[key].startswith(f"${{{key}:-")
