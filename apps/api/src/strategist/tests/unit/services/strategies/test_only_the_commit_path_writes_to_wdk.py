from __future__ import annotations

import ast
from pathlib import Path

_STRATEGIST = Path(__file__).resolve().parents[4]
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
        "services/strategies/_tree_write.py",
        "services/strategies/_wdk_step_calls.py",
    }
)
_NOT_YET_ON_IT = frozenset(
    {
        "devtools/seeds.py",
        "services/eval.py",
        "services/experiment/materialization.py",
        "services/strategies/save_substrategy.py",
        "services/strategies/naming.py",
        "services/strategies/wdk_sync.py",
        "services/strategies/abandoned_mint.py",
        "services/conversations/service.py",
        "services/user_data.py",
    }
)


def _writes_in(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        match node:
            case ast.Call(func=ast.Attribute(attr=name)) if name in _WRITES:
                found.add(name)
    return found


def _writers() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(_STRATEGIST.rglob("*.py")):
        relative = path.relative_to(_STRATEGIST).as_posix()
        if relative.startswith("tests/"):
            continue
        writes = _writes_in(path.read_text())
        if writes:
            found[relative] = writes
    return found


def test_only_the_commit_path_and_the_listed_writers_call_a_wdk_write() -> None:
    assert sorted(set(_writers()) - _THE_COMMIT_PATH) == sorted(_NOT_YET_ON_IT)


def test_a_new_caller_of_a_wdk_write_is_found() -> None:
    source = "async def f(api):\n    await api.update_step_search_config(1)\n"

    assert _writes_in(source) == {"update_step_search_config"}
