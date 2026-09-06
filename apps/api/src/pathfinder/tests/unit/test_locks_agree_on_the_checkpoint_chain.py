"""The app and the runtime package must install one checkpoint serializer."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[6]
API_LOCK = _REPO_ROOT / "apps" / "api" / "uv.lock"
CORE_LOCK = (
    _REPO_ROOT / "assistant-platform" / "packages" / "assistant-core" / "uv.lock"
)

# assistant_core owns the checkpoint serializer and its suite is the gate that
# decides whether a state type survives a round trip. A gate that runs another
# version than the app proves nothing about the app.
LANGGRAPH = "langgraph"


def _locked_versions(lock: Path) -> dict[str, str]:
    document = tomllib.loads(lock.read_text(encoding="utf-8"))
    packages = document["package"]
    return {str(entry["name"]): str(entry["version"]) for entry in packages}


def _langgraph_packages() -> list[str]:
    api = _locked_versions(API_LOCK)
    core = _locked_versions(CORE_LOCK)
    shared = set(api) & set(core)
    return sorted(name for name in shared if name.split("-")[0] == LANGGRAPH)


def test_the_checkpoint_chain_is_locked_in_both_places() -> None:
    assert "langgraph-checkpoint" in _langgraph_packages()
    assert "langgraph-checkpoint-postgres" in _langgraph_packages()


@pytest.mark.parametrize("package", _langgraph_packages())
def test_both_locks_resolve_the_same_version(package: str) -> None:
    assert _locked_versions(API_LOCK)[package] == _locked_versions(CORE_LOCK)[package]
