"""A tier's conftest may not write the process environment.

The tiers share one process, and one tier's global write decides what another
tier's settings say. Only the root conftest sets the suite's own defaults.
"""

from __future__ import annotations

import ast
from pathlib import Path

import strategist

_MUTATORS = frozenset({"setdefault", "update", "pop", "clear", "popitem"})


def _tier_conftests() -> list[Path]:
    tests = Path(strategist.__file__).parent / "tests"
    return sorted(path for path in tests.rglob("conftest.py") if path.parent != tests)


def _is_process_environ(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _environ_writes(source: str) -> list[int]:
    tree = ast.parse(source)
    lines: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and _is_process_environ(node.value)
        ):
            lines.append(node.lineno)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATORS
            and _is_process_environ(node.func.value)
        ):
            lines.append(node.lineno)
    return sorted(lines)


def test_no_tier_conftest_writes_the_process_environment() -> None:
    offenders = {
        str(path): _environ_writes(path.read_text())
        for path in _tier_conftests()
        if _environ_writes(path.read_text())
    }

    assert offenders == {}, "use monkeypatch.setenv in a fixture instead"
