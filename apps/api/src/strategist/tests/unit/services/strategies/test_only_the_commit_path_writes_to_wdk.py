from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[5]
_PACKAGES = ("strategist", "strategist_scripted")
_WRITES = frozenset(
    {
        "create_step",
        "create_combined_step",
        "create_transform_step",
        "update_step_search_config",
        "update_step_properties",
        "delete_step",
        "delete_orphaned_steps",
        "set_step_filter",
        "create_strategy",
        "update_strategy",
        "set_saved",
        "delete_strategy",
    }
)
_THE_COMMIT_PATH = frozenset(
    {
        "strategist/services/strategies/commit_tree.py",
        "strategist/services/strategies/_tree_write.py",
        "strategist/services/strategies/_wdk_step_calls.py",
    }
)
_OFF_THE_TREE = {
    "strategist/services/strategies/naming.py": (
        {"update_strategy"},
        "renames the strategy",
    ),
    "strategist/services/strategies/wdk_sync.py": (
        {"set_saved"},
        "sets the saved mark",
    ),
    "strategist/services/strategies/abandoned_mint.py": (
        {"delete_strategy"},
        "deletes a whole strategy",
    ),
    "strategist/services/conversations/service.py": (
        {"delete_strategy"},
        "deletes a whole strategy",
    ),
    "strategist/services/user_data.py": (
        {"delete_strategy"},
        "deletes a whole strategy",
    ),
    "strategist/services/eval.py": (
        {"delete_strategy"},
        "deletes a gold strategy it could not use",
    ),
    "strategist_scripted/seeds/record.py": (
        {"delete_strategy"},
        "deletes the strategy it measured",
    ),
}


def _writes_in(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        match node:
            case ast.Call(func=ast.Attribute(attr=name)) if name in _WRITES:
                found.add(name)
    return found


def _writers() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    paths = (path for package in _PACKAGES for path in (_SRC / package).rglob("*.py"))
    for path in sorted(paths):
        relative = path.relative_to(_SRC).as_posix()
        if relative.startswith("strategist/tests/"):
            continue
        writes = _writes_in(path.read_text())
        if writes:
            found[relative] = writes
    return found


def test_only_the_commit_path_and_the_listed_writers_call_a_wdk_write() -> None:
    found = {
        path: writes
        for path, writes in _writers().items()
        if path not in _THE_COMMIT_PATH
    }

    assert found == {path: writes for path, (writes, _why) in _OFF_THE_TREE.items()}


def test_a_new_caller_of_a_wdk_write_is_found() -> None:
    source = "async def f(api):\n    await api.update_step_search_config(1)\n"

    assert _writes_in(source) == {"update_step_search_config"}
