"""The agent-side scratchpad reaches the database through the service layer.

An agent module that opens its own session and drives a repository owns two
concerns: what the tool does, and how a note is stored.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

from pathfinder.services.conversations.scratchpad_service import ScratchpadNotebook

_AGENT_MODULES = (
    "pathfinder.ai.scratchpad.tools",
    "pathfinder.ai.scratchpad.toolset",
    "pathfinder.ai.scratchpad.compactor",
)


def _module(name: str) -> ModuleType:
    return importlib.import_module(name)


@pytest.mark.parametrize("name", _AGENT_MODULES)
def test_no_agent_module_names_a_repository(name: str) -> None:
    bound = {
        key
        for key, value in vars(_module(name)).items()
        if getattr(value, "__module__", "").startswith("pathfinder.persistence")
    }
    assert sorted(bound) == [], name


@pytest.mark.parametrize("name", _AGENT_MODULES)
def test_no_agent_module_imports_the_persistence_package(name: str) -> None:
    source = importlib.import_module(name).__file__
    assert source is not None
    assert "pathfinder.persistence" not in Path(source).read_text()


_NOTEBOOK_METHODS = (
    "create",
    "update",
    "delete",
    "set_pinned",
    "get",
    "list_notes",
    "search_notes",
    "total_notes",
    "compaction_totals",
    "notes_to_compact",
    "commit_compaction",
)


def test_the_notebook_facade_covers_what_the_tools_need() -> None:
    missing = [
        name
        for name in _NOTEBOOK_METHODS
        if not callable(getattr(ScratchpadNotebook, name, None))
    ]

    assert missing == []
